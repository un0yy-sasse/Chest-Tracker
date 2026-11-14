"""Tells chests from look-alike boxes (ammo, fruit) by the colors next to the SEARCH prompt.

Every searchable object shows the same prompt, so the prompt can't say which one it is.
The object itself sits just left of the prompt. Chests and boxes differ a lot in color, and
colors hold up from any angle, so the filter looks at a color summary of that spot.

The summaries of example screenshots ship in assets/box_model.npz. A small random forest
(from OpenCV, which the app already uses) is trained from them when the app starts. To add
examples, see tools/train_box_filter.py.
"""

from pathlib import Path

import cv2
import numpy as np

# The prompt word as it looks at 1920x1200. Distances below are measured at that size and
# scaled by how big the word turns out to be in the real frame.
REF_TEXT_WIDTH, REF_TEXT_HEIGHT = 85, 25
PILL_LEFT_OF_TEXT = 84  # the prompt's round edge is this far left of the word
OBJECT_WIDTH, OBJECT_HEIGHT = 200, 200  # the part of the object to look at
PROMPT_STRIP = 24  # the right-hand sliver of the crop is the prompt itself: ignored
SCALES = (0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.25, 1.4, 1.6)
MIN_PILL_SCORE = 0.6
MIN_OBJECT_WIDTH = 50  # a crop narrower than this (at reference size) says too little
SKIP_BELOW = 0.35  # a chest score under this is a box. Anything unsure still counts.

FEATURE_COUNT = 12 * 4 + 5 + 5


def feature_vector(crop_bgr: np.ndarray) -> np.ndarray:
    """A color summary of the object: hue/saturation counts, brightness spread, color strength."""
    crop = crop_bgr[:, : max(1, crop_bgr.shape[1] - PROMPT_STRIP)]
    small = cv2.resize(crop, (96, 96), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [12, 4], [0, 180, 0, 256]).flatten()
    hist /= max(hist.sum(), 1.0)
    value = hsv[..., 2].astype(np.float64).ravel()
    quantiles = np.percentile(value, [10, 25, 50, 75, 90]) / 255
    lab = cv2.cvtColor(small, cv2.COLOR_BGR2LAB).astype(np.float64)
    chroma = np.sqrt((lab[..., 1] - 128) ** 2 + (lab[..., 2] - 128) ** 2)
    extras = [(value > 200).mean(), (value < 90).mean(), chroma.mean() / 60, chroma.std() / 60,
              hsv[..., 1].mean() / 255]
    return np.concatenate([hist, quantiles, extras]).astype(np.float32)


def find_prompt_word(
    gray: np.ndarray, reference: np.ndarray, near: tuple[int, int] | None = None, radius: int = 90
) -> tuple[int, int, float] | None:
    """Finds the word SEARCH: (left, top, scale) of the best match, or None.

    `near` is where the app already saw the prompt, so only that neighbourhood is searched.
    """
    x0 = y0 = 0
    view = gray
    if near is not None:
        x0, y0 = max(0, near[0] - radius), max(0, near[1] - radius)
        view = gray[y0 : near[1] + radius, x0 : near[0] + radius]
    best: tuple[float, int, int, float] | None = None
    for scale in SCALES:
        size = (max(8, round(reference.shape[1] * scale)), max(4, round(reference.shape[0] * scale)))
        template = cv2.resize(reference, size, interpolation=cv2.INTER_AREA)
        if template.shape[0] >= view.shape[0] or template.shape[1] >= view.shape[1]:
            continue
        result = np.nan_to_num(cv2.matchTemplate(view, template, cv2.TM_CCOEFF_NORMED), nan=-1.0)
        _, score, _, loc = cv2.minMaxLoc(result)
        if best is None or score > best[0]:
            best = (float(score), loc[0] + x0, loc[1] + y0, scale)
    if best is None or best[0] < MIN_PILL_SCORE:
        return None
    return best[1], best[2], best[3]


def object_crop(color_bgr: np.ndarray, word_left: int, word_top: int, scale: float) -> np.ndarray | None:
    """The patch of screen where the object sits: just left of the prompt, centred on it."""
    centre_y = word_top + round(REF_TEXT_HEIGHT * scale / 2)
    right = word_left - round(PILL_LEFT_OF_TEXT * scale)
    left = right - round(OBJECT_WIDTH * scale)
    top = centre_y - round(OBJECT_HEIGHT * scale / 2)
    bottom = centre_y + round(OBJECT_HEIGHT * scale / 2)
    left, top = max(0, left), max(0, top)
    right, bottom = min(color_bgr.shape[1], right), min(color_bgr.shape[0], bottom)
    if right - left < MIN_OBJECT_WIDTH * scale or bottom - top < MIN_OBJECT_WIDTH * scale:
        return None
    return color_bgr[top:bottom, left:right]


class BoxFilter:
    """A chest-or-box score for the object next to a visible prompt."""

    def __init__(self, features: np.ndarray, is_chest: np.ndarray, reference: np.ndarray):
        self.reference = reference
        self.features = features.astype(np.float32)
        self.is_chest = is_chest.astype(np.int32)
        self.forest = self._train(self.features, self.is_chest)

    @staticmethod
    def _train(features: np.ndarray, labels: np.ndarray):
        cv2.setRNGSeed(0)  # the same samples always give the same forest
        forest = cv2.ml.RTrees_create()
        forest.setMaxDepth(8)
        forest.setMinSampleCount(2)
        forest.setActiveVarCount(0)
        forest.setCalculateVarImportance(False)
        forest.setTermCriteria((cv2.TERM_CRITERIA_MAX_ITER, 300, 0))
        forest.train(features, cv2.ml.ROW_SAMPLE, labels)
        return forest

    @classmethod
    def load(cls, path: Path) -> "BoxFilter | None":
        """None if the sample file is missing or damaged: counting then works as before."""
        try:
            with np.load(path) as saved:
                features, labels, reference = saved["features"], saved["is_chest"], saved["reference"]
            if features.ndim != 2 or features.shape[1] != FEATURE_COUNT or len(features) != len(labels):
                return None
            if len(set(labels.tolist())) < 2:
                return None
            return cls(features, labels, reference)
        except (OSError, ValueError, KeyError):
            return None

    def probability(self, features: np.ndarray) -> float:
        """Share of the forest's trees that call this a chest, from 0 to 1."""
        votes = self.forest.getVotes(features.reshape(1, -1).astype(np.float32), 0)
        votes = votes[1] if isinstance(votes, tuple) else votes
        classes = votes[0]  # row 0: the class labels, row 1: how many trees chose each
        counts = votes[1]
        total = float(counts.sum())
        if total <= 0:
            return 0.5
        for label, count in zip(classes, counts):
            if int(label) == 1:
                return float(count) / total
        return 0.0

    def chest_score(
        self, color: np.ndarray, gray: np.ndarray, near: tuple[int, int] | None = None
    ) -> float | None:
        """How chest-like the object by the prompt is, or None when it can't be told."""
        word = find_prompt_word(gray, self.reference, near)
        if word is None:
            return None
        crop = object_crop(color[..., :3] if color.ndim == 3 else color, *word)
        if crop is None:
            return None
        return self.probability(feature_vector(crop))


def load_bundled() -> "BoxFilter | None":
    """The filter built from the examples that ship with the app (None if they are missing)."""
    import sys

    folder = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return BoxFilter.load(folder / "assets" / "box_model.npz")
