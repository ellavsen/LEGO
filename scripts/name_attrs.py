"""Регэксп-парсер имён Rebrickable для Technic (Спринт 5, §10.3 источник (а)).

Имена кодируют тип/размеры/форму: "Technic Beam 1 x 7 Thick",
"Technic Brick 1 x 3 [3 Pin Holes]", "Gear 24 Tooth", "Beam 3 x 5 Bent 90".
"""
import re

# углы соединителей Angle Connector #N (номенклатура LEGO)
ANGLE_CONNECTOR_DEG = {1: 0, 2: 180, 3: 157.5, 4: 135, 5: 112.5, 6: 90}

CATEGORY_TYPE = {
    "Technic Beams": "beam", "Technic Beams Special": "beam",
    "Technic Bricks": "brick", "Technic Axles": "axle",
    "Technic Pins": "pin", "Technic Gears": "gear",
    "Technic Connectors": "connector", "Technic Panels": "panel",
    "Technic Bushes": "bush",
}


def _type(name: str, category: str) -> str:
    n = name
    if re.search(r"\bGear\b|\bDifferential\b|\bSprocket\b", n):
        return "gear"
    if re.search(r"\b(Angle|Axle|Pin) Connector\b|\bUniversal Joint\b", n):
        return "connector"
    if re.search(r"\bAxle Pin\b|\bTechnic Pin\b|\bPin (Long|Short|1/2|3/4)\b", n):
        return "pin"
    if re.search(r"\bAxle\s+\d+(\.\d+)?\b|\bAxle \d+L\b", n):
        return "axle"
    if re.search(r"\bBeam\b|\bLiftarm\b", n):
        return "beam_thin" if re.search(r"\bThin\b", n) else "beam"
    if re.search(r"\bBrick\b", n):
        return "brick"
    if re.search(r"\bPanel\b|\bFairing\b", n):
        return "panel"
    if re.search(r"\bBush\b", n):
        return "bush"
    return CATEGORY_TYPE.get(category, "other")


def parse_name(name: str, category: str) -> dict:
    a = {"type": _type(name, category)}

    m = re.search(r"(\d+(?:\.\d+)?)\s*x\s*(\d+(?:\.\d+)?)", name)
    if m:
        a["name_len_a"], a["name_len_b"] = sorted(
            (float(m.group(1)), float(m.group(2))), reverse=True)
    elif a["type"] in ("axle", "pin", "connector"):
        m = re.search(r"\b(?:Axle\s+)?(\d+(?:\.\d+)?)L?\b(?!\s*x)", name)
        if m and a["type"] == "axle":
            a["name_len_a"] = float(m.group(1))

    m = re.search(r"\[(\d+)\s+Pin Holes?\]|\b(\d+)\s+Pin Holes?\b", name)
    if m:
        a["hole_count"] = int(m.group(1) or m.group(2))

    m = re.search(r"(\d+)\s+Tooth", name)
    if m:
        a["gear_teeth"] = int(m.group(1))

    m = re.search(r"Connector(?: Angled)?.*#(\d)", name)
    if m:
        a["axle_hole_count"] = 2
        deg = ANGLE_CONNECTOR_DEG.get(int(m.group(1)))
        if deg is not None:
            a["angle_deg"] = deg
            a["shape"] = "straight" if deg in (0, 180) else "angled"
    elif re.search(r"Axle (and Pin )?Connector|with Axle Hole\b", name):
        a["axle_hole_count"] = 1
    m = re.search(r"with (\d+) Axle Holes", name)
    if m:
        a["axle_hole_count"] = int(m.group(1))

    if re.search(r"Ball Joint|Ball Socket|Tow ?ball|with Ball\b", name):
        a["has_ball_joint"] = True

    if "shape" not in a:
        for pat, shape in [(r"L-Shape", "L"), (r"T-Shape", "T"),
                           (r"H-Shape", "H"), (r"Bent", "bent"),
                           (r"Angled", "angled"), (r"Triangle", "triangle"),
                           (r"Round|Disc|Circle", "round"),
                           (r"Frame", "frame")]:
            if re.search(pat, name):
                a["shape"] = shape
                break
        else:
            if a["type"] in ("beam", "beam_thin", "brick", "axle"):
                a["shape"] = "straight"

    m = re.search(r"Bent\s+(\d+(?:\.\d+)?)", name)
    if m:
        a["angle_deg"] = float(m.group(1))

    return a


if __name__ == "__main__":
    import sys
    import psycopg
    with psycopg.connect("dbname=brickindex") as conn, conn.cursor() as cur:
        for pn in sys.argv[1:]:
            cur.execute("""SELECT p.name, c.name FROM parts p
                           JOIN part_categories c ON c.id = p.part_cat_id
                           WHERE p.part_num = %s""", (pn,))
            row = cur.fetchone()
            print(pn, row[0] if row else "?", "->",
                  parse_name(*row) if row else None)
