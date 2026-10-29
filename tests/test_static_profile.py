import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from noise_allocation import NoiseAllocator  # noqa: E402
from static_profile import build_profiles, mean_power_profile, split_runs  # noqa: E402

STEP_SIZES: list[float] = [0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3]
ACTIVE: list[bool] = [False, False, True, True, True, True, True, True, False, False]


def make(profile: list[float] | None, **options: object) -> NoiseAllocator:
    settings: dict[str, object] = {"eta": 1.6, "step_sizes": STEP_SIZES, "active": ACTIVE}
    settings.update(options)
    return NoiseAllocator(profile=profile, **settings)


def levels(allocator: NoiseAllocator) -> list[float]:
    return [allocator.level(index) for index in range(len(STEP_SIZES))]


def test_flat_profile_matches_uniform_eta() -> None:
    result = levels(make([1.0] * len(STEP_SIZES)))
    assert result == pytest.approx([1.6 if flag else 0.0 for flag in ACTIVE])


@pytest.mark.parametrize("profile", [
    [0.0, 0.0, 5.0, 1.0, 1.0, 1.0, 0.2, 0.1, 0.0, 0.0],
    [3.0] * 10,
    [0.1, 0.9, 0.3, 2.0, 0.5, 4.0, 0.7, 1.1, 8.0, 9.0],
])
def test_profile_conserves_budget(profile: list[float]) -> None:
    allocator = make(profile, tau_max=100.0)
    levels(allocator)
    assert allocator.spent == pytest.approx(allocator.budget, rel=1e-12)


def test_profile_shape_is_preserved() -> None:
    profile = [0.0, 0.0, 4.0, 2.0, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0]
    result = levels(make(profile, tau_max=100.0))
    ratio = (result[2] / result[3]) ** 2
    assert ratio == pytest.approx(2.0)


def test_profile_never_noises_inactive_steps() -> None:
    result = levels(make([1.0] * len(STEP_SIZES)))
    for value, flag in zip(result, ACTIVE):
        if not flag:
            assert value == 0.0


def test_wrong_length_is_rejected() -> None:
    with pytest.raises(ValueError):
        make([1.0, 2.0])


def test_all_zero_profile_is_silent() -> None:
    assert levels(make([0.0] * len(STEP_SIZES))) == [0.0] * len(STEP_SIZES)


def test_trace_parsing_and_mean_power(tmp_path: pathlib.Path) -> None:
    lines = [
        json.dumps({"i": index, "tau": tau, "signal": None})
        for run in ([0.0, 2.0, 1.0], [0.0, 4.0, 3.0])
        for index, tau in enumerate(run)
    ]
    runs = split_runs(lines)
    assert runs == [[0.0, 2.0, 1.0], [0.0, 4.0, 3.0]]
    assert mean_power_profile(runs, 4) == pytest.approx([0.0, 10.0, 5.0, 0.0])

    path = tmp_path / "trace.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert build_profiles({3: path})["3"] == pytest.approx([0.0, 10.0, 5.0])
