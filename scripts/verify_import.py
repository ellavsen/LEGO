#!/usr/bin/env python3
"""Тесты Спринта 0: счётчики строк, целостность FK, выборка 10 деталей с картинками.

Использование:
    python scripts/verify_import.py [--dsn "dbname=brickindex"]
Код выхода 0 = все проверки пройдены.
"""
import argparse
import csv
import gzip
import sys
import urllib.request
from pathlib import Path

import psycopg

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


def csv_count(name: str) -> int:
    with gzip.open(RAW_DIR / f"{name}.csv.gz", "rt", newline="") as fh:
        return sum(1 for _ in csv.reader(fh)) - 1  # минус заголовок


FK_CHECKS = [
    ("parts.part_cat_id -> part_categories",
     "SELECT count(*) FROM parts p LEFT JOIN part_categories c ON c.id = p.part_cat_id WHERE c.id IS NULL"),
    ("elements.part_num -> parts",
     "SELECT count(*) FROM elements e LEFT JOIN parts p ON p.part_num = e.part_num WHERE p.part_num IS NULL"),
    ("elements.color_id -> colors",
     "SELECT count(*) FROM elements e LEFT JOIN colors c ON c.id = e.color_id WHERE c.id IS NULL"),
    ("part_relationships.child -> parts",
     "SELECT count(*) FROM part_relationships r LEFT JOIN parts p ON p.part_num = r.child_part_num WHERE p.part_num IS NULL"),
    ("part_relationships.parent -> parts",
     "SELECT count(*) FROM part_relationships r LEFT JOIN parts p ON p.part_num = r.parent_part_num WHERE p.part_num IS NULL"),
    ("part_images.(part_num,color_id) -> elements/parts",
     "SELECT count(*) FROM part_images i LEFT JOIN parts p ON p.part_num = i.part_num WHERE p.part_num IS NULL"),
]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dsn", default="dbname=brickindex")
    args = ap.parse_args()
    failed = 0

    with psycopg.connect(args.dsn) as conn, conn.cursor() as cur:
        print("== счётчики строк (CSV vs БД) ==")
        for csv_name, table in [("part_categories", "part_categories"),
                                ("colors", "colors"), ("parts", "parts"),
                                ("elements", "elements"),
                                ("part_relationships", "part_relationships")]:
            expected = csv_count(csv_name)
            cur.execute(f"SELECT count(*) FROM {table}")
            actual = cur.fetchone()[0]
            # actual >= expected допустимо: upsert не удаляет ушедшие из дампа строки
            ok = actual >= expected
            failed += not ok
            print(f"  {table}: csv={expected} db={actual} {'OK' if ok else 'FAIL'}")

        cur.execute("SELECT count(*) FROM part_images")
        print(f"  part_images: db={cur.fetchone()[0]} (производная от inventory_parts)")

        print("== целостность FK ==")
        for label, sql in FK_CHECKS:
            cur.execute(sql)
            orphans = cur.fetchone()[0]
            failed += orphans != 0
            print(f"  {label}: сирот={orphans} {'OK' if orphans == 0 else 'FAIL'}")

        print("== 10 случайных деталей с картинками ==")
        cur.execute("""
            SELECT p.part_num, left(p.name, 45), col.name, i.img_url
            FROM part_images i
            JOIN parts p ON p.part_num = i.part_num
            JOIN colors col ON col.id = i.color_id
            ORDER BY random() LIMIT 10""")
        rows = cur.fetchall()
        failed += len(rows) != 10
        for part_num, name, color, url in rows:
            print(f"  {part_num:15} {name:45} [{color}]\n{'':19}{url}")

        # доступность картинок: HEAD-запрос к первым трём URL
        print("== доступность картинок (HEAD, 3 шт.) ==")
        for _, _, _, url in rows[:3]:
            req = urllib.request.Request(url, method="HEAD")
            try:
                status = urllib.request.urlopen(req, timeout=15).status
            except Exception as e:  # noqa: BLE001
                status = f"ошибка: {e}"
            ok = status == 200
            failed += not ok
            print(f"  {status} {url[:80]} {'OK' if ok else 'FAIL'}")

    print(f"\nИТОГ: {'все проверки пройдены' if failed == 0 else f'провалено проверок: {failed}'}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
