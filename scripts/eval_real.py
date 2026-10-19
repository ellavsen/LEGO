#!/usr/bin/env python3
"""Recall@1/@5 идентичности на РЕАЛЬНЫХ фото (LEGO.md §8.5; ПАТЧ К ТЗ, п.3).

Набор: каталог с картинками, имя файла = верный part_num (до расширения).
Рендеры сюда не класть — метрика только по реальным фотографиям.
    venv/bin/python scripts/eval_real.py --val data/val_real
Цели MVP: Recall@5 >= 90%, Recall@1 >= 75% (одиночные чистые детали).
"""
import argparse
from pathlib import Path

from PIL import Image

from retrieval import (Embedder, foreground_aspect, load_dims, load_index,
                       rerank_by_aspect, search)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--val", default="data/val_real")
    ap.add_argument("--verbose", action="store_true", help="печатать промахи")
    ap.add_argument("--agg", default="max",
                    help="max | mean_top3 | vote | all (абляция, патч п.4)")
    ap.add_argument("--index", default="data/index",
                    help="каталог index.faiss/labels.json")
    ap.add_argument("--rerank", type=float, default=0.0, metavar="W",
                    help="вес геометрического re-ranking по пропорциям (0=выкл)")
    args = ap.parse_args()
    modes = ["max", "mean_top3", "vote"] if args.agg == "all" else [args.agg]
    dims_ratio = load_dims() if args.rerank else {}

    files = sorted(p for p in Path(args.val).iterdir()
                   if p.suffix.lower() in (".jpg", ".jpeg", ".png"))
    if not files:
        raise SystemExit(f"нет картинок в {args.val}")

    index, labels, model_id = load_index(args.index)
    emb = Embedder(model_id)
    indexed = set(labels)

    stats = {m: [0, 0] for m in modes}  # mode -> [r1, r5]
    total = 0
    for f in files:
        truth = f.stem
        if truth not in indexed:
            continue  # деталь вне индекса — Recall не определён
        img = Image.open(f)
        query = emb.embed([img])[0]
        aspect = foreground_aspect(img) if args.rerank else None
        total += 1
        for m in modes:
            cands = search(index, labels, query, k=10, agg=m)
            if args.rerank:
                rerank_by_aspect(cands, aspect, dims_ratio, args.rerank)
            hits = [h["part_num"] for h in cands[:5]]
            stats[m][0] += hits[:1] == [truth]
            stats[m][1] += truth in hits
            if args.verbose and m == modes[0] and truth not in hits[:1]:
                mark = "MISS@5" if truth not in hits else "miss@1"
                print(f"  {mark} {truth}: top5={hits}")

    print(f"модель: {model_id}")
    print(f"валидация: {total} фото | деталей в индексе: {len(indexed)}")
    for m in modes:
        r1, r5 = stats[m]
        print(f"agg={m:9}: Recall@1 = {r1 / total:.1%} (цель >= 75%) | "
              f"Recall@5 = {r5 / total:.1%} (цель >= 90%)")


if __name__ == "__main__":
    main()
