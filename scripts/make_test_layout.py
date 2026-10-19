#!/usr/bin/env python3
"""Тестовая «раскладка»: композит из N рендеров разных деталей (Спринт 3).

Вырезает деталь из рендера хромакеем по цвету фона (фон рендера однотонный)
и раскладывает по сетке на светло-сером холсте.
    venv/bin/python scripts/make_test_layout.py --n 10 --out data/val_seg/layout10.png
"""
import argparse
import random
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent


def cutout(render: Image.Image) -> Image.Image:
    """RGBA-вырезка детали: прозрачность там, где цвет близок к фоновому."""
    arr = np.asarray(render.convert("RGB")).astype(int)
    bg = arr[2, 2]  # угол — всегда фон
    dist = np.abs(arr - bg).sum(axis=2)
    alpha = np.where(dist > 40, 255, 0).astype(np.uint8)
    rgba = np.dstack([arr.astype(np.uint8), alpha])
    return Image.fromarray(rgba)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--out", default=str(ROOT / "data" / "val_seg" / "layout10.png"))
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    parts = rng.sample(sorted(p.name for p in (ROOT / "data" / "renders").iterdir()
                              if p.is_dir()), args.n)

    # тёмный контрастный фон — требование UX к съёмке (LEGO.md §7 шаг 1)
    canvas = Image.new("RGB", (1536, 1152), (55, 55, 60))
    cols = 4
    cw, ch = canvas.width // cols, canvas.height // -(-args.n // cols)
    for i, part in enumerate(parts):
        view = rng.choice(sorted((ROOT / "data" / "renders" / part).glob("*.png")))
        piece = cutout(Image.open(view))
        piece.thumbnail((cw - 60, ch - 60))
        cx, cy = (i % cols) * cw, (i // cols) * ch
        canvas.paste(piece,
                     (cx + rng.randint(20, cw - piece.width - 20),
                      cy + rng.randint(20, ch - piece.height - 20)),
                     piece)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out)
    print(f"{args.n} деталей -> {out}")
    print("части:", " ".join(parts))


if __name__ == "__main__":
    main()
