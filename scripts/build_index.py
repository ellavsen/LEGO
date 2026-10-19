#!/usr/bin/env python3
"""Построение FAISS-индекса из рендеров (Спринт 2, LEGO.md §8.1).

    venv/bin/python scripts/build_index.py [--renders data/renders] [--batch 32]

Кладёт в индекс ВСЕ ракурсы каждой детали (multi-view), сохраняет
data/index/index.faiss + labels.json (part_num на каждый вектор).
"""
import argparse
from pathlib import Path

from PIL import Image

# faiss не импортировать напрямую: torch должен грузиться первым (см. retrieval.py)
from retrieval import MODEL_ID, ROOT, Embedder, new_index, save_index


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--renders", default=str(ROOT / "data" / "renders"))
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--out", default=str(ROOT / "data" / "index"),
                    help="каталог для index.faiss/labels.json")
    ap.add_argument("--parts", help="файл со списком part_num (подмножество)")
    args = ap.parse_args()

    files = sorted(Path(args.renders).glob("*/*.png"))
    if args.parts:
        subset = set(Path(args.parts).read_text().split())
        files = [f for f in files if f.parent.name in subset]
    if not files:
        raise SystemExit(f"нет рендеров в {args.renders}")
    parts = {f.parent.name for f in files}
    print(f"{len(files)} рендеров, {len(parts)} деталей, модель {MODEL_ID}")

    emb = Embedder()
    index, labels = None, []
    for i in range(0, len(files), args.batch):
        chunk = files[i:i + args.batch]
        vecs = emb.embed([Image.open(f) for f in chunk])
        if index is None:
            index = new_index(vecs.shape[1])
        index.add(vecs)
        labels += [f.parent.name for f in chunk]
        print(f"  {min(i + args.batch, len(files))}/{len(files)}")

    save_index(index, labels, emb.model_id, args.out)
    print(f"индекс: {index.ntotal} векторов dim={index.d} -> {args.out}")


if __name__ == "__main__":
    main()
