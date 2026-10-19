"""Общее ядро retrieval (Спринт 2): эмбеддер DINO + FAISS-индекс.

Эмбеддер по умолчанию — DINOv2-base (DINOv3 gated на HF, фолбэк по LEGO.md
Прил. Б.1). Переключение: env BRICKINDEX_MODEL=facebook/dinov3-vitb16-pretrain-lvd1689m
(требуется HF-токен с принятой лицензией).

Метрика: cosine = inner product на L2-нормированных векторах, IndexFlatIP
(точный поиск, LEGO.md §4.4). В индексе несколько векторов на part_num
(multi-view); агрегация при поиске — max сходства по ракурсам (§8.2).
"""
import json
import os
from pathlib import Path

# torch и faiss-cpu несут каждый свой libomp -> на macOS двойная инициализация
# OpenMP (Error #15 / segfault). Стандартный обход + torch грузим первым.
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import torch  # noqa: E402  (до faiss!)
import faiss  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image
from transformers import AutoImageProcessor, AutoModel

ROOT = Path(__file__).resolve().parent.parent
INDEX_DIR = ROOT / "data" / "index"
MODEL_ID = os.environ.get("BRICKINDEX_MODEL", "facebook/dinov2-base")


class Embedder:
    def __init__(self, model_id: str = MODEL_ID):
        self.model_id = model_id
        self.device = "mps" if torch.backends.mps.is_available() else "cpu"
        self.processor = AutoImageProcessor.from_pretrained(model_id)
        self.model = AutoModel.from_pretrained(model_id).to(self.device).eval()

    @torch.inference_mode()
    def embed(self, images: list[Image.Image]) -> np.ndarray:
        """PIL-картинки -> L2-нормированные эмбеддинги (n, dim) float32."""
        inputs = self.processor(images=[im.convert("RGB") for im in images],
                                return_tensors="pt").to(self.device)
        out = self.model(**inputs)
        vecs = (out.pooler_output if getattr(out, "pooler_output", None) is not None
                else out.last_hidden_state[:, 0])
        vecs = torch.nn.functional.normalize(vecs, dim=-1)
        return vecs.float().cpu().numpy()


def new_index(dim: int) -> faiss.Index:
    return faiss.IndexFlatIP(dim)


def save_index(index: faiss.Index, labels: list[str], model_id: str,
               index_dir: Path | str = INDEX_DIR) -> None:
    index_dir = Path(index_dir)
    index_dir.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(index_dir / "index.faiss"))
    (index_dir / "labels.json").write_text(json.dumps(
        {"model": model_id, "labels": labels}))


def load_index(index_dir: Path | str = INDEX_DIR) -> tuple[faiss.Index, list[str], str]:
    index_dir = Path(index_dir)
    meta = json.loads((index_dir / "labels.json").read_text())
    index = faiss.read_index(str(index_dir / "index.faiss"))
    return index, meta["labels"], meta["model"]


def search(index: faiss.Index, labels: list[str], query: np.ndarray,
           k: int = 5, k_vectors: int = 50, agg: str = "max") -> list[dict]:
    """Топ-k кандидатов part_num, агрегация сходства по ракурсам детали.

    agg: max — лучший ракурс; mean_top3 — среднее 3 лучших ракурсов;
    vote — число ракурсов детали в выдаче (tie-break по max). Абляция —
    ПАТЧ (параллельно Спринту 3), п.4.
    """
    scores, ids = index.search(query.reshape(1, -1), min(k_vectors, index.ntotal))
    sims: dict[str, list[float]] = {}
    for score, idx in zip(scores[0], ids[0]):
        if idx != -1:
            sims.setdefault(labels[idx], []).append(float(score))

    if agg == "max":
        key = lambda s: max(s)  # noqa: E731
    elif agg == "mean_top3":
        key = lambda s: sum(sorted(s, reverse=True)[:3]) / min(len(s), 3)  # noqa: E731
    elif agg == "vote":
        key = lambda s: (len(s), max(s))  # noqa: E731
    else:
        raise ValueError(f"unknown agg: {agg}")

    ranked = sorted(sims.items(), key=lambda kv: key(kv[1]), reverse=True)[:k]
    return [{"part_num": p, "score": round(max(s), 4),
             "votes": len(s) if agg == "vote" else None}
            for p, s in ranked]


def foreground_aspect(image) -> float | None:
    """Соотношение сторон bbox детали на фото (порог от цвета фона)."""
    arr = np.asarray(image.convert("RGB"))
    border = np.concatenate([arr[0], arr[-1], arr[:, 0], arr[:, -1]])
    fg = np.abs(arr.astype(int) - np.median(border, axis=0)).sum(axis=2) > 60
    if fg.mean() < 0.02:
        return None
    ys, xs = np.nonzero(fg)
    w, h = int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)
    return max(w, h) / max(min(w, h), 1)


def load_dims(dsn: str = "dbname=brickindex") -> dict[str, float]:
    """part_num -> длина/ширина (габариты LDraw из part_attributes)."""
    import psycopg
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("""SELECT part_num, length_studs, width_studs
                       FROM part_attributes
                       WHERE length_studs IS NOT NULL AND width_studs > 0""")
        return {p: length / w for p, length, w in cur.fetchall()}


def rerank_by_aspect(hits: list[dict], aspect: float | None,
                     dims_ratio: dict[str, float], weight: float = 0.2) -> None:
    """Геометрический re-ranking (ПАТЧ п.3): штраф за расхождение пропорций
    маски запроса и габаритов кандидата из LDraw. Сортирует hits на месте.
    При agg=vote голоса первичны, геометрия — tie-breaker внутри равных."""
    import math
    if aspect is None:
        return
    for h in hits:
        r = dims_ratio.get(h["part_num"])
        if r:
            h["score"] = round(
                h["score"] - weight * abs(math.log(aspect / r)), 4)
    hits.sort(key=lambda h: (h["votes"] if h.get("votes") is not None else 0,
                             h["score"]), reverse=True)
