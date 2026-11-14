"""Builds assets/box_model.npz from labeled screenshots.

Put full-screen screenshots (taken while the SEARCH prompt is showing) in two folders:

    examples/chest/   gold, rare (blue) and sprite chests
    examples/box/     ammo boxes and fruit boxes

then run:   python tools/train_box_filter.py examples
Add --keep to merge with the examples already in assets/box_model.npz.
"""

import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import boxfilter  # noqa: E402

ASSETS = Path(__file__).resolve().parent.parent / "assets"
MODEL = ASSETS / "box_model.npz"
IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".bmp"}


def collect(root: Path, reference: np.ndarray):
    features, labels, skipped = [], [], []
    for folder, label in (("chest", 1), ("box", 0)):
        for path in sorted((root / folder).rglob("*")):
            if path.suffix.lower() not in IMAGE_TYPES:
                continue
            image = cv2.imread(str(path))
            if image is None:
                skipped.append(path.name)
                continue
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            word = boxfilter.find_prompt_word(gray, reference)
            crop = boxfilter.object_crop(image, *word) if word else None
            if crop is None:
                skipped.append(path.name)
                continue
            features.append(boxfilter.feature_vector(crop))
            labels.append(label)
    return np.array(features, dtype=np.float32), np.array(labels, dtype=np.int32), skipped


def main(argv: list[str]) -> int:
    keep = "--keep" in argv
    args = [a for a in argv if not a.startswith("--")]
    if len(args) != 1:
        print(__doc__)
        return 1
    reference = cv2.imread(str(ASSETS / "prompt_word.png"), cv2.IMREAD_GRAYSCALE)
    features, labels, skipped = collect(Path(args[0]), reference)
    if keep and MODEL.exists():
        with np.load(MODEL) as old:
            features = np.vstack([old["features"], features]) if len(features) else old["features"]
            labels = np.concatenate([old["is_chest"], labels]) if len(labels) else old["is_chest"]
    if len(set(labels.tolist())) < 2:
        print("Need at least one chest and one box example.")
        return 1
    np.savez_compressed(MODEL, features=features, is_chest=labels, reference=reference)
    print(f"Saved {len(labels)} examples ({int(labels.sum())} chests, {int((labels == 0).sum())} boxes).")
    if skipped:
        print("Skipped (prompt not found):", ", ".join(skipped))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
