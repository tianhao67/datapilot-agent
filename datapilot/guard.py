# -*- coding: utf-8 -*-
"""SQL safety guard: read-only, single statement, table whitelist."""
from __future__ import annotations

import re

ALLOWED_TABLES = {"customers", "products", "orders", "order_items"}
FORBIDDEN_KEYWORDS = {
    "insert", "update", "delete", "drop", "alter", "create", "replace",
    "attach", "detach", "pragma", "vacuum", "reindex", "trigger", "grant",
    "revoke", "load_extension",
}
TABLE_PATTERN = re.compile(r"\b(?:from|join)\s+([a-zA-Z_][a-zA-Z0-9_]*)", re.IGNORECASE)


class SQLGuardError(ValueError):
    """Raised when a generated statement is not allowed to run."""


def strip_comments(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    sql = re.sub(r"--[^\n]*", " ", sql)
    return sql


def validate_sql(sql: str, allowed_tables: set[str] | None = None) -> str:
    """Validate and normalize a generated SQL statement.

    Returns the SQL without a trailing semicolon. Raises SQLGuardError.
    """
    if not sql or not sql.strip():
        raise SQLGuardError("SQL 为空")
    cleaned = strip_comments(sql).strip()
    if not cleaned:
        raise SQLGuardError("SQL 只有注释")
    if ";" in cleaned.rstrip(";"):
        raise SQLGuardError("只允许单条语句，检测到多条语句")
    cleaned = cleaned.rstrip(";").strip()

    lowered = cleaned.lower()
    if not (lowered.startswith("select") or lowered.startswith("with")):
        raise SQLGuardError("只允许 SELECT / WITH 查询")

    for word in FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{word}\b", lowered):
            raise SQLGuardError(f"检测到禁止的关键字：{word}")

    tables = allowed_tables or ALLOWED_TABLES
    cte_names = {
        m.group(1).lower()
        for m in re.finditer(r"(?:\bwith\b|,)\s*([a-zA-Z_][a-zA-Z0-9_]*)\s+as\s*\(", cleaned, re.IGNORECASE)
    }
    found = {m.group(1).lower() for m in TABLE_PATTERN.finditer(cleaned)}
    unknown = found - tables - cte_names
    if unknown:
        raise SQLGuardError(f"检测到未授权的表：{', '.join(sorted(unknown))}")

    return cleaned


def apply_limit(sql: str, max_rows: int) -> str:
    """Always wrap the query so a missing/huge LIMIT cannot return everything."""
    return f"SELECT * FROM (\n{sql}\n) LIMIT {max_rows + 1}"
