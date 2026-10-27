import argparse
import csv
import pathlib
import random
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont

from profiles import FLUX3

SOURCE: pathlib.Path = pathlib.Path("D:/ComfyUI/output") / FLUX3.subdir
NFE: int = 15
PROMPTS: list[str] = ["face", "fur"]
SEEDS: list[int] = [42, 1337, 7, 2024]
ORDER_SEED: int = 20261027
GAP: int = 32
LABEL_HEIGHT: int = 72
CONTRASTS: dict[str, tuple[str, str]] = {
    "texture_law": ("pce_m1", "pce_p1"),
    "eta_control": ("uniform_e14", "uniform_e20"),
    "claim": ("pce_m1", "uniform_e17"),
}
SINGLE_CONTRASTS: list[str] = ["texture_law", "eta_control"]


@dataclass(frozen=True)
class Item:
    prompt: str
    seed: int


def items() -> list[Item]:
    return [Item(prompt, seed) for prompt in PROMPTS for seed in SEEDS]


def source_path(variant: str, item: Item) -> pathlib.Path:
    tag = f"{variant}_{item.prompt}_s{item.seed}_n{NFE:03d}"
    matches = sorted(SOURCE.glob(f"{tag}_[0-9][0-9][0-9][0-9][0-9]_.png"))
    if not matches:
        raise FileNotFoundError(tag)
    return matches[-1]


def load(variant: str, item: Item) -> Image.Image:
    return Image.open(source_path(variant, item)).convert("RGB")


def label_font() -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype("arial.ttf", 48)
    except OSError:
        return ImageFont.load_default()


def compose_pair(left: Image.Image, right: Image.Image) -> Image.Image:
    width, height = left.size
    sheet = Image.new("RGB", (width * 2 + GAP, height + LABEL_HEIGHT), "white")
    sheet.paste(left, (0, LABEL_HEIGHT))
    sheet.paste(right, (width + GAP, LABEL_HEIGHT))
    draw = ImageDraw.Draw(sheet)
    font = label_font()
    for offset, letter in ((0, "A"), (width + GAP, "B")):
        draw.text((offset + width // 2 - 14, 8), letter, fill="black", font=font)
    return sheet


def build_pairs(output: pathlib.Path, generator: random.Random) -> list[dict[str, str]]:
    plan: list[tuple[str, Item, bool]] = []
    for contrast in CONTRASTS:
        flags = [index % 2 == 0 for index in range(len(items()))]
        generator.shuffle(flags)
        plan.extend((contrast, item, flag) for item, flag in zip(items(), flags))
    generator.shuffle(plan)

    folder = output / "pairs"
    folder.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, str]] = []
    for position, (contrast, item, first_left) in enumerate(plan, start=1):
        first, second = CONTRASTS[contrast]
        left_variant, right_variant = (first, second) if first_left else (second, first)
        name = f"pair_{position:02d}.png"
        compose_pair(load(left_variant, item), load(right_variant, item)).save(folder / name)
        rows.append(
            {
                "file": name,
                "contrast": contrast,
                "prompt": item.prompt,
                "seed": str(item.seed),
                "nfe": str(NFE),
                "variant_a": left_variant,
                "variant_b": right_variant,
            }
        )
    return rows


def build_singles(output: pathlib.Path, generator: random.Random) -> list[dict[str, str]]:
    slots: list[tuple[str, Item]] = [
        (contrast, item) for contrast in SINGLE_CONTRASTS for item in items()
    ]
    generator.shuffle(slots)

    rows: list[dict[str, str]] = []
    counters: dict[str, int] = {contrast: 0 for contrast in SINGLE_CONTRASTS}
    for position, (contrast, item) in enumerate(slots, start=1):
        first, second = CONTRASTS[contrast]
        index = counters[contrast]
        counters[contrast] += 1
        for form in (1, 2):
            variant = first if (index + form) % 2 == 0 else second
            folder = output / "singles" / f"form_{form}"
            folder.mkdir(parents=True, exist_ok=True)
            name = f"single_{position:02d}.png"
            load(variant, item).save(folder / name)
            rows.append(
                {
                    "form": str(form),
                    "file": name,
                    "contrast": contrast,
                    "prompt": item.prompt,
                    "seed": str(item.seed),
                    "nfe": str(NFE),
                    "variant": variant,
                }
            )
    return rows


def write_csv(path: pathlib.Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=pathlib.Path, default=pathlib.Path(__file__).parent / "survey")
    arguments = parser.parse_args()

    generator = random.Random(ORDER_SEED)
    pairs = build_pairs(arguments.output, generator)
    singles = build_singles(arguments.output, generator)
    write_csv(arguments.output / "key" / "pairs_key.csv", pairs)
    write_csv(arguments.output / "key" / "singles_key.csv", singles)
    print(f"{len(pairs)} pair images, {len(singles)} single images -> {arguments.output}")


if __name__ == "__main__":
    main()
