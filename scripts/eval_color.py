#!/usr/bin/env python3
"""Тест Спринта 4: точность цвета на фото известных цветов.

Набор: data/val_color/<part_num>__<color_id>.jpg.
Сравнивает точность с ограничением по elements и без (§9).
    venv/bin/python scripts/eval_color.py
"""
from pathlib import Path

from PIL import Image

from color_id import classify_color

VAL = Path(__file__).resolve().parent.parent / "data" / "val_color"


def main() -> None:
    files = sorted(VAL.glob("*__*.jpg"))
    if not files:
        raise SystemExit(f"нет файлов в {VAL}")
    total = ok_r = ok3_r = ok_u = 0
    for f in files:
        part, color = f.stem.rsplit("__", 1)
        truth = int(color)
        img = Image.open(img_path := f)
        restricted = classify_color(img, part_num=part, k=3)
        unrestricted = classify_color(img, part_num=None, k=1)
        if not restricted:
            print(f"  нет маски: {img_path.name}")
            continue
        total += 1
        hit_r = restricted[0]["color_id"] == truth
        ok_r += hit_r
        ok3_r += truth in [c["color_id"] for c in restricted]
        ok_u += unrestricted[0]["color_id"] == truth
        if not hit_r:
            print(f"  MISS {f.name}: ожидался {truth}, "
                  f"получен {restricted[0]['color_id']} "
                  f"({restricted[0]['color_name']}, d={restricted[0]['distance']})")
    print(f"\nфото: {total}")
    print(f"top-1 с ограничением по elements: {ok_r}/{total} = {ok_r / total:.0%}")
    print(f"top-3 с ограничением (UX подтверждения): "
          f"{ok3_r}/{total} = {ok3_r / total:.0%}")
    print(f"top-1 без ограничения (все 200+):  {ok_u}/{total} = {ok_u / total:.0%}")


if __name__ == "__main__":
    main()
