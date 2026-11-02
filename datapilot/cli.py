# -*- coding: utf-8 -*-
"""Command line interface: ask / eval / schema."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import config
from .agent import AgentError, NL2SQLAgent
from .db import schema_text
from .evaluate import load_questions, run_eval, write_report


def _print_table(columns: list[str], rows: list[tuple], limit: int = 20) -> None:
    if not columns:
        return
    widths = [len(str(c)) for c in columns]
    for row in rows[:limit]:
        for i, value in enumerate(row):
            widths[i] = max(widths[i], len(str(value)))
    print(" | ".join(str(c).ljust(widths[i]) for i, c in enumerate(columns)))
    print("-+-".join("-" * w for w in widths))
    for row in rows[:limit]:
        print(" | ".join(str(v).ljust(widths[i]) for i, v in enumerate(row)))
    if len(rows) > limit:
        print(f"... 共 {len(rows)} 行，只显示前 {limit} 行")


def cmd_ask(args) -> None:
    agent = NL2SQLAgent()
    try:
        result = agent.ask(args.question)
    except AgentError as exc:
        print(f"失败：{exc}")
        for attempt in exc.attempts:
            print(f"- SQL: {attempt.sql}\n  错误: {attempt.error}")
        sys.exit(1)
    print(f"\n问题：{result.question}")
    print(f"SQL：{result.sql}")
    print(f"结果：{result.answer}")
    print(f"尝试：{len(result.attempts)} 次｜耗时：{result.latency_ms} ms\n")
    _print_table(result.columns, result.rows)


def cmd_eval(args) -> None:
    questions = load_questions(Path(args.questions))
    if args.limit:
        questions = questions[: args.limit]
    agent = NL2SQLAgent()

    def progress(index, total, row):
        flag = "OK" if row.ok else "FAIL"
        print(f"[{index:02d}/{total}] {row.id} {flag}  {row.attempts} 次  {row.latency_ms} ms")

    report = run_eval(agent, questions, progress=progress)
    out_dir = Path(args.output)
    json_path, md_path = write_report(report, out_dir)
    print("\n=== 汇总 ===")
    print(f"题目数：{report.total}")
    print(f"执行准确率：{report.accuracy}%")
    print(f"SQL 可执行率：{report.valid_rate}%")
    print(f"首次生成可执行率：{report.first_attempt_valid_rate}%")
    print(f"自纠错成功率：{report.self_correction_rate}%")
    print(f"平均尝试次数：{report.avg_attempts}")
    print(f"平均延迟：{report.avg_latency_ms} ms")
    print(f"报告：{json_path} / {md_path}")


def cmd_schema(_args) -> None:
    print(schema_text())


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="datapilot", description="NL2SQL data analysis agent")
    sub = parser.add_subparsers(dest="command", required=True)

    ask = sub.add_parser("ask", help="ask one question")
    ask.add_argument("question", help="自然语言问题")
    ask.set_defaults(func=cmd_ask)

    ev = sub.add_parser("eval", help="run the offline evaluation set")
    ev.add_argument("--questions", default=str(config.ROOT / "data" / "questions.jsonl"))
    ev.add_argument("--limit", type=int, default=0)
    ev.add_argument("--output", default=str(config.ROOT / "eval"))
    ev.set_defaults(func=cmd_eval)

    schema = sub.add_parser("schema", help="print the schema prompt")
    schema.set_defaults(func=cmd_schema)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
