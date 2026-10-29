import argparse
import json
import pathlib
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from safetensors import safe_open

from metrics import bootstrap, geometry_error, texture_advantage, texture_energy
from profiles import (
    LATENT_REF,
    MODEL_REF,
    NEGATIVE_REF,
    NODE_BUILDERS,
    POSITIVE_REF,
    PROFILES,
    VAE_REF,
    SAME_BUDGET,
    Profile,
)
from static_profile import build_profiles, write_profiles

SERVER: str = "http://127.0.0.1:8188"
OUTPUT: pathlib.Path = pathlib.Path("D:/ComfyUI/output")

DEFAULT_SEEDS: list[int] = [42, 1337, 7, 2024, 31337, 99, 555, 8086]
DEFAULT_BUDGETS: list[int] = [6, 8, 10, 12, 15]
ETA: float = 1.7
FRONTIER: list[str] = ["uniform_e14", "uniform_e17", "uniform_e20"]


@dataclass(frozen=True)
class Variant:
    sampler_name: str | None = None
    settings: dict[str, Any] = field(default_factory=dict)
    uses_profile: bool = False
    traced: bool = False


def flow_sde(**settings: Any) -> Variant:
    return Variant(settings=settings)


VARIANTS: dict[str, Variant] = {
    "ode": Variant(sampler_name="euler"),
    "sa_solver": Variant(sampler_name="sa_solver"),
    "uniform_e10": flow_sde(eta=1.0),
    "uniform_e14": flow_sde(eta=1.4),
    "uniform_e17": flow_sde(eta=ETA),
    "uniform_e20": flow_sde(eta=2.0),
    "curv_p1": flow_sde(eta=ETA, signal="curvature", exponent=1.0),
    "curv_m1": flow_sde(eta=ETA, signal="curvature", exponent=-1.0),
    "pce_p1": flow_sde(eta=ETA, signal="pc_error", exponent=1.0),
    "pce_m1": flow_sde(eta=ETA, signal="pc_error", exponent=-1.0),
    "static_pce": Variant(
        settings={"eta": ETA, "signal": "pc_error", "exponent": 0.0},
        uses_profile=True,
    ),
}

CALIBRATION_VARIANT: str = "cal_pce_m1"
CALIBRATION_SEEDS: list[int] = [101, 102, 103, 104]
TRACE_DIR: pathlib.Path = OUTPUT / "flow_sde_traces"
PROFILE_DIR: pathlib.Path = pathlib.Path(__file__).parent / "results"
HIDDEN_VARIANTS: dict[str, Variant] = {
    CALIBRATION_VARIANT: Variant(
        settings={"eta": ETA, "signal": "pc_error", "exponent": -1.0},
        traced=True,
    ),
}


def trace_path(profile: Profile, steps: int) -> pathlib.Path:
    return TRACE_DIR / f"{profile.name}_n{steps:03d}.jsonl"


def profile_path(profile: Profile) -> pathlib.Path:
    return PROFILE_DIR / f"static_profile_{profile.name}.json"

FLOW_SDE_DEFAULTS: dict[str, Any] = {
    "eta": 1.0,
    "stochastic_start": 0.2,
    "stochastic_end": 0.8,
    "signal": "curvature",
    "exponent": 0.0,
    "conserve_budget": True,
    "spread": 3.0,
    "smoothing": 0.5,
    "tau_max": 4.0,
    "predictor_order": 3,
    "corrector_order": 4,
    "s_noise": 1.0,
    "simple_order_2": False,
}


@dataclass(frozen=True)
class Job:
    tag: str
    prompt: str
    seed: int
    steps: int
    variant: str


def request(path: str, payload: dict[str, Any] | None = None) -> Any:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {} if data is None else {"Content-Type": "application/json"}
    with urllib.request.urlopen(
        urllib.request.Request(f"{SERVER}{path}", data=data, headers=headers)
    ) as response:
        return json.loads(response.read())


def build_graph(job: Job, profile: Profile) -> dict[str, Any]:
    variant = {**VARIANTS, **HIDDEN_VARIANTS}[job.variant]
    if variant.sampler_name is not None:
        sampler = {
            "class_type": "KSamplerSelect",
            "inputs": {"sampler_name": variant.sampler_name},
        }
    else:
        inputs = {**FLOW_SDE_DEFAULTS, **variant.settings}
        if variant.uses_profile:
            inputs["profile_file"] = str(profile_path(profile))
        if variant.traced:
            inputs["trace_file"] = str(trace_path(profile, job.steps))
        sampler = {"class_type": "FlowSDESampler", "inputs": inputs}
    graph = NODE_BUILDERS[profile.name](profile, profile.prompts[job.prompt])
    graph.update(
        {
            "51": {
                "class_type": "BasicScheduler",
                "inputs": {
                    "scheduler": profile.scheduler,
                    "steps": job.steps,
                    "denoise": 1,
                    "model": MODEL_REF,
                },
            },
            "52": sampler,
            "54": {
                "class_type": "SamplerCustom",
                "inputs": {
                    "add_noise": True,
                    "noise_seed": job.seed,
                    "cfg": profile.cfg,
                    "model": MODEL_REF,
                    "positive": POSITIVE_REF,
                    "negative": NEGATIVE_REF,
                    "sampler": ["52", 0],
                    "sigmas": ["51", 0],
                    "latent_image": LATENT_REF,
                },
            },
            "27": {"class_type": "VAEDecode", "inputs": {"samples": ["54", 0], "vae": VAE_REF}},
            "12": {
                "class_type": "SaveImage",
                "inputs": {"filename_prefix": f"{profile.subdir}/{job.tag}", "images": ["27", 0]},
            },
            "13": {
                "class_type": "SaveLatent",
                "inputs": {"filename_prefix": f"{profile.subdir}/{job.tag}", "samples": ["54", 0]},
            },
        }
    )
    return graph


def latent_path(tag: str, profile: Profile) -> pathlib.Path | None:
    matches = sorted((OUTPUT / profile.subdir).glob(f"{tag}_[0-9][0-9][0-9][0-9][0-9]_.latent"))
    return matches[-1] if matches else None


def load_latent(tag: str, profile: Profile) -> np.ndarray | None:
    path = latent_path(tag, profile)
    if path is None:
        return None
    with safe_open(str(path), "pt") as handle:
        return handle.get_tensor("latent_tensor").numpy().astype(np.float64)


def wait_for(prompt_id: str, timeout: float = 3600.0) -> str | None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        history = request(f"/history/{prompt_id}")
        if prompt_id in history:
            status = history[prompt_id].get("status", {})
            if status.get("status_str") == "error":
                return json.dumps(status.get("messages", [])[-1:])[:400]
            return None
        time.sleep(0.5)
    return "timeout"


def tag_for(variant: str, prompt: str, seed: int, steps: int) -> str:
    return f"{variant}_{prompt}_s{seed}_n{steps:03d}"


def plan_jobs(
    profile: Profile,
    prompts: list[str],
    seeds: list[int],
    budgets: list[int],
    variants: list[str],
) -> list[Job]:
    same_budget = profile.geometry_reference == SAME_BUDGET
    jobs: list[Job] = []
    for prompt in prompts:
        for seed in seeds:
            if not same_budget:
                jobs.append(
                    Job(
                        tag_for("ode", prompt, seed, profile.geometry_steps),
                        prompt,
                        seed,
                        profile.geometry_steps,
                        "ode",
                    )
                )
            jobs.append(
                Job(
                    tag_for("sa_solver", prompt, seed, profile.texture_steps),
                    prompt,
                    seed,
                    profile.texture_steps,
                    "sa_solver",
                )
            )
            for steps in budgets:
                needed = variants if "ode" in variants or not same_budget else ["ode"] + variants
                for variant in needed:
                    jobs.append(Job(tag_for(variant, prompt, seed, steps), prompt, seed, steps, variant))
    return jobs


def run_jobs(jobs: list[Job], profile: Profile) -> None:
    pending = [job for job in jobs if latent_path(job.tag, profile) is None]
    print(f"{len(jobs)} jobs, {len(pending)} to run")
    started = time.time()
    for position, job in enumerate(pending, start=1):
        began = time.time()
        try:
            prompt_id = request("/prompt", {"prompt": build_graph(job, profile)})["prompt_id"]
        except urllib.error.HTTPError as error:
            print(f"  [{position}/{len(pending)}] {job.tag}: rejected {error.read()[:300]!r}")
            continue
        failure = wait_for(prompt_id)
        status = "FAILED " + failure if failure else f"{time.time() - began:.1f}s"
        print(f"  [{position}/{len(pending)}] {job.tag}: {status}", flush=True)
    print(f"sampling done in {(time.time() - started) / 60:.1f} min\n")


def collect(
    profile: Profile,
    prompts: list[str],
    seeds: list[int],
    steps: int,
    variants: list[str],
) -> dict[str, dict[str, np.ndarray]]:
    geometry: dict[str, list[float]] = {name: [] for name in variants}
    texture: dict[str, list[float]] = {name: [] for name in variants}
    gap: dict[str, list[float]] = {name: [] for name in variants}
    for prompt in prompts:
        for seed in seeds:
            same_budget = profile.geometry_reference == SAME_BUDGET
            reference_steps = steps if same_budget else profile.geometry_steps
            reference = load_latent(tag_for("ode", prompt, seed, reference_steps), profile)
            converged = load_latent(tag_for("sa_solver", prompt, seed, profile.texture_steps), profile)
            latents = {name: load_latent(tag_for(name, prompt, seed, steps), profile) for name in variants}
            if reference is None or converged is None or any(v is None for v in latents.values()):
                continue
            target = texture_energy(converged, profile.pool)
            for name, latent in latents.items():
                geometry[name].append(geometry_error(latent, reference, profile.pool))
                energy = texture_energy(latent, profile.pool)
                texture[name].append(energy)
                gap[name].append(energy - target)
    return {
        "geometry": {name: np.array(values) for name, values in geometry.items()},
        "texture": {name: np.array(values) for name, values in texture.items()},
        "gap": {name: np.array(values) for name, values in gap.items()},
    }


def format_interval(point: float, low: float, high: float) -> str:
    if np.isnan(point):
        return "n/a"
    return f"{point:+.4f} [{low:+.4f}, {high:+.4f}]"


def report(
    profile: Profile,
    prompts: list[str],
    seeds: list[int],
    budgets: list[int],
    variants: list[str],
) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for steps in budgets:
        data = collect(profile, prompts, seeds, steps, variants)
        count = min(len(values) for values in data["geometry"].values())
        if count == 0:
            continue
        geometry, texture, gap = data["geometry"], data["texture"], data["gap"]
        print(f"nfe={steps}  samples={count}")
        print(f"{'variant':>13} | {'geometry':>8} | {'texture':>8} | {'gap':>8} | "
              f"{'texture vs uniform frontier (95% CI)':>40}")
        print("-" * 92)
        frontier_ready = all(name in variants for name in FRONTIER)
        summary[str(steps)] = {}
        for name in variants:
            advantage = "n/a"
            interval = (float("nan"),) * 3
            if frontier_ready and name not in FRONTIER:
                interval = bootstrap(
                    lambda indices, name=name: texture_advantage(
                        geometry, texture, FRONTIER, name, indices
                    ),
                    count,
                )
                advantage = format_interval(*interval)
            print(f"{name:>13} | {geometry[name].mean():8.4f} | {texture[name].mean():8.4f} | "
                  f"{gap[name].mean():+8.4f} | {advantage:>40}")
            summary[str(steps)][name] = {
                "geometry": geometry[name].tolist(),
                "texture": texture[name].tolist(),
                "gap": gap[name].tolist(),
                "frontier_advantage": list(interval),
            }
        print()
    return summary


def calibrate(profile: Profile, prompts: list[str], budgets: list[int]) -> None:
    TRACE_DIR.mkdir(parents=True, exist_ok=True)
    jobs = [
        Job(tag_for(CALIBRATION_VARIANT, prompt, seed, steps), prompt, seed, steps, CALIBRATION_VARIANT)
        for prompt in prompts
        for seed in CALIBRATION_SEEDS
        for steps in budgets
    ]
    pending = [job for job in jobs if latent_path(job.tag, profile) is None]
    for steps in budgets:
        if any(job.steps == steps for job in pending):
            trace_path(profile, steps).unlink(missing_ok=True)
    run_jobs(jobs, profile)
    profiles = build_profiles({steps: trace_path(profile, steps) for steps in budgets})
    write_profiles(profiles, profile_path(profile))
    print(f"wrote {profile_path(profile)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="anima", choices=list(PROFILES))
    parser.add_argument("--prompts", nargs="+", default=None)
    parser.add_argument("--seeds", nargs="+", type=int, default=DEFAULT_SEEDS)
    parser.add_argument("--budgets", nargs="+", type=int, default=DEFAULT_BUDGETS)
    parser.add_argument("--variants", nargs="+", default=list(VARIANTS), choices=list(VARIANTS))
    parser.add_argument("--analyse-only", action="store_true")
    parser.add_argument("--calibrate", action="store_true")
    parser.add_argument("--report", type=pathlib.Path)
    arguments = parser.parse_args()

    profile = PROFILES[arguments.model]
    prompts = arguments.prompts or list(profile.prompts)

    if arguments.calibrate:
        calibrate(profile, prompts, arguments.budgets)
        return

    if not arguments.analyse_only:
        run_jobs(plan_jobs(profile, prompts, arguments.seeds, arguments.budgets, arguments.variants), profile)

    summary = report(profile, prompts, arguments.seeds, arguments.budgets, arguments.variants)
    if arguments.report is not None:
        arguments.report.write_text(json.dumps(summary), encoding="utf-8")


if __name__ == "__main__":
    main()
