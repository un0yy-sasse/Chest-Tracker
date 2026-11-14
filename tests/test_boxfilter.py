import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import boxfilter
from boxfilter import BoxFilter, FEATURE_COUNT, SKIP_BELOW, feature_vector, find_prompt_word, object_crop

ASSETS = Path(__file__).resolve().parent.parent / "assets"


def reference():
    return cv2.imread(str(ASSETS / "prompt_word.png"), cv2.IMREAD_GRAYSCALE)


def test_the_bundled_examples_load_and_hold_both_kinds():
    with np.load(ASSETS / "box_model.npz") as saved:
        labels = saved["is_chest"]
        assert saved["features"].shape == (len(labels), FEATURE_COUNT)
    assert (labels == 1).sum() >= 20 and (labels == 0).sum() >= 20
    assert boxfilter.load_bundled() is not None


def test_the_bundled_filter_knows_its_own_examples():
    with np.load(ASSETS / "box_model.npz") as saved:
        features, labels = saved["features"], saved["is_chest"]
    model = boxfilter.load_bundled()
    scores = np.array([model.probability(f) for f in features])
    assert (scores[labels == 1] >= SKIP_BELOW).all()  # no chest is ever skipped
    assert (scores[labels == 0] < 0.5).mean() > 0.9


def test_training_is_repeatable():
    with np.load(ASSETS / "box_model.npz") as saved:
        features, labels, ref = saved["features"], saved["is_chest"], saved["reference"]
    a, b = BoxFilter(features, labels, ref), BoxFilter(features, labels, ref)
    assert [a.probability(f) for f in features[:10]] == [b.probability(f) for f in features[:10]]


def test_a_missing_or_damaged_model_means_no_filter(tmp_path):
    assert BoxFilter.load(tmp_path / "nope.npz") is None
    bad = tmp_path / "bad.npz"
    bad.write_bytes(b"not a model")
    assert BoxFilter.load(bad) is None
    wrong = tmp_path / "wrong.npz"
    np.savez(wrong, features=np.zeros((4, 3)), is_chest=np.array([0, 1, 0, 1]), reference=reference())
    assert BoxFilter.load(wrong) is None
    one_kind = tmp_path / "one.npz"
    np.savez(one_kind, features=np.zeros((4, FEATURE_COUNT)), is_chest=np.ones(4), reference=reference())
    assert BoxFilter.load(one_kind) is None


def test_feature_vector_has_a_fixed_size_for_any_crop():
    for shape in [(200, 200, 3), (60, 40, 3), (120, 300, 3)]:
        crop = np.random.default_rng(0).integers(0, 255, shape, dtype=np.uint8)
        vector = feature_vector(crop)
        assert vector.shape == (FEATURE_COUNT,) and np.isfinite(vector).all()


def scene_with_prompt(scale=1.0, at=(900, 600)):
    ref = reference()
    word = cv2.resize(ref, (round(ref.shape[1] * scale), round(ref.shape[0] * scale)))
    frame = np.random.default_rng(1).integers(40, 90, (1000, 1600), dtype=np.uint8)
    frame = cv2.GaussianBlur(frame, (0, 0), 3)
    frame[at[1] : at[1] + word.shape[0], at[0] : at[0] + word.shape[1]] = word
    return frame


@pytest.mark.parametrize("scale", [0.7, 1.0, 1.25])
def test_the_prompt_word_is_found_at_other_screen_sizes(scale):
    found = find_prompt_word(scene_with_prompt(scale), reference())
    assert found is not None
    left, top, got = found
    assert abs(left - 900) <= 4 and abs(top - 600) <= 4
    assert abs(got - scale) < 0.15


def test_searching_near_a_known_spot_and_finding_nothing():
    assert find_prompt_word(scene_with_prompt(), reference(), near=(900, 600)) is not None
    blank = np.full((1000, 1600), 50, dtype=np.uint8)
    assert find_prompt_word(blank, reference()) is None


def test_the_object_crop_sits_left_of_the_prompt_and_scales():
    frame = np.zeros((1000, 1600, 3), dtype=np.uint8)
    crop = object_crop(frame, 900, 600, 1.0)
    assert crop.shape[:2] == (200, 200)
    assert object_crop(frame, 20, 600, 1.0) is None  # no room left of the prompt
    assert object_crop(frame, 900, 600, 0.5).shape[:2] == (100, 100)


def test_chest_score_can_be_asked_on_a_gray_frame_without_color():
    model = boxfilter.load_bundled()
    gray = scene_with_prompt()
    color = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    score = model.chest_score(color, gray)
    assert score is None or 0.0 <= score <= 1.0
