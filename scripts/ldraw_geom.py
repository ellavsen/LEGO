"""Парсер LDraw-геометрии (Спринт 5, LEGO.md §10.3, источник (б)).

Рекурсивно обходит .dat (субфайлы s/, примитивы p/), считает:
- bbox по вершинам треугольников/квадов (в LDU; 1 стад = 20 LDU);
- счётчики примитивов-коннекторов (peghole, beamhole, axlehole, ...).

Семантика примитивов откалибрована на деталях с известными свойствами:
- beamhole.dat        = 1 сквозное пиновое отверстие (балки)
- peghole.dat         = 1/2 отверстия (по половинке с каждой стороны)
- npeghole.dat        = 1/2 осевого торца балки (X-отверстие на конце)
- axlehole/axl?hole   = 1/2 крестового отверстия
- axleend/axle.dat    = сегменты осевого стержня (наличие = has_axle)
- stud*.dat           = шипы; confric*/connect* = пины
"""
from functools import lru_cache
from pathlib import Path

import numpy as np

LDRAW = Path(__file__).resolve().parent.parent / "data" / "ldraw"
SEARCH_DIRS = [LDRAW / "parts", LDRAW / "p", LDRAW / "parts" / "s",
               LDRAW / "p" / "48", LDRAW / "models"]
STUD_LDU = 20.0


def _resolve(name: str) -> Path | None:
    name = name.lower().replace("\\", "/")
    for base in SEARCH_DIRS:
        p = base / name
        if p.exists():
            return p
    return None


@lru_cache(maxsize=None)
def _parse(path_str: str):
    """-> (vertices ndarray (n,3) в ЛОКАЛЬНЫХ координатах файла,
          refs: list[(subname, 4x4 matrix)])."""
    verts, refs = [], []
    for raw in Path(path_str).read_text(errors="ignore").splitlines():
        t = raw.split()
        if not t:
            continue
        if t[0] == "1" and len(t) >= 15:
            m = np.eye(4)
            m[:3, 3] = [float(x) for x in t[2:5]]
            m[:3, :3] = np.array([float(x) for x in t[5:14]]).reshape(3, 3)
            refs.append((" ".join(t[14:]), m))
        elif t[0] in ("3", "4"):
            n = 3 if t[0] == "3" else 4
            for i in range(n):
                verts.append([float(x) for x in t[2 + 3 * i:5 + 3 * i]])
    return (np.array(verts).reshape(-1, 3), refs)


# примитивы-коннекторы: считаем при первом вхождении, их внутренности
# (peghole внутри beamhole и т.п.) не учитываем
CONNECTOR_PREFIXES = ("beamhole", "peghole", "npeghol", "axl", "stud",
                      "confric", "connect", "connhole", "bushloc")


def _is_connector(base: str) -> bool:
    return any(base.startswith(p) for p in CONNECTOR_PREFIXES)


def analyze(part_num: str, max_depth: int = 12) -> dict | None:
    """bbox (в стадах, оси отсортированы по убыванию) + счётчики примитивов."""
    root = _resolve(f"{part_num}.dat")
    if root is None:
        return None
    prims: dict[str, float] = {}
    pts: list[np.ndarray] = []

    def walk(path: Path, m: np.ndarray, depth: int, inside_conn: bool):
        verts, refs = _parse(str(path))
        if len(verts):
            hom = np.hstack([verts, np.ones((len(verts), 1))])
            pts.append((hom @ m.T)[:, :3])
        for name, sub_m in refs:
            base = name.lower().replace("\\", "/").split("/")[-1]
            conn = _is_connector(base)
            if conn and not inside_conn:
                prims[base] = prims.get(base, 0) + 1
            sub = _resolve(name)
            if sub is not None and depth < max_depth:
                walk(sub, m @ sub_m, depth + 1, inside_conn or conn)

    walk(root, np.eye(4), 0, False)
    if not pts:
        return None
    allp = np.vstack(pts)
    dims = sorted((allp.max(0) - allp.min(0)) / STUD_LDU, reverse=True)

    def cnt(*prefixes):
        return sum(v for k, v in prims.items()
                   if any(k.startswith(p) for p in prefixes))

    return {
        "dims_studs": [round(float(d), 2) for d in dims],
        "beamhole": cnt("beamhole"),
        "peghole": cnt("peghole"),
        "npeghole": cnt("npeghol"),
        # сегменты крестовых отверстий: axl2hol*, axl3hol* ... (не axleend/axlehol)
        "axlehole_prims": cnt("axl2ho", "axl3ho", "axl4ho", "axl5ho", "axl6ho"),
        "axle_shaft": cnt("axleend", "axl2end", "axl3end", "axl5end",
                          "axlehol2", "axlehol8", "axlehol9", "axleho10"),
        # верхние шипы; stud3*/stud4* — нижние анти-трубки, не считаем
        "stud": cnt("stud.", "stud2", "stud6", "stud10", "stud15", "studp"),
        "pin": cnt("confric", "connect"),
    }


if __name__ == "__main__":
    import sys
    for p in sys.argv[1:]:
        print(p, analyze(p))
