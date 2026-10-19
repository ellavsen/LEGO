#!/usr/bin/env python3
"""Поиск детали по фото через FAISS-индекс (Спринт 2).

    venv/bin/python scripts/search.py photo.jpg [--k 5]
"""
import argparse

from PIL import Image

import psycopg

from retrieval import Embedder, load_index, search


def part_names(part_nums: list[str]) -> dict[str, str]:
    try:
        with psycopg.connect("dbname=brickindex") as conn, conn.cursor() as cur:
            cur.execute("SELECT part_num, name FROM parts WHERE part_num = ANY(%s)",
                        (part_nums,))
            return dict(cur.fetchall())
    except psycopg.OperationalError:
        return {}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("image")
    ap.add_argument("--k", type=int, default=5)
    args = ap.parse_args()

    index, labels, model_id = load_index()
    query = Embedder(model_id).embed([Image.open(args.image)])[0]
    hits = search(index, labels, query, k=args.k)
    names = part_names([h["part_num"] for h in hits])
    for i, h in enumerate(hits, 1):
        print(f"{i}. {h['part_num']:12} score={h['score']:.4f}  "
              f"{names.get(h['part_num'], '')}")


if __name__ == "__main__":
    main()
