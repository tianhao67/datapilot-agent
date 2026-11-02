# -*- coding: utf-8 -*-
"""NL2SQL agent loop: generate -> guard -> execute -> self-correct."""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import config
from .db import QueryError, execute_readonly, schema_text
from .llm import LLMError, get_client
from .prompts import build_messages


class AgentError(RuntimeError):
    def __init__(self, message: str, attempts: list["Attempt"] | None = None):
        super().__init__(message)
        self.attempts = attempts or []


@dataclass
class Attempt:
    sql: str
    error: str | None = None
    elapsed_ms: float = 0.0
    row_count: int | None = None


@dataclass
class AgentResult:
    question: str
    sql: str
    columns: list[str] = field(default_factory=list)
    rows: list[tuple] = field(default_factory=list)
    answer: str = ""
    reason: str = ""
    attempts: list[Attempt] = field(default_factory=list)
    latency_ms: float = 0.0
    chart: dict = field(default_factory=dict)


def _strip_fence(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json|sql)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def parse_sql(content: str) -> str:
    """Extract SQL from a JSON response, with a tolerant fallback for small models."""
    text = _strip_fence(content)
    candidates = [text]
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        candidates.insert(0, match.group(0))
    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            for key in ("sql", "query", "SQL", "Sql"):
                value = data.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip().rstrip(";").strip()
    # Last resort: take the first SELECT/WITH block.
    match = re.search(r"(?is)\b(select|with)\b.+", text)
    if match:
        sql = match.group(0).strip()
        sql = sql.split("```")[0].strip()
        return sql.rstrip(";").strip()
    raise ValueError("模型输出里没有找到 SQL")


def _format_value(value) -> str:
    if isinstance(value, float):
        return f"{value:,.2f}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def summarize(columns: list[str], rows: list[tuple]) -> str:
    if not rows:
        return "没有查到符合条件的数据。"
    if len(rows) == 1 and len(columns) == 1:
        return f"{columns[0]} 为 {_format_value(rows[0][0])}。"
    first = "，".join(f"{c} = {_format_value(v)}" for c, v in zip(columns, rows[0]))
    more = f"（共 {len(rows)} 行）" if len(rows) > 1 else ""
    return f"查到 {len(rows)} 行{more}；第一行：{first}。"


def infer_chart(columns: list[str], rows: list[tuple]) -> dict:
    if not rows:
        return {"type": "table"}
    if len(rows) == 1 and len(columns) == 1:
        return {"type": "metric", "label": columns[0], "value": rows[0][0]}
    if len(columns) != 2:
        return {"type": "table"}
    x, y = columns
    numeric_y = all(isinstance(r[1], (int, float)) for r in rows)
    if not numeric_y:
        return {"type": "table"}
    looks_like_time = all(re.match(r"^\d{4}(-\d{2})?", str(r[0])) for r in rows)
    return {"type": "line" if looks_like_time else "bar", "x": x, "y": y}


class NL2SQLAgent:
    def __init__(self, db_path: Path | str | None = None, llm=None, max_attempts: int | None = None):
        self.db_path = db_path or config.DB_PATH
        self.llm = llm or get_client()
        self.max_attempts = max_attempts or config.MAX_ATTEMPTS
        self.schema = schema_text(self.db_path)

    def ask(self, question: str) -> AgentResult:
        question = question.strip()
        if not question:
            raise AgentError("问题不能为空")
        started = time.perf_counter()
        attempts: list[Attempt] = []
        previous: list[dict] = []
        last_error = ""

        for _ in range(self.max_attempts):
            messages = build_messages(question, self.schema, previous)
            try:
                content = self.llm.chat(messages, json_mode=True)
            except LLMError as exc:
                raise AgentError(f"模型调用失败：{exc}", attempts) from exc

            try:
                sql = parse_sql(content)
            except ValueError as exc:
                last_error = f"输出解析失败：{exc}"
                attempts.append(Attempt(sql="", error=last_error))
                previous.append({"sql": "", "error": last_error})
                continue

            try:
                result = execute_readonly(sql, self.db_path)
            except QueryError as exc:
                last_error = str(exc)
                attempts.append(Attempt(sql=sql, error=last_error))
                previous.append({"sql": sql, "error": last_error})
                continue

            attempts.append(
                Attempt(sql=sql, elapsed_ms=result.elapsed_ms, row_count=len(result.rows))
            )
            reason = ""
            match = re.search(r'"reason"\s*:\s*"([^"]*)"', content)
            if match:
                reason = match.group(1)
            return AgentResult(
                question=question,
                sql=sql,
                columns=result.columns,
                rows=result.rows,
                answer=summarize(result.columns, result.rows),
                reason=reason,
                attempts=attempts,
                latency_ms=round((time.perf_counter() - started) * 1000, 1),
                chart=infer_chart(result.columns, result.rows),
            )

        raise AgentError(f"连续 {self.max_attempts} 次没有生成可执行的 SQL：{last_error}", attempts)
