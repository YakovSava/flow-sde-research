import importlib.util
import pathlib
import sys
from typing import Any, Callable

import pytest

COMFY_ROOT: pathlib.Path = pathlib.Path(__file__).resolve().parents[3]
PACKAGE_ROOT: pathlib.Path = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(COMFY_ROOT))

torch = pytest.importorskip("torch")
kds = pytest.importorskip("comfy.k_diffusion.sampling")
model_sampling_module = pytest.importorskip("comfy.model_sampling")

spec = importlib.util.spec_from_file_location(
    "flow_sde_research",
    PACKAGE_ROOT / "__init__.py",
    submodule_search_locations=[str(PACKAGE_ROOT)],
)
package = importlib.util.module_from_spec(spec)
sys.modules["flow_sde_research"] = package
spec.loader.exec_module(package)

from flow_sde_research.sampler import sample_flow_sde  # noqa: E402

SHAPE: tuple[int, int, int, int] = (1, 16, 32, 32)
SIGMA_FLOOR: float = 1e-4


class FlowSampling(
    model_sampling_module.ModelSamplingDiscreteFlow,
    model_sampling_module.CONST,
):
    pass


class Patcher:
    def __init__(self, sampling: FlowSampling) -> None:
        self.sampling: FlowSampling = sampling

    def get_model_object(self, name: str) -> FlowSampling:
        return self.sampling


class Inner:
    def __init__(self, sampling: FlowSampling) -> None:
        self.model_patcher: Patcher = Patcher(sampling)
        self.model_sampling: FlowSampling = sampling


class FlowModel:
    def __init__(self) -> None:
        self.sampling: FlowSampling = FlowSampling()
        self.inner_model: Inner = Inner(self.sampling)
        self.calls: int = 0

    def __call__(self, x: Any, sigma: Any, **kwargs: object) -> Any:
        self.calls += 1
        level = sigma.reshape(-1, 1, 1, 1).clamp(min=SIGMA_FLOOR)
        return torch.tanh((1.0 - level) * x / level**2)


def fixed_noise_sampler(seed: int) -> Callable[..., Any]:
    generator = torch.Generator().manual_seed(seed)

    def sampler(sigma: Any, sigma_next: Any) -> Any:
        return torch.randn(SHAPE, generator=generator)

    return sampler


def run(function: Callable[..., Any], steps: int, **kwargs: object) -> tuple[Any, int]:
    model = FlowModel()
    sigmas = torch.linspace(1.0, 0.0, steps + 1)
    start = torch.randn(SHAPE, generator=torch.Generator().manual_seed(1))
    result = function(
        model,
        start,
        sigmas,
        extra_args={},
        callback=None,
        disable=True,
        noise_sampler=fixed_noise_sampler(5),
        **kwargs,
    )
    return result, model.calls


@pytest.mark.parametrize("steps", [6, 10, 15])
@pytest.mark.parametrize("signal", ["curvature", "pc_error"])
def test_zero_exponent_matches_sa_solver_bitwise(steps: int, signal: str) -> None:
    reference, reference_calls = run(kds.sample_sa_solver, steps)
    candidate, candidate_calls = run(sample_flow_sde, steps, signal=signal, exponent=0.0)
    assert float((reference - candidate).abs().max()) == 0.0
    assert reference_calls == candidate_calls == steps


@pytest.mark.parametrize("exponent", [-1.0, 1.0])
@pytest.mark.parametrize("signal", ["curvature", "pc_error"])
def test_adaptive_run_costs_one_evaluation_per_step(exponent: float, signal: str) -> None:
    _, calls = run(sample_flow_sde, 12, signal=signal, exponent=exponent)
    assert calls == 12


@pytest.mark.parametrize("exponent", [-1.0, -0.5, 0.5, 1.0])
def test_realised_noise_budget_equals_uniform(exponent: float) -> None:
    uniform_taus: list[float] = []
    adaptive_taus: list[float] = []
    steps = 12
    eta = 1.6

    def record(sink: list[float]) -> Callable[[int, float, float | None], None]:
        def observer(index: int, tau: float, signal: float | None) -> None:
            sink.append(tau)

        return observer

    run(sample_flow_sde, steps, eta=eta, step_observer=record(uniform_taus))
    run(
        sample_flow_sde,
        steps,
        eta=eta,
        exponent=exponent,
        tau_max=100.0,
        step_observer=record(adaptive_taus),
    )

    sampling = FlowSampling()
    sigmas = kds.offset_first_sigma_for_snr(torch.linspace(1.0, 0.0, steps + 1), sampling)
    lambdas = kds.sigma_to_half_log_snr(sigmas, model_sampling=sampling)
    sizes = [float(lambdas[i + 1] - lambdas[i]) for i in range(len(adaptive_taus))]

    uniform_spent = sum(tau**2 * size for tau, size in zip(uniform_taus, sizes))
    adaptive_spent = sum(tau**2 * size for tau, size in zip(adaptive_taus, sizes))
    assert uniform_spent > 0.0
    assert adaptive_spent == pytest.approx(uniform_spent, rel=1e-6)
    assert adaptive_taus != uniform_taus


def test_eta_zero_is_deterministic() -> None:
    first, _ = run(sample_flow_sde, 10, eta=0.0, exponent=1.0)
    second, _ = run(sample_flow_sde, 10, eta=0.0, exponent=-1.0)
    assert float((first - second).abs().max()) == 0.0
