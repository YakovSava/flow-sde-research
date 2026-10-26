from typing import Callable, Sequence

import numpy as np

POOL: int = 8


def lowpass(latent: np.ndarray, pool: int = POOL) -> np.ndarray:
    height, width = latent.shape[-2], latent.shape[-1]
    trimmed = latent[..., : height // pool * pool, : width // pool * pool]
    shape = trimmed.shape[:-2] + (
        trimmed.shape[-2] // pool,
        pool,
        trimmed.shape[-1] // pool,
        pool,
    )
    return trimmed.reshape(shape).mean(axis=(-3, -1))


def texture_energy(latent: np.ndarray, pool: int = POOL) -> float:
    coarse = lowpass(latent, pool)
    expanded = np.repeat(np.repeat(coarse, pool, axis=-2), pool, axis=-1)
    height, width = expanded.shape[-2], expanded.shape[-1]
    return float(np.sqrt(np.mean((latent[..., :height, :width] - expanded) ** 2)))


def geometry_error(latent: np.ndarray, reference: np.ndarray, pool: int = POOL) -> float:
    return float(np.sqrt(np.mean((lowpass(latent, pool) - lowpass(reference, pool)) ** 2)))


def frontier_value(points: Sequence[tuple[float, float]], at: float) -> float:
    ordered = sorted(points)
    xs = [point[0] for point in ordered]
    ys = [point[1] for point in ordered]
    if at < xs[0] or at > xs[-1]:
        return float("nan")
    return float(np.interp(at, xs, ys))


def texture_advantage(
    geometry: dict[str, np.ndarray],
    texture: dict[str, np.ndarray],
    frontier: Sequence[str],
    variant: str,
    indices: np.ndarray,
) -> float:
    points = [
        (float(geometry[name][indices].mean()), float(texture[name][indices].mean()))
        for name in frontier
    ]
    expected = frontier_value(points, float(geometry[variant][indices].mean()))
    return float(texture[variant][indices].mean()) - expected


def bootstrap(
    statistic: Callable[[np.ndarray], float],
    count: int,
    resamples: int = 2000,
    seed: int = 0,
) -> tuple[float, float, float]:
    generator = np.random.default_rng(seed)
    draws = generator.integers(0, count, size=(resamples, count))
    values = np.array([statistic(indices) for indices in draws])
    point = statistic(np.arange(count))
    if np.all(np.isnan(values)):
        return point, float("nan"), float("nan")
    low, high = np.nanpercentile(values, [2.5, 97.5])
    return point, float(low), float(high)
