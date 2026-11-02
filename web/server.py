# -*- coding: utf-8 -*-
"""Zero-dependency web demo for DataPilot (stdlib http.server)."""
from __future__ import annotations

import argparse
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from datapilot.agent import AgentError, NL2SQLAgent  # noqa: E402
from datapilot import config  # noqa: E402

INDEX = Path(__file__).resolve().parent / "index.html"
_LOCK = threading.Lock()
_AGENT: NL2SQLAgent | None = None


def get_agent() -> NL2SQLAgent:
    global _AGENT
    if _AGENT is None:
        _AGENT = NL2SQLAgent()
    return _AGENT


def _json_default(value):
    if isinstance(value, float):
        return round(value, 4)
    return str(value)


class Handler(BaseHTTPRequestHandler):
    server_version = "DataPilot/0.1"

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: dict) -> None:
        self._send(status, json.dumps(payload, ensure_ascii=False, default=_json_default).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self) -> None:  # noqa: N802
        if self.path in ("/", "/index.html"):
            self._send(200, INDEX.read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/api/health":
            self._json(200, {"ok": True})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/api/ask":
            self._json(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            question = str(payload.get("question", "")).strip()
        except (ValueError, UnicodeDecodeError):
            self._json(400, {"error": "请求不是合法 JSON"})
            return
        if not question:
            self._json(400, {"error": "问题不能为空"})
            return
        try:
            with _LOCK:
                result = get_agent().ask(question)
            self._json(
                200,
                {
                    "ok": True,
                    "question": result.question,
                    "sql": result.sql,
                    "answer": result.answer,
                    "columns": result.columns,
                    "rows": result.rows,
                    "attempts": [
                        {"sql": a.sql, "error": a.error, "elapsed_ms": a.elapsed_ms, "row_count": a.row_count}
                        for a in result.attempts
                    ],
                    "latency_ms": result.latency_ms,
                    "chart": result.chart,
                    "reason": result.reason,
                    "model": config.OLLAMA_MODEL if config.LLM_PROVIDER == "ollama" else config.OPENAI_MODEL,
                },
            )
        except AgentError as exc:
            self._json(
                422,
                {
                    "ok": False,
                    "error": str(exc),
                    "attempts": [
                        {"sql": a.sql, "error": a.error, "elapsed_ms": a.elapsed_ms, "row_count": a.row_count}
                        for a in exc.attempts
                    ],
                },
            )
        except Exception as exc:  # noqa: BLE001
            self._json(500, {"ok": False, "error": f"服务端异常：{exc}"})

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        return


def main() -> None:
    parser = argparse.ArgumentParser(description="DataPilot web demo")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"DataPilot running at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
