import functools
import json
import pathlib
from typing import Any, Callable

import comfy.samplers

from .noise_allocation import CURVATURE, SIGNALS
from .sampler import STOCHASTIC_END, STOCHASTIC_START, sample_flow_sde


def trace_writer(path: pathlib.Path) -> Callable[[int, float, float | None], None]:
    def write(index: int, tau: float, signal: float | None) -> None:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"i": index, "tau": tau, "signal": signal}) + "\n")

    return write


def sample_with_profile_file(
    model: Any,
    x: Any,
    sigmas: Any,
    profile_file: str = "",
    trace_file: str = "",
    **options: Any,
) -> Any:
    profile: list[float] | None = None
    if profile_file:
        profiles: dict[str, list[float]] = json.loads(
            pathlib.Path(profile_file).read_text(encoding="utf-8")
        )
        profile = profiles[str(len(sigmas) - 1)]
    if trace_file:
        options["step_observer"] = trace_writer(pathlib.Path(trace_file))
    return sample_flow_sde(model, x, sigmas, profile=profile, **options)


class FlowSDESampler:
    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {
            "required": {
                "eta": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 6.0, "step": 0.05}),
                "stochastic_start": (
                    "FLOAT",
                    {"default": STOCHASTIC_START, "min": 0.0, "max": 1.0, "step": 0.01},
                ),
                "stochastic_end": (
                    "FLOAT",
                    {"default": STOCHASTIC_END, "min": 0.0, "max": 1.0, "step": 0.01},
                ),
                "signal": (SIGNALS, {"default": CURVATURE}),
                "exponent": ("FLOAT", {"default": 0.0, "min": -4.0, "max": 4.0, "step": 0.05}),
                "conserve_budget": ("BOOLEAN", {"default": True}),
                "spread": ("FLOAT", {"default": 3.0, "min": 1.0, "max": 16.0, "step": 0.25}),
                "smoothing": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.05}),
                "tau_max": ("FLOAT", {"default": 4.0, "min": 0.0, "max": 8.0, "step": 0.05}),
                "predictor_order": ("INT", {"default": 3, "min": 1, "max": 6}),
                "corrector_order": ("INT", {"default": 4, "min": 0, "max": 6}),
                "s_noise": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 2.0, "step": 0.01}),
                "simple_order_2": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "profile_file": ("STRING", {"default": ""}),
                "trace_file": ("STRING", {"default": ""}),
            },
        }

    RETURN_TYPES = ("SAMPLER",)
    RETURN_NAMES = ("sampler",)
    FUNCTION = "build"
    CATEGORY = "sampling/custom_sampling/flow_sde"

    def build(
        self,
        eta: float,
        stochastic_start: float,
        stochastic_end: float,
        signal: str,
        exponent: float,
        conserve_budget: bool,
        spread: float,
        smoothing: float,
        tau_max: float,
        predictor_order: int,
        corrector_order: int,
        s_noise: float,
        simple_order_2: bool,
        profile_file: str = "",
        trace_file: str = "",
    ) -> tuple[Any]:
        sampler_function = functools.partial(
            sample_with_profile_file,
            profile_file=profile_file,
            trace_file=trace_file,
            eta=eta,
            stochastic_start=stochastic_start,
            stochastic_end=stochastic_end,
            signal=signal,
            exponent=exponent,
            conserve_budget=conserve_budget,
            spread=spread,
            smoothing=smoothing,
            tau_max=tau_max,
            predictor_order=predictor_order,
            corrector_order=corrector_order,
            s_noise=s_noise,
            simple_order_2=simple_order_2,
        )
        return (comfy.samplers.KSAMPLER(sampler_function),)


NODE_CLASS_MAPPINGS: dict[str, Any] = {
    "FlowSDESampler": FlowSDESampler,
}

NODE_DISPLAY_NAME_MAPPINGS: dict[str, str] = {
    "FlowSDESampler": "Flow-SDE Sampler",
}
