"""Сегментация раскладки деталей (Спринт 3, LEGO.md §7 шаг 3).

SAM 3 gated на HF (как DINOv3) -> фолбэк по LEGO.md §4.2: SAM 2.1 base
(свободные веса Ultralytics). Переключение на SAM 3 (текстовый промпт
«lego piece»):  export BRICKINDEX_SAM=sam3.pt  (+ HF-токен с лицензией).

Стратегия: everything-режим SAM на раскладке нестабилен (даёт фрагменты
деталей вместо целых), поэтому детали сначала грубо находятся порогом по
контрастному фону (требование UX, §7 шаг 1) -> связные компоненты -> их
bbox идут в SAM как box-промпты -> точные маски. Если фон выделить не
удалось, фолбэк на everything-режим с постфильтрами.
"""
import os

import numpy as np
from PIL import Image
from scipy import ndimage
from ultralytics.models.sam import SAM2Predictor

SAM_WEIGHTS = os.environ.get("BRICKINDEX_SAM", "sam2.1_b.pt")

# доли площади кадра: больше -> фон/стол, меньше -> шум
MAX_AREA_FRAC = 0.5
MIN_AREA_FRAC = 0.001
CONTAINMENT_THRESHOLD = 0.8  # доля пересечения с уже принятой маской
CROP_PADDING = 8  # px вокруг bbox


def _merge_boxes(boxes: list[list[int]], thresh: float = 0.3) -> list[list[int]]:
    """Сливает боксы, у которых пересечение > thresh от меньшего бокса
    (одна деталь, разорванная порогом на куски, напр. диагональная ось)."""
    merged = True
    while merged:
        merged = False
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                a, b = boxes[i], boxes[j]
                iw = min(a[2], b[2]) - max(a[0], b[0])
                ih = min(a[3], b[3]) - max(a[1], b[1])
                if iw <= 0 or ih <= 0:
                    continue
                min_area = min((a[2] - a[0]) * (a[3] - a[1]),
                               (b[2] - b[0]) * (b[3] - b[1]))
                if iw * ih / min_area > thresh:
                    boxes[i] = [min(a[0], b[0]), min(a[1], b[1]),
                                max(a[2], b[2]), max(a[3], b[3])]
                    boxes.pop(j)
                    merged = True
                    break
            if merged:
                break
    return boxes


class Segmenter:
    def __init__(self, weights: str = SAM_WEIGHTS):
        self.weights = weights
        # предиктор напрямую: параметры everything-режима (points_stride и
        # пороги) через model() не пробрасываются, только через predictor
        self.predictor = SAM2Predictor(overrides=dict(
            task="segment", mode="predict", model=weights,
            save=False, verbose=False))

    @staticmethod
    def _proposal_boxes(arr: np.ndarray) -> list[list[int]]:
        """Грубые bbox деталей: порог от цвета фона + связные компоненты."""
        border = np.concatenate([arr[0], arr[-1], arr[:, 0], arr[:, -1]])
        bg = np.median(border, axis=0)
        fg = np.abs(arr.astype(int) - bg).sum(axis=2) > 60
        fg = ndimage.binary_closing(fg, np.ones((7, 7)))
        fg = ndimage.binary_opening(fg, np.ones((3, 3)))
        labeled, n = ndimage.label(fg)
        frame_area = arr.shape[0] * arr.shape[1]
        boxes = []
        for i in range(1, n + 1):
            m = labeled == i
            if MIN_AREA_FRAC <= m.sum() / frame_area <= MAX_AREA_FRAC:
                ys, xs = np.nonzero(m)
                boxes.append([int(xs.min()), int(ys.min()),
                              int(xs.max()), int(ys.max())])
        return _merge_boxes(boxes)

    def segment(self, image: Image.Image) -> list[dict]:
        """Кропы отдельных деталей: [{bbox, area, crop(PIL)}], крупные первыми."""
        image = image.convert("RGB")
        boxes = self._proposal_boxes(np.asarray(image))
        if boxes:
            result = self.predictor(source=image, bboxes=boxes)[0]
        else:  # фон не выделился (неоднородный) — everything-режим
            result = self.predictor(source=image)[0]
        if result.masks is None:
            return []
        masks = result.masks.data.cpu().numpy().astype(bool)  # (n, H, W)
        frame_area = masks.shape[1] * masks.shape[2]

        # SAM в everything-режиме иногда даёт одну маску на две разнесённые
        # детали — режем каждую маску на связные компоненты
        components = []
        for m in masks:
            labeled, n = ndimage.label(m)
            components += [labeled == i for i in range(1, n + 1)]

        candidates = sorted(
            (m for m in components
             if MIN_AREA_FRAC <= m.sum() / frame_area <= MAX_AREA_FRAC),
            key=lambda m: m.sum(), reverse=True)

        kept: list[np.ndarray] = []
        for m in candidates:
            area = m.sum()
            if any((m & k).sum() / area > CONTAINMENT_THRESHOLD for k in kept):
                continue  # вложенный дубль (отверстие/фрагмент уже принятой)
            kept.append(m)

        items = []
        for m in kept:
            ys, xs = np.nonzero(m)
            x1 = max(int(xs.min()) - CROP_PADDING, 0)
            y1 = max(int(ys.min()) - CROP_PADDING, 0)
            x2 = min(int(xs.max()) + CROP_PADDING, m.shape[1])
            y2 = min(int(ys.max()) + CROP_PADDING, m.shape[0])
            items.append({"bbox": [x1, y1, x2, y2], "area": int(m.sum()),
                          "crop": image.crop((x1, y1, x2, y2))})
        return items
