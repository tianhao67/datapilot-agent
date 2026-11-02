# -*- coding: utf-8 -*-
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from datapilot.db import QueryResult  # noqa: E402
from datapilot.evaluate import same_result  # noqa: E402


class CompareTest(unittest.TestCase):
    def test_order_insensitive(self):
        gold = QueryResult(columns=["city", "n"], rows=[("南京", 3), ("苏州", 2)])
        pred = QueryResult(columns=["city", "n"], rows=[("苏州", 2.0), ("南京", 3.0)])
        self.assertTrue(same_result(gold, pred))

    def test_column_count_must_match(self):
        gold = QueryResult(columns=["city", "n"], rows=[("南京", 3)])
        pred = QueryResult(columns=["city"], rows=[("南京",)])
        self.assertFalse(same_result(gold, pred))

    def test_value_mismatch(self):
        gold = QueryResult(columns=["sales"], rows=[(100.0,)])
        pred = QueryResult(columns=["sales"], rows=[(101.0,)])
        self.assertFalse(same_result(gold, pred))

    def test_float_tolerance(self):
        gold = QueryResult(columns=["sales"], rows=[(288159.58,)])
        pred = QueryResult(columns=["sales"], rows=[(288159.5812,)])
        self.assertTrue(same_result(gold, pred))


if __name__ == "__main__":
    unittest.main()
