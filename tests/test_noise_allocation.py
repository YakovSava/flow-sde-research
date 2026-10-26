import pathlib
import random
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from noise_allocation import NoiseAllocator  # noqa: E402

STEP_SIZES: list[float] = [0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3]
ACTIVE: list[bool] = [False, False, True, True, True, True, True, True, False, False]


def make(**options: object) -> NoiseAllocator:
    settings: dict[str, object] = {
        "eta": 1.6,
        "step_sizes": STEP_SIZES,
        "active": ACTIVE,
    }
    settings.update(options)
    return NoiseAllocator(**settings)


def run(allocator: NoiseAllocator, signals: list[float | None]) -> list[float]:
    levels: list[float] = []
    for index, signal in enumerate(signals):
        allocator.observe(signal)
        levels.append(allocator.level(index))
    return levels


def random_signals(seed: int) -> list[float | None]:
    generator = random.Random(seed)
    return [None] + [generator.uniform(0.05, 20.0) for _ in range(len(STEP_SIZES) - 1)]


def test_zero_exponent_reproduces_constant_eta() -> None:
    levels = run(make(exponent=0.0), random_signals(0))
    expected = [1.6 if flag else 0.0 for flag in ACTIVE]
    assert levels == expected


def test_inactive_steps_receive_no_noise() -> None:
    levels = run(make(exponent=1.0), random_signals(1))
    for level, flag in zip(levels, ACTIVE):
        if not flag:
            assert level == 0.0


@pytest.mark.parametrize("exponent", [-2.0, -1.0, -0.5, 0.5, 1.0, 2.0])
@pytest.mark.parametrize("seed", range(20))
def test_conserved_budget_is_spent_exactly(exponent: float, seed: int) -> None:
    allocator = make(exponent=exponent, tau_max=100.0)
    run(allocator, random_signals(seed))
    assert allocator.spent == pytest.approx(allocator.budget, rel=1e-9)


def test_budget_matches_uniform_run() -> None:
    uniform = make(exponent=0.0)
    run(uniform, random_signals(2))
    adaptive = make(exponent=1.0, tau_max=100.0)
    run(adaptive, random_signals(2))
    assert adaptive.spent == pytest.approx(uniform.spent, rel=1e-9)


def test_unconserved_budget_drifts() -> None:
    allocator = make(exponent=1.0, conserve_budget=False, tau_max=100.0)
    run(allocator, random_signals(3))
    assert allocator.spent != pytest.approx(allocator.budget, rel=1e-3)


def test_clipping_never_overspends() -> None:
    allocator = make(exponent=1.0, tau_max=1.0)
    run(allocator, random_signals(4))
    assert allocator.spent <= allocator.budget * (1.0 + 1e-9)


def test_weight_is_bounded_by_spread() -> None:
    allocator = make(exponent=3.0, spread=2.0)
    for signal in [1.0, 1000.0, 0.001, 50.0]:
        allocator.observe(signal)
        assert 0.5 <= allocator.weight() <= 2.0


def test_sign_of_exponent_flips_allocation() -> None:
    signals: list[float | None] = [None, 1.0, 1.0, 8.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]
    stiff = run(make(exponent=1.0, tau_max=100.0), signals)
    smooth = run(make(exponent=-1.0, tau_max=100.0), signals)
    assert stiff[3] > 1.6 > smooth[3]


def test_missing_signal_falls_back_to_unit_weight() -> None:
    allocator = make(exponent=2.0)
    allocator.observe(None)
    assert allocator.weight() == 1.0


def test_empty_window_is_harmless() -> None:
    allocator = make(active=[False] * len(STEP_SIZES), exponent=1.0)
    levels = run(allocator, random_signals(5))
    assert levels == [0.0] * len(STEP_SIZES)
    assert allocator.budget == 0.0
