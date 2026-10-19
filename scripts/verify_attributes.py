#!/usr/bin/env python3
"""Тест Спринта 5: сверка part_attributes с ручным эталоном 30 деталей.

    venv/bin/python scripts/verify_attributes.py
Эталон: data/attr_ground_truth.csv (пустая ячейка = поле не проверяется).
"""
import csv
from pathlib import Path

import psycopg

GT = Path(__file__).resolve().parent.parent / "data" / "attr_ground_truth.csv"


def main() -> None:
    checked = mismatches = 0
    with psycopg.connect("dbname=brickindex") as conn, conn.cursor() as cur, \
            open(GT) as fh:
        for gt in csv.DictReader(fh):
            cur.execute("""SELECT type, hole_count, axle_hole_count, has_axle,
                                  gear_teeth, shape, length_studs
                           FROM part_attributes WHERE part_num = %s""",
                        (gt["part_num"],))
            row = cur.fetchone()
            if row is None:
                print(f"  НЕТ СТРОКИ: {gt['part_num']}")
                mismatches += 1
                continue
            typ, holes, axholes, has_axle, teeth, shape, length = row
            actual = {
                "type": typ,
                "hole_count": holes or 0,
                "axle_hole_count": axholes or 0,
                "has_axle": "t" if has_axle else "f",
                "gear_teeth": teeth,
                "shape": shape,
            }
            for field, want in gt.items():
                if field in ("part_num", "len_studs") or want == "":
                    continue
                got = actual[field]
                checked += 1
                if str(got) != want and not (
                        field in ("hole_count", "axle_hole_count", "gear_teeth")
                        and str(got) == want):
                    if str(got) != want:
                        mismatches += 1
                        print(f"  {gt['part_num']:8} {field}: "
                              f"ожидалось {want!r}, получено {got!r}")
            if gt["len_studs"]:
                checked += 1
                if length is None or abs(length - float(gt["len_studs"])) > 0.6:
                    mismatches += 1
                    print(f"  {gt['part_num']:8} len_studs: "
                          f"ожидалось {gt['len_studs']}, получено {length}")

    ok = checked - mismatches
    print(f"\nИТОГ: {ok}/{checked} полей совпало "
          f"({ok / checked:.0%}), расхождений: {mismatches}")


if __name__ == "__main__":
    main()
