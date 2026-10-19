"""Определение цвета детали (Спринт 4, LEGO.md §9).

Пайплайн: маска детали (порог от фона) -> баланс белого по фону
(студийные фото: фон белый/серый = эталон; в мобильном UX роль эталона
играет карточка в кадре) -> медиана RGB внутри маски (края эродируются:
там тени/блики) -> LAB -> ближайший цвет каталога, ОГРАНИЧЕННЫЙ цветами,
в которых деталь реально существует (elements) — §9: это главный буст.
"""
import cv2
import numpy as np
import psycopg
from PIL import Image

_CACHE: dict = {}


def _lab(rgb: np.ndarray) -> np.ndarray:
    """(n,3) uint8 RGB -> (n,3) float32 LAB (OpenCV масштаб)."""
    return cv2.cvtColor(rgb.reshape(-1, 1, 3), cv2.COLOR_RGB2LAB) \
        .reshape(-1, 3).astype(np.float32)


def catalog_colors(dsn: str = "dbname=brickindex") -> dict[int, dict]:
    """color_id -> {name, rgb(np), lab(np), is_trans}; кэшируется."""
    if "colors" not in _CACHE:
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute("SELECT id, name, rgb_hex, is_trans FROM colors "
                        "WHERE id >= 0")
            out = {}
            for cid, name, hx, trans in cur.fetchall():
                rgb = np.array([int(hx[i:i + 2], 16) for i in (0, 2, 4)],
                               dtype=np.uint8)
                out[cid] = {"name": name, "rgb": rgb,
                            "lab": _lab(rgb)[0], "is_trans": trans}
        _CACHE["colors"] = out
    return _CACHE["colors"]


def part_color_ids(part_num: str, dsn: str = "dbname=brickindex") -> list[int]:
    """Цвета, в которых деталь реально выпускалась (elements)."""
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT DISTINCT color_id FROM elements "
                    "WHERE part_num = %s AND color_id >= 0", (part_num,))
        return [r[0] for r in cur.fetchall()]


def dominant_rgb(image: Image.Image) -> np.ndarray | None:
    """Медианный RGB детали после баланса белого по фону."""
    arr = np.asarray(image.convert("RGB"))
    border = np.concatenate([arr[0], arr[-1], arr[:, 0], arr[:, -1]])
    bg = np.median(border, axis=0)

    # баланс белого: фон считаем нейтральным, выравниваем каналы
    scale = bg.mean() / np.maximum(bg, 1)
    balanced = np.clip(arr * scale, 0, 255).astype(np.uint8)

    fg = (np.abs(arr.astype(int) - bg).sum(axis=2) > 60).astype(np.uint8)
    if fg.mean() < 0.01:
        return None
    fg = cv2.erode(fg, np.ones((7, 7), np.uint8))  # края: тени/блики
    if fg.sum() < 50:
        return None
    pix = balanced[fg.astype(bool)]
    # берём освещённую часть детали (50–90 перцентиль светлоты):
    # медиана по всей маске утягивает в тень, топ — в блик
    lum = pix.astype(np.float32).sum(axis=1)
    lo, hi = np.percentile(lum, [50, 90])
    lit = pix[(lum >= lo) & (lum <= hi)]
    if len(lit) < 20:
        lit = pix
    return np.median(lit, axis=0).astype(np.uint8)


def classify_color(image: Image.Image, part_num: str | None = None,
                   k: int = 3) -> list[dict]:
    """Топ-k цветов по LAB-расстоянию; при part_num — только цвета детали."""
    rgb = dominant_rgb(image)
    if rgb is None:
        return []
    lab = _lab(rgb.reshape(1, 3))[0]
    cat = catalog_colors()
    ids = part_color_ids(part_num) if part_num else list(cat)
    ids = [i for i in ids if i in cat] or list(cat)

    def dist(i):  # светлота плавает от освещения — вес L понижен
        d = lab - cat[i]["lab"]
        return float(np.sqrt(0.4 * d[0] ** 2 + d[1] ** 2 + d[2] ** 2))

    ranked = sorted(ids, key=dist)
    return [{"color_id": i, "color_name": cat[i]["name"],
             "distance": round(dist(i), 1),
             "is_trans": cat[i]["is_trans"]} for i in ranked[:k]]
