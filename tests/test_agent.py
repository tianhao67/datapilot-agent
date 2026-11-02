# -*- coding: utf-8 -*-
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from datapilot.agent import AgentError, NL2SQLAgent, parse_sql  # noqa: E402
from scripts.build_db import build  # noqa: E402

GOOD_SQL = (
    "SELECT ROUND(SUM(oi.quantity * oi.unit_price * oi.discount), 2) AS sales "
    "FROM orders o JOIN order_items oi ON oi.order_id = o.order_id "
    "WHERE o.status = '已支付' AND o.order_date >= '2026-10-01' AND o.order_date < '2026-11-01'"
)


class FakeLLM:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def chat(self, messages, json_mode=True):
        self.calls.append(messages)
        return self.replies.pop(0)


class ParseTest(unittest.TestCase):
    def test_plain_json(self):
        self.assertEqual(parse_sql('{"sql": "SELECT 1"}'), "SELECT 1")

    def test_fenced_json(self):
        self.assertEqual(parse_sql('```json\n{"sql": "SELECT 2"}\n```'), "SELECT 2")

    def test_fallback_select(self):
        self.assertEqual(parse_sql("这是 SQL：SELECT 3"), "SELECT 3")

    def test_empty(self):
        with self.assertRaises(ValueError):
            parse_sql("没有 SQL")


class AgentTest(unittest.TestCase):
    def setUp(self):
        tmp_dir = ROOT / ".test_tmp"
        tmp_dir.mkdir(exist_ok=True)
        self.db = tmp_dir / "agent.db"
        build(self.db)

    def test_success_first_try(self):
        agent = NL2SQLAgent(self.db, llm=FakeLLM([f'{{"sql": "{GOOD_SQL}", "reason": "ok"}}']))
        result = agent.ask("2026 年 10 月的销售额是多少？")
        self.assertEqual(len(result.attempts), 1)
        self.assertAlmostEqual(result.rows[0][0], 288159.58, places=2)

    def test_self_correction(self):
        bad = '{"sql": "SELECT missing_column FROM orders"}'
        good = '{"sql": "%s", "reason": "fixed"}' % GOOD_SQL
        llm = FakeLLM([bad, good])
        agent = NL2SQLAgent(self.db, llm=llm)
        result = agent.ask("2026 年 10 月的销售额是多少？")
        self.assertEqual(len(result.attempts), 2)
        self.assertIsNotNone(result.attempts[0].error)
        self.assertEqual(len(llm.calls), 2)

    def test_gives_up_after_max_attempts(self):
        bad = '{"sql": "SELECT missing_column FROM orders"}'
        agent = NL2SQLAgent(self.db, llm=FakeLLM([bad, bad, bad]), max_attempts=3)
        with self.assertRaises(AgentError):
            agent.ask("坏问题")


if __name__ == "__main__":
    unittest.main()
