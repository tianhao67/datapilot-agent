# -*- coding: utf-8 -*-
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from datapilot.guard import SQLGuardError, apply_limit, validate_sql  # noqa: E402


class GuardTest(unittest.TestCase):
    def test_select_allowed(self):
        sql = validate_sql("SELECT * FROM orders")
        self.assertEqual(sql, "SELECT * FROM orders")

    def test_dml_rejected(self):
        for sql in [
            "UPDATE orders SET status = 'x'",
            "DELETE FROM orders",
            "DROP TABLE orders",
            "INSERT INTO orders VALUES (1)",
        ]:
            with self.subTest(sql=sql):
                with self.assertRaises(SQLGuardError):
                    validate_sql(sql)

    def test_multi_statement_rejected(self):
        with self.assertRaises(SQLGuardError):
            validate_sql("SELECT * FROM orders; DROP TABLE orders")

    def test_unknown_table_rejected(self):
        with self.assertRaises(SQLGuardError):
            validate_sql("SELECT * FROM secret_table")

    def test_cte_allowed(self):
        sql = "WITH t AS (SELECT city FROM customers) SELECT * FROM t"
        self.assertTrue(validate_sql(sql).startswith("WITH"))

    def test_comment_stripped(self):
        self.assertEqual(validate_sql("SELECT 1 -- hi\n"), "SELECT 1")

    def test_apply_limit(self):
        self.assertIn("LIMIT 201", apply_limit("SELECT * FROM orders", 200))


if __name__ == "__main__":
    unittest.main()
