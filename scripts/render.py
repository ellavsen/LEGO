#!/usr/bin/env python3
"""Multi-view рендер эталонов одной детали (Спринт 1, LEGO.md прил. А).

Обёртка над headless Blender + аддон ExportLdraw:
    python scripts/render.py --part 32524 --views 24 --out data/renders

Модель ищется как <ldraw>/parts/<part>.dat — для большинства деталей
part_num Rebrickable совпадает с именем LDraw-файла; исключения потребуют
маппинга через API (part_external_ids, см. CLAUDE.md).
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--part", required=True, help="part_num / ldraw_id детали")
    ap.add_argument("--views", type=int, default=24, help="число ракурсов (12–36)")
    ap.add_argument("--out", default=str(ROOT / "data" / "renders"))
    ap.add_argument("--size", type=int, default=512, help="размер кадра, px")
    ap.add_argument("--samples", type=int, default=16, help="сэмплы Cycles")
    ap.add_argument("--ldraw", default=str(ROOT / "data" / "ldraw"))
    args = ap.parse_args()

    dat = Path(args.ldraw) / "parts" / f"{args.part}.dat"
    if not dat.exists():
        sys.exit(f"нет LDraw-модели {dat}; проверьте ldraw_id детали")

    blender = shutil.which("blender") or "/Applications/Blender.app/Contents/MacOS/Blender"
    cmd = [blender, "--background", "--factory-startup",
           "--python", str(ROOT / "scripts" / "blender_render.py"), "--",
           "--dat", str(dat), "--part", args.part, "--ldraw", args.ldraw,
           "--out", args.out, "--views", str(args.views),
           "--size", str(args.size), "--samples", str(args.samples)]
    proc = subprocess.run(cmd, capture_output=True, text=True)

    for line in proc.stdout.splitlines():
        if line.startswith("RENDER "):
            print(line)
    if proc.returncode != 0 or "RENDER DONE" not in proc.stdout:
        print("--- blender stdout (хвост) ---\n" + proc.stdout[-3000:])
        print("--- blender stderr (хвост) ---\n" + proc.stderr[-1500:],
              file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
