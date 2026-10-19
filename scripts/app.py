"""FastAPI-сервер инференса (LEGO.md §6.1): /identify, /segment, /health.

Запуск:
    venv/bin/uvicorn app:app --app-dir scripts --port 8000

    curl -F "file=@photo.jpg" "http://127.0.0.1:8000/identify?k=5"
    curl -F "file=@layout.jpg" http://127.0.0.1:8000/segment
"""
import base64
import io
import json
import time
from contextlib import asynccontextmanager
from pathlib import Path

import psycopg
from fastapi import FastAPI, File, Form, UploadFile
from PIL import Image

CROPS_DIR = Path(__file__).resolve().parent.parent / "data" / "confirm_crops"

from color_id import classify_color
from retrieval import (Embedder, foreground_aspect, load_dims, load_index,
                       rerank_by_aspect, search)
from segmentation import Segmenter

import os

RERANK_WEIGHT = 0.05
# max лучше на полном индексе (623 дет.), vote выигрывал только на 100:
# на большом индексе голосование заливают популярные формы (замеры в CLAUDE.md)
AGG = os.environ.get("BRICKINDEX_AGG", "max")
# цвет «спорный»: top-2 ближе 5 ед. к top-1 или top-1 дальше 25 (LAB)
COLOR_MARGIN, COLOR_MAX_DIST = 5.0, 25.0

state: dict = {}


@asynccontextmanager
async def lifespan(_: FastAPI):
    index, labels, model_id = load_index()
    state.update(index=index, labels=labels, embedder=Embedder(model_id),
                 dims_ratio=load_dims())
    yield


app = FastAPI(title="BrickIndex", lifespan=lifespan)


def enrich(hits: list[dict]) -> None:
    """Имя и картинка кандидата из каталога (если Postgres доступен)."""
    nums = [h["part_num"] for h in hits]
    try:
        with psycopg.connect("dbname=brickindex") as conn, conn.cursor() as cur:
            cur.execute("""
                SELECT p.part_num, p.name,
                       (SELECT img_url FROM part_images i
                        WHERE i.part_num = p.part_num LIMIT 1)
                FROM parts p WHERE p.part_num = ANY(%s)""", (nums,))
            info = {r[0]: r[1:] for r in cur.fetchall()}
    except psycopg.OperationalError:
        info = {}
    for h in hits:
        name, img = info.get(h["part_num"], (None, None))
        h["name"], h["img_url"] = name, img


@app.post("/identify")
async def identify(file: UploadFile = File(...), k: int = 5):
    image = Image.open(io.BytesIO(await file.read()))
    query = state["embedder"].embed([image])[0]
    hits = search(state["index"], state["labels"], query, k=max(k, 10),
                  agg=AGG)
    rerank_by_aspect(hits, foreground_aspect(image), state["dims_ratio"],
                     RERANK_WEIGHT)
    hits = hits[:k]
    enrich(hits)
    for h in hits:  # цвет, ограниченный цветами конкретного кандидата (§9)
        cc = classify_color(image, part_num=h["part_num"], k=3)
        if cc:
            h["color"] = cc[0]
            h["color_alternatives"] = cc[1:]
            h["color_needs_confirmation"] = (
                cc[0]["distance"] > COLOR_MAX_DIST
                or (len(cc) > 1
                    and cc[1]["distance"] - cc[0]["distance"] < COLOR_MARGIN))
    return {"model": state["embedder"].model_id, "candidates": hits}


@app.post("/segment")
async def segment(file: UploadFile = File(...)):
    """Раскладка деталей -> кропы по одной детали (Спринт 3, без ID)."""
    if "segmenter" not in state:  # ленивая загрузка: SAM тяжелее эмбеддера
        state["segmenter"] = Segmenter()
    image = Image.open(io.BytesIO(await file.read()))
    items = state["segmenter"].segment(image)
    out = []
    for it in items:
        buf = io.BytesIO()
        it["crop"].save(buf, format="PNG")
        out.append({"bbox": it["bbox"], "area": it["area"],
                    "crop_png_base64": base64.b64encode(buf.getvalue()).decode()})
    return {"model": state["segmenter"].weights, "count": len(out), "items": out}


@app.post("/confirm")
async def confirm(file: UploadFile = File(...),
                  candidates: str = Form(...),      # JSON top-K [{part_num, score}]
                  chosen_part_num: str = Form(...),
                  chosen_color_id: int | None = Form(None),
                  user_id: int = Form(1)):
    """Подтверждение кандидата пользователем: кроп -> диск, строка ->
    confirmations (накопительный few-shot-набор, ПАТЧ К ТЗ п.2)."""
    CROPS_DIR.mkdir(parents=True, exist_ok=True)
    cand = json.loads(candidates)
    crop_ref = str(CROPS_DIR / f"{int(time.time() * 1000)}_{chosen_part_num}.jpg")
    Image.open(io.BytesIO(await file.read())).convert("RGB").save(crop_ref)
    was_top1 = bool(cand) and cand[0].get("part_num") == chosen_part_num
    with psycopg.connect("dbname=brickindex") as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO confirmations (user_id, crop_ref, candidates,
                   chosen_part_num, chosen_color_id, was_top1)
               VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
            (user_id, crop_ref, json.dumps(cand), chosen_part_num,
             chosen_color_id, was_top1))
        cid = cur.fetchone()[0]
        conn.commit()
    return {"id": cid, "was_top1": was_top1}


@app.get("/health")
async def health():
    return {"status": "ok", "vectors": state["index"].ntotal,
            "model": state["embedder"].model_id}
