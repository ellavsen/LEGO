#!/usr/bin/env python3
"""Снапшот каталога для Android (Спринт 6): Postgres -> SQLite в assets.

Кладёт Technic-детали, цвета и атрибуты в android/app/src/main/assets/catalog.db.
Схема должна 1:1 совпадать с Room-энтити CatalogDb (см. data/CatalogDb.kt).
    venv/bin/python scripts/export_catalog_snapshot.py
"""
import sqlite3
from pathlib import Path

import psycopg

OUT = (Path(__file__).resolve().parent.parent / "android" / "app" / "src"
       / "main" / "assets" / "catalog.db")


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.unlink(missing_ok=True)
    lite = sqlite3.connect(OUT)
    lite.executescript("""
        CREATE TABLE catalog_part (
            part_num TEXT NOT NULL PRIMARY KEY,
            name TEXT NOT NULL, img_url TEXT);
        CREATE TABLE catalog_color (
            id INTEGER NOT NULL PRIMARY KEY,
            name TEXT NOT NULL, rgb_hex TEXT NOT NULL,
            is_trans INTEGER NOT NULL);
        CREATE TABLE part_attr (
            part_num TEXT NOT NULL PRIMARY KEY,
            type TEXT, hole_count INTEGER, axle_hole_count INTEGER,
            has_axle INTEGER NOT NULL, gear_teeth INTEGER,
            shape TEXT, angle_deg REAL, length_studs REAL);
        CREATE INDEX idx_attr_type ON part_attr(type);
        CREATE INDEX idx_attr_holes ON part_attr(hole_count);
    """)
    with psycopg.connect("dbname=brickindex") as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT p.part_num, p.name,
                   (SELECT img_url FROM part_images i
                    WHERE i.part_num = p.part_num LIMIT 1)
            FROM parts p JOIN part_categories c ON c.id = p.part_cat_id
            WHERE c.name ILIKE 'technic%'""")
        lite.executemany("INSERT INTO catalog_part VALUES (?,?,?)",
                         cur.fetchall())
        cur.execute("SELECT id, name, rgb_hex, is_trans FROM colors WHERE id >= 0")
        lite.executemany("INSERT INTO catalog_color VALUES (?,?,?,?)",
                         [(i, n, h, int(t)) for i, n, h, t in cur.fetchall()])
        cur.execute("""
            SELECT part_num, type, hole_count, axle_hole_count,
                   coalesce(has_axle, false), gear_teeth, shape, angle_deg,
                   length_studs
            FROM part_attributes""")
        lite.executemany("INSERT INTO part_attr VALUES (?,?,?,?,?,?,?,?,?)",
                         [(pn, t, h, ah, int(ha), gt, s, a, ln)
                          for pn, t, h, ah, ha, gt, s, a, ln in cur.fetchall()])
    lite.commit()
    counts = {t: lite.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
              for t in ("catalog_part", "catalog_color", "part_attr")}
    lite.close()
    print(f"{OUT} ({OUT.stat().st_size // 1024} КБ): {counts}")


if __name__ == "__main__":
    main()
