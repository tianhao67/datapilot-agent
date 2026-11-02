# -*- coding: utf-8 -*-
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from datapilot.db import QueryError, execute_readonly, schema_text  # noqa: E402
from scripts.build_db import build  # noqa: E402


class DatabaseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tmp_dir = ROOT / ".test_tmp"
        tmp_dir.mkdir(exist_ok=True)
        cls.db = tmp_dir / "shop.db"
        build(cls.db)

    def test_scalar_query(self):
        sql = (
            "SELECT ROUND(SUM(oi.quantity * oi.unit_price * oi.discount), 2) AS sales "
            "FROM orders o JOIN order_items oi ON oi.order_id = o.order_id "
            "WHERE o.status = '已支付' AND o.order_date >= '2026-10-01' AND o.order_date < '2026-11-01'"
        )
        result = execute_readonly(sql, self.db)
        self.assertEqual(result.columns, ["sales"])
        self.assertEqual(len(result.rows), 1)
        self.assertGreater(result.rows[0][0], 0)

    def test_schema_contains_tables_and_rules(self):
        text = schema_text(self.db)
        self.assertIn("order_items", text)
        self.assertIn("销售额", text)
        self.assertIn("已支付", text)

    def test_write_rejected(self):
        with self.assertRaises(QueryError):
            execute_readonly("DELETE FROM orders", self.db)

    def test_truncation(self):
        result = execute_readonly("SELECT * FROM orders", self.db, max_rows=10)
        self.assertEqual(len(result.rows), 10)
        self.assertTrue(result.truncated)


if __name__ == "__main__":
    unittest.main()
