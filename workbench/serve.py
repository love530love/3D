"""Interactive local server for the workbench (pure standard library).

Serves the live decision dashboard and exposes a tiny JSON API so the dashboard
buttons can actually run pipeline functions in the background. No external
dependencies, no auto-apply of changes; high-risk actions (rollback) require an
explicit confirm flag from the client.
"""

from __future__ import annotations

import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import dashboard, engine
from .registry import by_id

TASKS: dict[str, dict] = {}
TASK_LOCK = threading.Lock()


def start_task(func_id: str, extra_args=None) -> str:
    tid = uuid.uuid4().hex[:12]
    with TASK_LOCK:
        TASKS[tid] = {"status": "running", "log": [], "returncode": None}
    fid = func_id

    def worker() -> None:
        def on_line(s: str) -> None:
            with TASK_LOCK:
                if tid in TASKS:
                    TASKS[tid]["log"].append(s)

        res = engine.run_function(fid, extra_args=extra_args, on_line=on_line)
        with TASK_LOCK:
            if tid in TASKS:
                TASKS[tid]["status"] = "done"
                TASKS[tid]["returncode"] = res["returncode"]

    threading.Thread(target=worker, daemon=True).start()
    return tid


def _parse_qs(path: str) -> dict:
    qs = path.split("?", 1)[1] if "?" in path else ""
    out = {}
    for pair in qs.split("&"):
        if "=" in pair:
            k, v = pair.split("=", 1)
            out[k] = v
    return out


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body, ctype: str) -> None:
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            html = dashboard.build_html(engine.collect_state(), live=True)
            self._send(200, html, "text/html; charset=utf-8")
        elif path == "/api/state":
            self._send(200, json.dumps(engine.collect_state(), ensure_ascii=False), "application/json; charset=utf-8")
        elif path == "/api/task":
            tid = _parse_qs(self.path).get("id", "")
            with TASK_LOCK:
                t = TASKS.get(tid)
                snap = dict(t) if t else {"status": "unknown", "log": [], "returncode": None}
            self._send(200, json.dumps(snap, ensure_ascii=False), "application/json; charset=utf-8")
        elif path == "/api/versions":
            self._send(200, json.dumps(engine.git_versions(), ensure_ascii=False), "application/json; charset=utf-8")
        else:
            self._send(404, "not found", "text/plain; charset=utf-8")

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length else b""
        try:
            body = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            body = {}
        path = self.path.split("?", 1)[0]
        if path == "/api/run":
            fid = body.get("id", "")
            extra = body.get("args", [])
            func = by_id(fid)
            if not func or func["script"] == "__rollback__":
                self._send(400, json.dumps({"error": f"invalid function id: {fid}"}), "application/json; charset=utf-8")
                return
            tid = start_task(fid, extra_args=extra)
            self._send(200, json.dumps({"task_id": tid}), "application/json; charset=utf-8")
        elif path == "/api/rollback":
            ref = body.get("ref", "")
            confirm = bool(body.get("confirm"))
            res = engine.rollback(ref, confirm=confirm)
            self._send(200, json.dumps(res, ensure_ascii=False), "application/json; charset=utf-8")
        else:
            self._send(404, "not found", "text/plain; charset=utf-8")

    def log_message(self, *args) -> None:  # silence default logging
        return


def serve(port: int = 8787, host: str = "127.0.0.1"):
    httpd = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host}:{port}/"
    print(f"决策大屏已启动: {url}  (Ctrl+C 退出)")
    print("可用功能见页面 '功能' 选项卡；高风险操作需确认。")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        httpd.server_close()
