import json
import pathlib
from typing import Sequence


def split_runs(lines: Sequence[str]) -> list[list[float]]:
    runs: list[list[float]] = []
    for line in lines:
        if not line.strip():
            continue
        record = json.loads(line)
        if record["i"] == 0:
            runs.append([])
        runs[-1].append(float(record["tau"]))
    return runs


def mean_power_profile(runs: Sequence[Sequence[float]], steps: int) -> list[float]:
    if not runs:
        raise ValueError("no calibration runs")
    totals: list[float] = [0.0] * steps
    for run in runs:
        for index, tau in enumerate(run[:steps]):
            totals[index] += tau * tau
    return [total / len(runs) for total in totals]


def build_profiles(trace_files: dict[int, pathlib.Path]) -> dict[str, list[float]]:
    profiles: dict[str, list[float]] = {}
    for steps, path in sorted(trace_files.items()):
        runs = split_runs(path.read_text(encoding="utf-8").splitlines())
        profiles[str(steps)] = mean_power_profile(runs, steps)
    return profiles


def write_profiles(profiles: dict[str, list[float]], path: pathlib.Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profiles, indent=1), encoding="utf-8")
