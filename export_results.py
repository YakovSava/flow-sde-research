import argparse
import csv
import pathlib
from typing import Any

import numpy as np

from metrics import bootstrap, geometry_error, texture_advantage, texture_energy
from profiles import PROFILES, SAME_BUDGET, Profile
from run_experiment import (
    DEFAULT_BUDGETS,
    FRONTIER,
    VARIANTS,
    load_latent,
    tag_for,
)

COHORTS: dict[str, list[int]] = {
    "main": [42, 1337, 7, 2024],
    "confirm": [31337, 99, 555, 8086],
}
COMFYUI_VERSIONS: dict[str, str] = {"anima": "0.31.1", "flux3": "0.42.5", "moss": "0.42.5", "krea": "0.42.5"}
SAMPLE_FIELDS: list[str] = [
    "model",
    "cohort",
    "comfyui_version",
    "variant",
    "prompt",
    "seed",
    "nfe",
    "geometry",
    "texture",
    "texture_gap",
    "geometry_reference",
]
SUMMARY_FIELDS: list[str] = [
    "model",
    "cohort",
    "comfyui_version",
    "nfe",
    "variant",
    "samples",
    "geometry_mean",
    "texture_mean",
    "texture_gap_mean",
    "frontier_advantage",
    "frontier_ci_low",
    "frontier_ci_high",
]


def geometry_reference_for(profile: Profile, prompt: str, seed: int, steps: int) -> np.ndarray | None:
    reference_steps = steps if profile.geometry_reference == SAME_BUDGET else profile.geometry_steps
    return load_latent(tag_for("ode", prompt, seed, reference_steps), profile)


def sample_rows(profile: Profile, cohort: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    version = COMFYUI_VERSIONS[profile.name]
    for prompt in profile.prompts:
        for seed in COHORTS[cohort]:
            converged = load_latent(tag_for("sa_solver", prompt, seed, profile.texture_steps), profile)
            target = None if converged is None else texture_energy(converged, profile.pool)
            for steps in DEFAULT_BUDGETS:
                reference = geometry_reference_for(profile, prompt, seed, steps)
                for variant in VARIANTS:
                    latent = load_latent(tag_for(variant, prompt, seed, steps), profile)
                    if latent is None:
                        continue
                    energy = texture_energy(latent, profile.pool)
                    rows.append(
                        {
                            "model": profile.name,
                            "cohort": cohort,
                            "comfyui_version": version,
                            "variant": variant,
                            "prompt": prompt,
                            "seed": seed,
                            "nfe": steps,
                            "geometry": "" if reference is None else geometry_error(latent, reference, profile.pool),
                            "texture": energy,
                            "texture_gap": "" if target is None else energy - target,
                            "geometry_reference": profile.geometry_reference,
                        }
                    )
    return rows


def summary_rows(samples: list[dict[str, Any]], profile: Profile, cohort: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    version = COMFYUI_VERSIONS[profile.name]
    mine = [
        row
        for row in samples
        if row["model"] == profile.name and row["cohort"] == cohort and row["geometry"] != ""
    ]
    for steps in DEFAULT_BUDGETS:
        at_budget = [row for row in mine if row["nfe"] == steps]
        counts = {name: sum(row["variant"] == name for row in at_budget) for name in VARIANTS}
        largest = max(counts.values(), default=0)
        variants = [name for name, count in counts.items() if count == largest and count > 0]
        keys = sorted({(row["prompt"], row["seed"]) for row in at_budget})
        complete = [
            key
            for key in keys
            if all(any(r["variant"] == v and (r["prompt"], r["seed"]) == key for r in at_budget) for v in variants)
        ]
        if not complete:
            continue
        index = {(r["variant"], r["prompt"], r["seed"]): r for r in at_budget}
        geometry = {v: np.array([index[(v, *key)]["geometry"] for key in complete]) for v in variants}
        texture = {v: np.array([index[(v, *key)]["texture"] for key in complete]) for v in variants}
        gap = {
            v: np.array([index[(v, *key)]["texture_gap"] for key in complete if index[(v, *key)]["texture_gap"] != ""])
            for v in variants
        }
        frontier_ready = all(name in variants for name in FRONTIER)
        for variant in variants:
            interval = (float("nan"),) * 3
            if frontier_ready and variant not in FRONTIER:
                interval = bootstrap(
                    lambda indices, variant=variant: texture_advantage(
                        geometry, texture, FRONTIER, variant, indices
                    ),
                    len(complete),
                )
            rows.append(
                {
                    "model": profile.name,
                    "cohort": cohort,
                    "comfyui_version": version,
                    "nfe": steps,
                    "variant": variant,
                    "samples": len(complete),
                    "geometry_mean": float(geometry[variant].mean()),
                    "texture_mean": float(texture[variant].mean()),
                    "texture_gap_mean": float(gap[variant].mean()) if gap[variant].size else "",
                    "frontier_advantage": "" if np.isnan(interval[0]) else interval[0],
                    "frontier_ci_low": "" if np.isnan(interval[0]) else interval[1],
                    "frontier_ci_high": "" if np.isnan(interval[0]) else interval[2],
                }
            )
    return rows


def write_csv(path: pathlib.Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=pathlib.Path, default=pathlib.Path(__file__).parent / "results")
    arguments = parser.parse_args()
    arguments.output.mkdir(parents=True, exist_ok=True)

    samples: list[dict[str, Any]] = []
    summary: list[dict[str, Any]] = []
    for profile in PROFILES.values():
        for cohort in COHORTS:
            profile_samples = sample_rows(profile, cohort)
            samples.extend(profile_samples)
            summary.extend(summary_rows(profile_samples, profile, cohort))
            print(f"{profile.name}/{cohort}: {len(profile_samples)} sample rows")

    write_csv(arguments.output / "samples.csv", SAMPLE_FIELDS, samples)
    write_csv(arguments.output / "summary.csv", SUMMARY_FIELDS, summary)
    print(f"{len(samples)} sample rows, {len(summary)} summary rows -> {arguments.output}")


if __name__ == "__main__":
    main()
