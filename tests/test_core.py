import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from fetch_sd3d import extract_draw_rows, extract_rows
from models_sd3d import REGISTRY


class CoreContractTests(unittest.TestCase):
    def test_parser_keeps_only_period_rows(self):
        html = "<table><tr><th>期号</th><th>号码</th><th>和值</th><th>日期</th></tr><tr><td>2026001</td><td>1 2 3</td><td>6</td><td>2026-01-01</td></tr></table>"
        self.assertEqual(extract_draw_rows(extract_rows(html)), [["2026001", "1 2 3", "6", "2026-01-01"]])

    def test_model_registry_has_uniform_baseline(self):
        self.assertEqual(REGISTRY[0].name, "uniform_baseline")
        self.assertEqual(len(REGISTRY[0].predict([], 10)), 10)

    def test_persisted_payload_is_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.sqlite3"
            connection = sqlite3.connect(path)
            try:
                connection.execute("CREATE TABLE draws(period TEXT PRIMARY KEY, values_json TEXT)")
                connection.execute("INSERT INTO draws VALUES (?, ?)", ("2026001", json.dumps(["2026001", "1 2 3"])))
                connection.commit()
                payload = connection.execute("SELECT values_json FROM draws").fetchone()[0]
            finally:
                connection.close()
            self.assertEqual(json.loads(payload)[1], "1 2 3")


if __name__ == "__main__":
    unittest.main()
