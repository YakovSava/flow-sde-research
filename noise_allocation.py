import math
from typing import Sequence

CURVATURE: str = "curvature"
PC_ERROR: str = "pc_error"
SIGNALS: list[str] = [CURVATURE, PC_ERROR]


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


class RunningReference:
    def __init__(self, smoothing: float) -> None:
        self.smoothing: float = smoothing
        self.value: float | None = None

    def update(self, sample: float) -> float:
        if self.value is None:
            self.value = sample
        else:
            self.value = (1.0 - self.smoothing) * self.value + self.smoothing * sample
        return self.value


class NoiseAllocator:
    def __init__(
        self,
        eta: float,
        step_sizes: Sequence[float],
        active: Sequence[bool],
        exponent: float = 0.0,
        spread: float = 3.0,
        smoothing: float = 0.5,
        tau_max: float = 4.0,
        conserve_budget: bool = True,
    ) -> None:
        self.eta: float = eta
        self.step_sizes: list[float] = [float(size) for size in step_sizes]
        self.active: list[bool] = [bool(flag) for flag in active]
        self.exponent: float = exponent
        self.spread: float = spread
        self.tau_max: float = tau_max
        self.conserve_budget: bool = conserve_budget
        self.reference: RunningReference = RunningReference(smoothing)
        self.ratio: float | None = None
        self.spent: float = 0.0
        self.budget: float = eta**2 * self.window_size(0)
        self.last_active: int = max(
            (index for index, flag in enumerate(self.active) if flag),
            default=-1,
        )

    def window_size(self, start: int) -> float:
        return sum(
            size
            for size, flag in zip(self.step_sizes[start:], self.active[start:])
            if flag
        )

    def observe(self, signal: float | None) -> None:
        if signal is None or signal <= 0.0:
            self.ratio = None
            return
        self.ratio = signal / self.reference.update(signal)

    def weight(self) -> float:
        if self.exponent == 0.0 or self.ratio is None:
            return 1.0
        return clamp(
            self.ratio**self.exponent,
            1.0 / self.spread,
            self.spread,
        )

    def level(self, index: int) -> float:
        if not self.active[index]:
            return 0.0
        weight: float = self.weight()
        size: float = self.step_sizes[index]
        if self.exponent == 0.0 or not self.conserve_budget:
            tau: float = min(self.eta * math.sqrt(weight), self.tau_max)
        else:
            tau = min(math.sqrt(self.conserved_power(index, weight, size)), self.tau_max)
        self.spent += tau * tau * size
        return tau

    def conserved_power(self, index: int, weight: float, size: float) -> float:
        remaining: float = max(self.budget - self.spent, 0.0)
        if index == self.last_active:
            return remaining / size
        nominal: float = self.eta**2 * self.window_size(index)
        share: float = self.eta**2 * weight * remaining / nominal
        return min(share, remaining / size)
