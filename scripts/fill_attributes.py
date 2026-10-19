#!/usr/bin/env python3
"""Наполнение part_attributes для Technic-подмножества (Спринт 5, §10.3).

Источники: имена Rebrickable (name_attrs) + LDraw-геометрия (ldraw_geom).
Правила слияния:
- отверстия: LDraw точнее (beamhole + peghole/2), имя — фолбэк,
  для балок — длина из имени (Beam 1 x 7 -> 7 отверстий);
- крестовые: имя приоритетно, иначе сигналы npeghole/axl?ho*;
- габариты: bbox из LDraw (в стадах), сортированы по убыванию.
Строки с source='curated' не перезаписываются.

    venv/bin/python scripts/fill_attributes.py
"""
import psycopg

from ldraw_geom import analyze
from name_attrs import parse_name

UPSERT = """
INSERT INTO part_attributes (part_num, type, length_studs, width_studs,
    height_studs, hole_count, axle_hole_count, pin_count, stud_count,
    has_axle, has_ball_joint, gear_teeth, shape, angle_deg,
    name_len_a, name_len_b, source, updated_at)
VALUES (%(part_num)s, %(type)s, %(length_studs)s, %(width_studs)s,
    %(height_studs)s, %(hole_count)s, %(axle_hole_count)s, %(pin_count)s,
    %(stud_count)s, %(has_axle)s, %(has_ball_joint)s, %(gear_teeth)s,
    %(shape)s, %(angle_deg)s, %(name_len_a)s, %(name_len_b)s, 'auto', now())
ON CONFLICT (part_num) DO UPDATE SET
    type = EXCLUDED.type, length_studs = EXCLUDED.length_studs,
    width_studs = EXCLUDED.width_studs, height_studs = EXCLUDED.height_studs,
    hole_count = EXCLUDED.hole_count,
    axle_hole_count = EXCLUDED.axle_hole_count,
    pin_count = EXCLUDED.pin_count, stud_count = EXCLUDED.stud_count,
    has_axle = EXCLUDED.has_axle, has_ball_joint = EXCLUDED.has_ball_joint,
    gear_teeth = EXCLUDED.gear_teeth, shape = EXCLUDED.shape,
    angle_deg = EXCLUDED.angle_deg, name_len_a = EXCLUDED.name_len_a,
    name_len_b = EXCLUDED.name_len_b, updated_at = now()
WHERE part_attributes.source != 'curated'
"""


def merge(part_num: str, name: str, category: str) -> dict:
    na = parse_name(name, category)
    geo = analyze(part_num)

    row = {"part_num": part_num, "type": na.get("type"),
           "length_studs": None, "width_studs": None, "height_studs": None,
           "hole_count": None, "axle_hole_count": None, "pin_count": None,
           "stud_count": None, "has_axle": False,
           "has_ball_joint": na.get("has_ball_joint", False),
           "gear_teeth": na.get("gear_teeth"), "shape": na.get("shape"),
           "angle_deg": na.get("angle_deg"),
           "name_len_a": na.get("name_len_a"), "name_len_b": na.get("name_len_b")}

    if geo:
        d = geo["dims_studs"]
        row["length_studs"], row["width_studs"], row["height_studs"] = d[:3]
        row["stud_count"] = geo["stud"] or None
        row["pin_count"] = geo["pin"] or None
        row["has_axle"] = geo["axle_shaft"] > 0

    # крестовые отверстия: имя приоритетно; npeghole НЕ осевой (это вариант
    # пинового, "Peg Hole Negative"), сигнал только axl?ho*-примитивы
    if na.get("axle_hole_count") is not None:
        row["axle_hole_count"] = na["axle_hole_count"]
    elif geo and geo["axlehole_prims"]:
        row["axle_hole_count"] = 1  # сигнал есть, точный счёт ненадёжен

    # пиновые отверстия. Авторы LDraw моделируют их неконсистентно
    # (beamhole/peghole/npeghole), поэтому для балок — правило из имени:
    # прямая 1xN -> N; погнутая AxB -> A+B-1 (минус крестовые на концах)
    a, b = na.get("name_len_a"), na.get("name_len_b")
    if na.get("hole_count") is not None:
        row["hole_count"] = na["hole_count"]          # "[N Pin Holes]"
    elif row["type"] in ("beam", "beam_thin") and a:
        if na.get("shape") == "straight":
            row["hole_count"] = round(a)
        elif b:
            row["hole_count"] = (round(a + b - 1)
                                 - (row["axle_hole_count"] or 0))
    elif geo:
        ldraw_holes = geo["beamhole"] + round(geo["peghole"] / 2)
        row["hole_count"] = ldraw_holes or None

    if row["type"] == "axle":
        row["has_axle"] = True

    return row


def apply_curated(cur) -> int:
    """Точечные ручные поправки: data/attr_curated.csv (part_num,field,value).
    Помечает строку source='curated' — автозаполнение её больше не трогает."""
    import csv
    from pathlib import Path
    path = Path(__file__).resolve().parent.parent / "data" / "attr_curated.csv"
    if not path.exists():
        return 0
    allowed = {"type", "hole_count", "axle_hole_count", "pin_count",
               "stud_count", "has_axle", "has_ball_joint", "gear_teeth",
               "shape", "angle_deg", "length_studs", "width_studs",
               "height_studs"}
    n = 0
    with open(path) as fh:
        for r in csv.DictReader(fh):
            assert r["field"] in allowed, f"поле {r['field']} не разрешено"
            cur.execute(
                f"UPDATE part_attributes SET {r['field']} = %s, "
                f"source = 'curated', updated_at = now() WHERE part_num = %s",
                (r["value"], r["part_num"]))
            n += cur.rowcount
    return n


def main() -> None:
    with psycopg.connect("dbname=brickindex") as conn, conn.cursor() as cur:
        cur.execute("""SELECT p.part_num, p.name, c.name FROM parts p
                       JOIN part_categories c ON c.id = p.part_cat_id
                       WHERE c.name ILIKE 'technic%' ORDER BY p.part_num""")
        parts = cur.fetchall()
        n_geo = 0
        for part_num, name, cat in parts:
            row = merge(part_num, name, cat)
            if row["length_studs"] is not None:
                n_geo += 1
            cur.execute(UPSERT, row)
        n_cur = apply_curated(cur)
        conn.commit()
        cur.execute("SELECT count(*) FROM part_attributes")
        print(f"part_attributes: {cur.fetchone()[0]} строк "
              f"({len(parts)} Technic, {n_geo} с LDraw-геометрией, "
              f"{n_cur} курированных правок)")


if __name__ == "__main__":
    main()
