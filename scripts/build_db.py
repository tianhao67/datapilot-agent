# -*- coding: utf-8 -*-
"""Build a deterministic demo SQLite database for DataPilot."""
from __future__ import annotations

import argparse
import datetime as dt
import random
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "shop.db"
SCHEMA = ROOT / "data" / "schema.sql"

CITIES = ["南京", "苏州", "上海", "杭州", "广州", "深圳", "北京", "成都"]
CITY_WEIGHTS = [18, 14, 16, 14, 12, 10, 9, 7]
LEVELS = ["普通", "银卡", "金卡", "黑卡"]
LEVEL_WEIGHTS = [55, 27, 14, 4]
CATEGORIES = {
    "数码": ["降噪耳机", "机械键盘", "便携投影", "智能手表", "移动电源", "蓝牙音箱"],
    "家电": ["空气炸锅", "扫地机器人", "电饭煲", "吹风机", "净水器", "取暖器"],
    "服饰": ["冲锋衣", "羊毛大衣", "运动鞋", "牛仔裤", "卫衣", "羽绒服"],
    "美妆": ["精华液", "面霜", "口红", "防晒霜", "面膜", "香水"],
    "食品": ["坚果礼盒", "咖啡豆", "牛肉干", "茶叶", "巧克力", "自热火锅"],
}
PRICE_RANGE = {
    "数码": (199, 2999),
    "家电": (299, 3999),
    "服饰": (129, 1299),
    "美妆": (79, 899),
    "食品": (29, 399),
}
CHANNELS = ["App", "小程序", "Web"]
STATUSES = ["已支付", "已退款", "待支付", "已取消"]
STATUS_WEIGHTS = [82, 8, 7, 3]


def _date(rng: random.Random, start: dt.date, end: dt.date) -> str:
    days = (end - start).days
    return (start + dt.timedelta(days=rng.randint(0, days))).isoformat()


def build(path: Path = DEFAULT_DB, seed: int = 20261101) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    rng = random.Random(seed)
    conn = sqlite3.connect(path)
    try:
        conn.executescript(SCHEMA.read_text(encoding="utf-8"))

        customers = []
        for cid in range(1, 161):
            customers.append(
                (
                    cid,
                    f"客户{cid:03d}",
                    rng.choices(CITIES, weights=CITY_WEIGHTS, k=1)[0],
                    rng.choices(LEVELS, weights=LEVEL_WEIGHTS, k=1)[0],
                    _date(rng, dt.date(2024, 1, 1), dt.date(2026, 10, 31)),
                )
            )
        conn.executemany("INSERT INTO customers VALUES (?,?,?,?,?)", customers)

        products = []
        pid = 1
        for category, names in CATEGORIES.items():
            lo, hi = PRICE_RANGE[category]
            for name in names:
                price = round(rng.uniform(lo, hi), 2)
                cost = round(price * rng.uniform(0.45, 0.75), 2)
                status = "下架" if rng.random() < 0.08 else "在售"
                products.append((pid, f"{category}-{name}", category, price, cost, status))
                pid += 1
        conn.executemany("INSERT INTO products VALUES (?,?,?,?,?,?)", products)

        orders = []
        order_items = []
        item_id = 1
        for oid in range(1, 901):
            odate = _date(rng, dt.date(2026, 1, 1), dt.date(2026, 10, 31))
            status = rng.choices(STATUSES, weights=STATUS_WEIGHTS, k=1)[0]
            orders.append((oid, rng.randint(1, 160), odate, status, rng.choice(CHANNELS)))
            for _ in range(rng.randint(1, 4)):
                product = rng.choice(products)
                qty = rng.randint(1, 3)
                unit_price = round(product[3] * rng.uniform(0.9, 1.0), 2)
                discount = rng.choice([1.0, 0.95, 0.9, 0.85])
                order_items.append((item_id, oid, product[0], qty, unit_price, discount))
                item_id += 1
        conn.executemany("INSERT INTO orders VALUES (?,?,?,?,?)", orders)
        conn.executemany("INSERT INTO order_items VALUES (?,?,?,?,?,?)", order_items)
        conn.commit()
    finally:
        conn.close()
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the DataPilot demo database")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--seed", type=int, default=20261101)
    args = parser.parse_args()
    path = build(args.db, args.seed)
    print(f"built {path}")


if __name__ == "__main__":
    main()
