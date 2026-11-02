# -*- coding: utf-8 -*-
"""Offline evaluation: execution accuracy, valid-SQL rate, latency."""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .agent import AgentError, NL2SQLAgent
from .db import QueryError, QueryResult, execute_readonly


@dataclass
class EvalRow:
    id: str
    question: str
    difficulty: str
    ok: bool
    valid_sql: bool
    first_attempt_valid: bool
    attempts: int
    latency_ms: float
    pred_sql: str = ""
    gold_sql: str = ""
    error: str = ""


@dataclass
class EvalReport:
    total: int = 0
    accuracy: float = 0.0
    valid_rate: float = 0.0
    first_attempt_valid_rate: float = 0.0
    self_correction_rate: float = 0.0
    avg_attempts: float = 0.0
    avg_latency_ms: float = 0.0
    by_difficulty: dict = field(default_factory=dict)
    rows: list[EvalRow] = field(default_factory=list)


def _norm_value(value):
    if isinstance(value, float):
        return round(value, 2) if abs(value) >= 1 else round(value, 4)
    if isinstance(value, str):
        return value.strip()
    return value


def _norm_rows(result: QueryResult) -> list[tuple]:
    rows = [tuple(_norm_value(v) for v in row) for row in result.rows]
    return sorted(rows, key=lambda r: tuple(str(v) for v in r))


def same_result(gold: QueryResult, pred: QueryResult) -> bool:
    if len(gold.columns) != len(pred.columns):
        return False
    return _norm_rows(gold) == _norm_rows(pred)


def load_questions(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def run_eval(agent: NL2SQLAgent, questions: list[dict], progress=None) -> EvalReport:
    rows: list[EvalRow] = []
    for index, item in enumerate(questions, 1):
        started = time.perf_counter()
        ok = False
        valid = False
        first_valid = False
        attempts = 0
        pred_sql = ""
        error = ""
        try:
            result = agent.ask(item["question"])
            pred_sql = result.sql
            attempts = len(result.attempts)
            first_valid = bool(result.attempts and result.attempts[0].error is None)
            valid = True
            gold = execute_readonly(item["gold_sql"])
            ok = same_result(gold, QueryResult(result.columns, result.rows))
        except AgentError as exc:
            attempts = len(exc.attempts)
            first_valid = bool(exc.attempts and exc.attempts[0].error is None)
            pred_sql = exc.attempts[-1].sql if exc.attempts else ""
            error = str(exc)
        except (QueryError, FileNotFoundError) as exc:
            error = str(exc)
        latency = round((time.perf_counter() - started) * 1000, 1)
        rows.append(
            EvalRow(
                id=item["id"],
                question=item["question"],
                difficulty=item.get("difficulty", "unknown"),
                ok=ok,
                valid_sql=valid,
                first_attempt_valid=first_valid,
                attempts=attempts,
                latency_ms=latency,
                pred_sql=pred_sql,
                gold_sql=item["gold_sql"],
                error=error,
            )
        )
        if progress:
            progress(index, len(questions), rows[-1])

    total = len(rows)
    report = EvalReport(total=total, rows=rows)
    if total:
        report.accuracy = round(100.0 * sum(r.ok for r in rows) / total, 2)
        report.valid_rate = round(100.0 * sum(r.valid_sql for r in rows) / total, 2)
        report.first_attempt_valid_rate = round(100.0 * sum(r.first_attempt_valid for r in rows) / total, 2)
        corrected = [r for r in rows if r.ok and r.attempts > 1]
        failed_first = [r for r in rows if r.attempts > 1]
        report.self_correction_rate = (
            round(100.0 * len(corrected) / len(failed_first), 2) if failed_first else 0.0
        )
        report.avg_attempts = round(sum(r.attempts for r in rows) / total, 2)
        report.avg_latency_ms = round(sum(r.latency_ms for r in rows) / total, 1)
    for difficulty in sorted({r.difficulty for r in rows}):
        subset = [r for r in rows if r.difficulty == difficulty]
        report.by_difficulty[difficulty] = {
            "total": len(subset),
            "accuracy": round(100.0 * sum(r.ok for r in subset) / len(subset), 2) if subset else 0.0,
        }
    return report


def write_report(report: EvalReport, out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "report.json"
    md_path = out_dir / "report.md"
    json_path.write_text(
        json.dumps(
            {
                **{k: v for k, v in asdict(report).items() if k != "rows"},
                "rows": [asdict(r) for r in report.rows],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    lines = [
        "# DataPilot 评测报告",
        "",
        f"- 题目数：{report.total}",
        f"- 执行准确率：**{report.accuracy}%**",
        f"- SQL 可执行率：{report.valid_rate}%",
        f"- 首次生成可执行率：{report.first_attempt_valid_rate}%",
        f"- 自纠错成功率：{report.self_correction_rate}%",
        f"- 平均尝试次数：{report.avg_attempts}",
        f"- 平均延迟：{report.avg_latency_ms} ms",
        "",
        "## 分难度",
        "",
        "| 难度 | 题数 | 准确率 |",
        "|---|---|---|",
    ]
    for difficulty, stat in report.by_difficulty.items():
        lines.append(f"| {difficulty} | {stat['total']} | {stat['accuracy']}% |")
    lines.extend(["", "## 错题", "", "| ID | 问题 | 尝试 | 错误 |", "|---|---|---|---|"])
    for row in report.rows:
        if not row.ok:
            error = (row.error or "结果不一致").replace("|", "/")[:120]
            lines.append(f"| {row.id} | {row.question} | {row.attempts} | {error} |")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path
