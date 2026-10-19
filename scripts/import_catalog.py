#!/usr/bin/env python3
"""Импорт CSV-дампов Rebrickable в Postgres (Спринт 0, LEGO.md прил. А).

Идемпотентен: повторный запуск делает upsert (ON CONFLICT DO UPDATE),
исчезнувшие из дампа строки НЕ удаляются (решение Спринта 0 — коллекция
пользователя позже будет ссылаться на parts, удаление опасно).

Использование:
    python scripts/import_catalog.py [--download] [--dsn "dbname=brickindex"]
"""
import argparse
import csv
import gzip
import sys
import urllib.request
from pathlib import Path

import psycopg

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
CDN = "https://cdn.rebrickable.com/media/downloads/{}.csv.gz"
DUMPS = ["part_categories", "colors", "parts", "elements",
         "part_relationships", "inventory_parts"]


def download() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for name in DUMPS:
        dest = RAW_DIR / f"{name}.csv.gz"
        print(f"скачиваю {name}.csv.gz ...")
        urllib.request.urlretrieve(CDN.format(name), dest)


def read_csv(name: str):
    with gzip.open(RAW_DIR / f"{name}.csv.gz", "rt", newline="") as fh:
        yield from csv.DictReader(fh)


def nullable(v: str):
    return v if v != "" else None


# (csv-имя, целевая таблица, колонки таблицы, функция строки csv -> кортеж)
TABLES = [
    ("part_categories", "part_categories", ["id", "name"],
     lambda r: (r["id"], r["name"])),
    ("colors", "colors",
     ["id", "name", "rgb_hex", "is_trans", "num_parts", "num_sets",
      "year_from", "year_to"],
     lambda r: (r["id"], r["name"], r["rgb"], r["is_trans"] == "True",
                nullable(r["num_parts"]), nullable(r["num_sets"]),
                nullable(r["y1"]), nullable(r["y2"]))),
    ("parts", "parts", ["part_num", "name", "part_cat_id", "part_material"],
     lambda r: (r["part_num"], r["name"], r["part_cat_id"],
                nullable(r["part_material"]))),
    ("elements", "elements", ["element_id", "part_num", "color_id", "design_id"],
     lambda r: (r["element_id"], r["part_num"], r["color_id"],
                nullable(r["design_id"]))),
    ("part_relationships", "part_relationships",
     ["rel_type", "child_part_num", "parent_part_num"],
     lambda r: (r["rel_type"], r["child_part_num"], r["parent_part_num"])),
]


def upsert(cur: psycopg.Cursor, table: str, cols: list[str], rows) -> int:
    """COPY во временную таблицу, затем upsert в целевую."""
    col_list = ", ".join(cols)
    cur.execute(f"CREATE TEMP TABLE stage (LIKE {table} INCLUDING DEFAULTS) "
                f"ON COMMIT DROP")
    with cur.copy(f"COPY stage ({col_list}) FROM STDIN") as copy:
        n = 0
        for row in rows:
            copy.write_row(row)
            n += 1
    pk = {"part_categories": ["id"], "colors": ["id"], "parts": ["part_num"],
          "elements": ["element_id"],
          "part_relationships": ["rel_type", "child_part_num", "parent_part_num"],
          "part_images": ["part_num", "color_id"]}[table]
    updates = [c for c in cols if c not in pk]
    if updates:
        action = "DO UPDATE SET " + ", ".join(f"{c} = EXCLUDED.{c}" for c in updates)
    else:
        action = "DO NOTHING"
    cur.execute(
        f"INSERT INTO {table} ({col_list}) "
        f"SELECT DISTINCT ON ({', '.join(pk)}) {col_list} FROM stage "
        f"ON CONFLICT ({', '.join(pk)}) {action}")
    cur.execute("DROP TABLE stage")
    cur.execute("INSERT INTO import_log (table_name, row_count) VALUES (%s, %s)",
                (table, n))
    return n


def part_image_rows():
    """Первый непустой img_url на (part_num, color_id) из inventory_parts."""
    seen = {}
    for r in read_csv("inventory_parts"):
        key = (r["part_num"], r["color_id"])
        if r["img_url"] and key not in seen:
            seen[key] = r["img_url"]
    for (part_num, color_id), url in seen.items():
        yield (part_num, color_id, url)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--download", action="store_true",
                    help="сначала скачать свежие дампы с CDN")
    ap.add_argument("--dsn", default="dbname=brickindex")
    args = ap.parse_args()

    if args.download:
        download()

    missing = [n for n in DUMPS if not (RAW_DIR / f"{n}.csv.gz").exists()]
    if missing:
        sys.exit(f"нет файлов {missing} в {RAW_DIR}; запустите с --download")

    schema = (Path(__file__).resolve().parent.parent / "db" / "schema.sql").read_text()
    with psycopg.connect(args.dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(schema)
            for csv_name, table, cols, xform in TABLES:
                n = upsert(cur, table, cols, (xform(r) for r in read_csv(csv_name)))
                print(f"{table}: {n} строк из дампа")
            n = upsert(cur, "part_images", ["part_num", "color_id", "img_url"],
                       part_image_rows())
            print(f"part_images: {n} строк (из inventory_parts)")
        conn.commit()
    print("импорт завершён")


if __name__ == "__main__":
    main()
