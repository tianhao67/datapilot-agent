# -*- coding: utf-8 -*-
"""Read-only SQLite access, schema introspection and query execution."""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import config
from .guard import ALLOWED_TABLES, SQLGuardError, apply_limit, validate_sql

TABLE_NOTES = {
    "customers": "客户表",
    "products": "商品表",
    "orders": "订单表（一个订单可包含多个商品）",
    "order_items": "订单明细表（一行 = 一个订单里的一个商品）",
}

COLUMN_NOTES = {
    "customer_id": "客户 ID，主键",
    "customer_name": "客户名称",
    "city": "所在城市",
    "level": "客户等级：普通 / 银卡 / 金卡 / 黑卡",
    "register_date": "注册日期 YYYY-MM-DD",
    "product_id": "商品 ID，主键",
    "product_name": "商品名称",
    "category": "商品品类：数码 / 家电 / 服饰 / 美妆 / 食品",
    "price": "商品标价（元）",
    "cost": "商品成本（元）",
    "status": "商品状态（在售 / 下架）；orders.status 为订单状态（已支付 / 已退款 / 待支付 / 已取消）",
    "order_id": "订单 ID，主键",
    "order_date": "下单日期 YYYY-MM-DD",
    "channel": "下单渠道：App / 小程序 / Web",
    "item_id": "明细 ID，主键",
    "quantity": "购买数量",
    "unit_price": "成交单价（元）",
    "discount": "折扣系数，0.9 表示 9 折",
}

CATEGORICAL_COLUMNS = {
    "customers": ["city", "level"],
    "products": ["category", "status"],
    "orders": ["status", "channel"],
}


class QueryError(RuntimeError):
    """A SQL statement failed to execute (syntax, timeout, sandbox denial...)."""


@dataclass
class QueryResult:
    columns: list[str] = field(default_factory=list)
    rows: list[tuple] = field(default_factory=list)
    elapsed_ms: float = 0.0
    truncated: bool = False


def connect(path: Path | str | None = None, readonly: bool = True) -> sqlite3.Connection:
    db_path = Path(path or config.DB_PATH)
    if not db_path.exists():
        raise FileNotFoundError(f"数据库不存在：{db_path}（先运行 python scripts/build_db.py）")
    if readonly:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
    else:
        conn = sqlite3.connect(str(db_path), timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def _authorizer(action, arg1, arg2, dbname, source):  # noqa: ANN001
    if action in (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_RECURSIVE):
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_READ:
        table = (arg1 or "").lower()
        return sqlite3.SQLITE_OK if table in ALLOWED_TABLES else sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_FUNCTION:
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


def execute_readonly(
    sql: str,
    path: Path | str | None = None,
    timeout: float | None = None,
    max_rows: int | None = None,
) -> QueryResult:
    """Validate, sandbox and execute one read-only SQL query."""
    timeout = config.QUERY_TIMEOUT_SECONDS if timeout is None else timeout
    max_rows = config.MAX_ROWS if max_rows is None else max_rows
    try:
        sql = validate_sql(sql)
    except SQLGuardError as exc:
        raise QueryError(str(exc)) from exc

    wrapped = apply_limit(sql, max_rows)
    started = time.perf_counter()
    conn = connect(path, readonly=True)
    try:
        conn.set_authorizer(_authorizer)
        deadline = time.monotonic() + timeout

        def _progress() -> int:
            return 1 if time.monotonic() > deadline else 0

        conn.set_progress_handler(_progress, 1000)
        try:
            cursor = conn.execute(wrapped)
            rows = cursor.fetchmany(max_rows + 1)
            columns = [d[0] for d in (cursor.description or [])]
        except sqlite3.OperationalError as exc:
            message = str(exc)
            if "interrupted" in message:
                raise QueryError(f"查询超过 {timeout:g}s，已被沙箱中止") from exc
            if "not authorized" in message:
                raise QueryError("SQL 被沙箱拒绝：只允许读取白名单表") from exc
            raise QueryError(f"SQL 执行失败：{message}") from exc
        except sqlite3.DatabaseError as exc:
            raise QueryError(f"SQL 执行失败：{exc}") from exc
    finally:
        conn.close()

    truncated = len(rows) > max_rows
    if truncated:
        rows = rows[:max_rows]
    return QueryResult(
        columns=columns,
        rows=[tuple(r) for r in rows],
        elapsed_ms=round((time.perf_counter() - started) * 1000, 1),
        truncated=truncated,
    )


def _sample_values(conn: sqlite3.Connection, table: str, column: str) -> list[str]:
    try:
        rows = conn.execute(
            f"SELECT DISTINCT {column} FROM {table} WHERE {column} IS NOT NULL LIMIT 6"
        ).fetchall()
        return [str(r[0]) for r in rows]
    except sqlite3.Error:
        return []


def schema_text(path: Path | str | None = None) -> str:
    """Build a compact, LLM-friendly schema description with business rules."""
    conn = connect(path, readonly=True)
    try:
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        lines = ["数据库：SQLite，电商销售业务。"]
        for table in tables:
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            lines.append(f"\n表 {table}（{TABLE_NOTES.get(table, '')}，{count} 行）")
            for col in conn.execute(f"PRAGMA table_info({table})"):
                name, col_type = col[1], col[2]
                note = COLUMN_NOTES.get(name, "")
                lines.append(f"  - {name} {col_type}：{note}")
            for col in CATEGORICAL_COLUMNS.get(table, []):
                values = _sample_values(conn, table, col)
                if values:
                    lines.append(f"    {col} 取值示例：{' / '.join(values)}")
        lines.extend(
            [
                "\n业务口径：",
                "1) 销售额 = SUM(order_items.quantity * order_items.unit_price * order_items.discount)。",
                "2) 未特别说明时，销售额/订单数只统计 orders.status = '已支付'；退款率按全部订单计算。",
                "3) order_date 是 TEXT，格式 YYYY-MM-DD；按月分组用 strftime('%Y-%m', order_date)。",
                "4) 一个订单有多个 order_items，统计订单数要 COUNT(DISTINCT o.order_id)，避免 JOIN 后重复计数。",
                "5) 金额保留 2 位小数；Top-N 默认按金额降序。",
            ]
        )
        return "\n".join(lines)
    finally:
        conn.close()
