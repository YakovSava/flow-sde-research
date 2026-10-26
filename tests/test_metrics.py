import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from metrics import (  # noqa: E402
    bootstrap,
    frontier_value,
    geometry_error,
    lowpass,
    texture_advantage,
    texture_energy,
)


def test_lowpass_pools_blocks() -> None:
    latent = np.arange(16, dtype=np.float64).reshape(1, 4, 4)
    pooled = lowpass(latent, pool=2)
    assert pooled.shape == (1, 2, 2)
    assert pooled[0, 0, 0] == np.mean([0, 1, 4, 5])


def test_constant_field_has_no_texture() -> None:
    assert texture_energy(np.full((2, 16, 16), 3.0)) == 0.0


def test_texture_ignores_block_means() -> None:
    generator = np.random.default_rng(0)
    blocks = generator.normal(size=(1, 2, 2))
    smooth = np.repeat(np.repeat(blocks, 8, axis=-2), 8, axis=-1)
    assert texture_energy(smooth) < 1e-12


def test_geometry_error_zero_for_identical_and_blind_to_detail() -> None:
    generator = np.random.default_rng(1)
    base = generator.normal(size=(1, 16, 16))
    assert geometry_error(base, base) == 0.0
    detail = base.copy()
    detail[..., ::2, ::2] += 1.0
    detail[..., 1::2, 1::2] -= 1.0
    assert geometry_error(detail, base, pool=2) < 1e-12


def test_frontier_interpolates_and_rejects_extrapolation() -> None:
    points = [(0.4, 0.3), (0.2, 0.1), (0.3, 0.2)]
    assert frontier_value(points, 0.25) == np.interp(0.25, [0.2, 0.3, 0.4], [0.1, 0.2, 0.3])
    assert np.isnan(frontier_value(points, 0.1))
    assert np.isnan(frontier_value(points, 0.5))


def test_texture_advantage_is_zero_on_the_frontier() -> None:
    geometry = {
        "a": np.array([0.2, 0.2]),
        "b": np.array([0.4, 0.4]),
        "mid": np.array([0.3, 0.3]),
    }
    texture = {
        "a": np.array([0.1, 0.1]),
        "b": np.array([0.3, 0.3]),
        "mid": np.array([0.25, 0.25]),
    }
    advantage = texture_advantage(geometry, texture, ["a", "b"], "mid", np.arange(2))
    assert abs(advantage - 0.05) < 1e-12


def test_bootstrap_interval_contains_point_estimate() -> None:
    values = np.random.default_rng(2).normal(loc=1.0, scale=0.3, size=40)
    point, low, high = bootstrap(lambda indices: float(values[indices].mean()), values.size)
    assert low <= point <= high
    assert 0.8 < point < 1.2
