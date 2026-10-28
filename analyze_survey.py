import argparse
import csv
import pathlib

import numpy as np
from scipy import stats

PAIR_COUNT: int = 24
CANONICAL_FIRST: dict[str, str] = {
    "texture_law": "pce_m1",
    "eta_control": "uniform_e14",
    "claim": "pce_m1",
}
KEY_PATH: pathlib.Path = pathlib.Path(__file__).parent / "survey" / "key" / "pairs_key.csv"
RESAMPLES: int = 5000


def load_answers(path: pathlib.Path) -> np.ndarray:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))[1:]
    return np.array([[int(value) for value in row[1:1 + PAIR_COUNT]] for row in rows])


def first_called_ai(answers: np.ndarray, key: list[dict[str, str]]) -> dict[str, np.ndarray]:
    grouped: dict[str, list[np.ndarray]] = {contrast: [] for contrast in CANONICAL_FIRST}
    for column, row in enumerate(key):
        first_is_a = row["variant_a"] == CANONICAL_FIRST[row["contrast"]]
        called = answers[:, column] == (1 if first_is_a else 2)
        grouped[row["contrast"]].append(called.astype(float))
    return {contrast: np.stack(columns, axis=1) for contrast, columns in grouped.items()}


def two_way_bootstrap(matrix: np.ndarray, generator: np.random.Generator) -> tuple[float, float]:
    respondents, items = matrix.shape
    means = np.empty(RESAMPLES)
    for index in range(RESAMPLES):
        rows = generator.integers(0, respondents, respondents)
        columns = generator.integers(0, items, items)
        means[index] = matrix[np.ix_(rows, columns)].mean()
    low, high = np.percentile(means, [2.5, 97.5])
    return float(low), float(high)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("responses", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path)
    arguments = parser.parse_args()

    with KEY_PATH.open(encoding="utf-8", newline="") as handle:
        key = list(csv.DictReader(handle))
    answers = load_answers(arguments.responses)
    respondents = answers.shape[0]
    generator = np.random.default_rng(0)

    print(f"respondents: {respondents}")
    print(f"share of answers choosing image 2: {(answers == 2).mean():.3f} (0.5 means no position bias)")
    print()
    print(f"{'contrast':>12} {'first variant':>13} {'P(first called AI)':>19} {'resp. CI':>17} "
          f"{'resp.+item CI':>17} {'t-test p':>9}")

    rows: list[dict[str, str | float]] = []
    for contrast, matrix in first_called_ai(answers, key).items():
        per_respondent = matrix.mean(axis=1)
        mean = float(per_respondent.mean())
        boot = [
            per_respondent[generator.integers(0, respondents, respondents)].mean()
            for _ in range(RESAMPLES)
        ]
        low, high = np.percentile(boot, [2.5, 97.5])
        two_low, two_high = two_way_bootstrap(matrix, generator)
        p_value = float(stats.ttest_1samp(per_respondent, 0.5).pvalue)
        print(f"{contrast:>12} {CANONICAL_FIRST[contrast]:>13} {mean:19.3f} "
              f"[{low:.3f},{high:.3f}] [{two_low:.3f},{two_high:.3f}] {p_value:9.3f}")
        rows.append(
            {
                "contrast": contrast,
                "first_variant": CANONICAL_FIRST[contrast],
                "respondents": respondents,
                "p_first_called_ai": mean,
                "ci_respondents_low": float(low),
                "ci_respondents_high": float(high),
                "ci_two_way_low": two_low,
                "ci_two_way_high": two_high,
                "t_test_p": p_value,
            }
        )

    print("\nper prompt class (share of answers calling the first variant AI):")
    for contrast, matrix in first_called_ai(answers, key).items():
        prompts = [row["prompt"] for row in key if row["contrast"] == contrast]
        parts = []
        for prompt in sorted(set(prompts)):
            columns = [index for index, value in enumerate(prompts) if value == prompt]
            parts.append(f"{prompt} {matrix[:, columns].mean():.3f}")
        print(f"  {contrast:>12}: " + ", ".join(parts))

    if arguments.output is not None:
        with arguments.output.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)


if __name__ == "__main__":
    main()
