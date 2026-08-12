"""Fetch the historical 福彩3D results from 500.com.

The visible history page is ``/sd/history/history.shtml``; its actual data
table is loaded by the iframe at ``/sd/history/inc/history.php``.  Requests
use a mobile browser profile because the site can be more reliable when the
request looks like a phone page.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sqlite3
import shutil
import uuid
from datetime import datetime, timezone
import csv
import re
import sys
import os
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


URL = os.environ.get(
    "SD3D_URL",
    "https://datachart.500.com/sd/history/inc/history.php",
)
DEFAULT_OUTPUT = Path(__file__).with_name("sd3d_history.csv")
DEFAULT_DB = Path(__file__).with_name("sd3d_history.sqlite3")
DEFAULT_LOG = Path(__file__).with_name("sd3d_history.jsonl")
LEGACY_LOG = Path(__file__).with_name("sd3d_history.tx")
DEFAULT_STATE = Path(__file__).with_name("sd3d_fetch_state.json")
MIN_REQUEST_INTERVAL = float(os.environ.get("SD3D_MIN_INTERVAL", "3.0"))


class TableParser(HTMLParser):
    """Collect table rows without requiring pandas or BeautifulSoup."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "tr":
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"td", "th"} and self._cell is not None and self._row is not None:
            value = re.sub(r"\s+", " ", "".join(self._cell)).strip()
            self._row.append(value)
            self._cell = None
        elif tag == "tr" and self._row:
            self.rows.append(self._row)
            self._row = None


def fetch_html(url: str, retries: int = 3, state_path: Path = DEFAULT_STATE) -> str:
    headers = {
        # Android Chrome mobile profile.
        "User-Agent": (
            "Mozilla/5.0 (Linux; Android 13; Pixel 7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Mobile Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
        "Referer": "https://m.500.com/",
        "Cache-Control": "no-cache",
        "Connection": "close",
    }
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        state = {}
        if state_path.exists():
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                state = {}
        elapsed = time.time() - float(state.get("last_request_epoch", 0))
        if elapsed < MIN_REQUEST_INTERVAL:
            time.sleep(MIN_REQUEST_INTERVAL - elapsed + random.uniform(0.3, 1.5))
        try:
            state_path.write_text(json.dumps({"last_request_epoch": time.time(), "url": url}, ensure_ascii=False), encoding="utf-8")
            request = Request(url, headers=headers, method="GET")
            with urlopen(request, timeout=25) as response:
                status = getattr(response, "status", response.getcode())
                body = response.read()
                if status != 200:
                    raise RuntimeError(f"HTTP {status}")
                state_path.write_text(json.dumps({
                    "last_request_epoch": time.time(), "last_success_epoch": time.time(),
                    "last_status": status, "url": url,
                    "etag": response.headers.get("ETag"),
                    "last_modified": response.headers.get("Last-Modified"),
                }, ensure_ascii=False, indent=2), encoding="utf-8")
                # The endpoint normally declares GB18030; replace invalid
                # declarations safely for occasional UTF-8 responses.
                return body.decode(response.headers.get_content_charset() or "gb18030", errors="replace")
        except HTTPError as exc:
            last_error = exc
            if exc.code in {403, 406}:
                raise RuntimeError(
                    f"服务器返回 HTTP {exc.code}，为避免加重限制，本次停止重试。"
                    "请稍后再运行，不要并行或缩短请求间隔。"
                ) from exc
            if exc.code == 404:
                raise RuntimeError(
                    f"接口返回 404：{url}\n"
                    "请确认 URL、起止期号参数和网络访问状态。"
                    "可用 SD3D_URL 环境变量指定其他数据接口。"
                ) from exc
        except (URLError, TimeoutError, OSError, RuntimeError) as exc:
            last_error = exc
            if exc.code in {429, 500, 502, 503, 504}:
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                try:
                    delay = max(float(retry_after), attempt * 8) if retry_after else attempt * 8
                except ValueError:
                    delay = attempt * 8
                time.sleep(delay + random.uniform(0.5, 2.0))
        if attempt < retries and not isinstance(last_error, HTTPError):
            time.sleep(attempt * 3 + random.uniform(0.5, 1.5))
    raise RuntimeError(f"访问失败（重试 {retries} 次）：{last_error}") from last_error


def extract_rows(html: str) -> list[list[str]]:
    parser = TableParser()
    parser.feed(html)
    rows = [row for row in parser.rows if len(row) >= 4]
    if not rows:
        raise RuntimeError("页面已返回，但没有找到历史开奖表格；可能遇到验证码或页面结构已变化。")
    # Remove repeated table headers while preserving the first header row.
    result: list[list[str]] = []
    seen_header = False
    for row in rows:
        if row and ("期号" in row[0] or "开奖日期" in "".join(row)):
            if seen_header:
                continue
            seen_header = True
        result.append(row)
    return result


def extract_draw_rows(rows: list[list[str]]) -> list[list[str]]:
    """Keep only actual draw rows; headers and page controls are excluded."""
    return [row for row in rows if row and re.fullmatch(r"\d{5,8}", row[0])]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def open_store(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=FULL")
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS draws (
            period TEXT PRIMARY KEY, values_json TEXT NOT NULL,
            source_url TEXT NOT NULL, source_sha256 TEXT NOT NULL,
            first_seen TEXT NOT NULL, last_seen TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT,
            source_url TEXT NOT NULL, source_sha256 TEXT, fetched_rows INTEGER NOT NULL DEFAULT 0,
            inserted_rows INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL, error TEXT
        );
    """)
    return connection


def append_tx(path: Path, event: dict) -> None:
    previous = "GENESIS"
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()
        if lines:
            previous = json.loads(lines[-1])["event_hash"]
    event = {"previous_hash": previous, **event}
    payload = json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    event["event_hash"] = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


def persist_draws(rows: list[list[str]], source_url: str, source_hash: str,
                  db_path: Path, log_path: Path, run_id: str) -> tuple[int, int]:
    connection = open_store(db_path)
    inserted = 0
    try:
        connection.execute("INSERT INTO runs(run_id,started_at,source_url,source_sha256,status) VALUES(?,?,?,?,?)",
                           (run_id, utc_now(), source_url, source_hash, "started"))
        for row in rows:
            period = row[0]
            if connection.execute("SELECT 1 FROM draws WHERE period=?", (period,)).fetchone():
                connection.execute("UPDATE draws SET last_seen=? WHERE period=?", (utc_now(), period))
                continue
            now = utc_now()
            connection.execute("INSERT INTO draws VALUES(?,?,?,?,?,?)",
                               (period, json.dumps(row, ensure_ascii=False), source_url, source_hash, now, now))
            append_tx(log_path, {"type": "draw_insert", "run_id": run_id, "period": period, "row": row, "at": now})
            inserted += 1
        connection.execute("UPDATE runs SET finished_at=?,fetched_rows=?,inserted_rows=?,status=? WHERE run_id=?",
                           (utc_now(), len(rows), inserted, "committed", run_id))
        connection.commit()
        append_tx(log_path, {"type": "run_commit", "run_id": run_id, "fetched_rows": len(rows), "inserted_rows": inserted, "at": utc_now()})
        return len(rows), inserted
    except Exception as exc:
        connection.rollback()
        append_tx(log_path, {"type": "run_rollback", "run_id": run_id, "error": repr(exc), "at": utc_now()})
        raise
    finally:
        connection.close()


def save_csv(rows: list[list[str]], output: Path) -> None:
    width = max(len(row) for row in rows)
    with output.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerows(row + [""] * (width - len(row)) for row in rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="抓取福彩3D历史开奖数据")
    parser.add_argument("-o", "--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--start", help="起始期号，例如 2026001")
    parser.add_argument("--end", help="结束期号，例如 2026999")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--log", "--tx", dest="log", type=Path, default=DEFAULT_LOG,
                        help="追加式 JSONL 审计日志；--tx 仅为旧参数兼容别名")
    args = parser.parse_args()
    if args.log == DEFAULT_LOG and LEGACY_LOG.exists() and not args.log.exists():
        # Preserve the old hash chain while moving to the standard JSONL suffix.
        shutil.copy2(LEGACY_LOG, args.log)
    url = URL
    if args.start or args.end:
        if not (args.start and args.end):
            parser.error("--start 和 --end 必须同时提供")
        url += ("&" if "?" in url else "?") + f"start={args.start}&end={args.end}"
    else:
        # Bootstrap from the first known 福彩3D period; later runs request
        # only periods newer than the highest committed period.
        connection = open_store(args.db)
        latest = connection.execute("SELECT MAX(CAST(period AS INTEGER)) FROM draws").fetchone()[0]
        connection.close()
        start = latest + 1 if latest is not None else 2004001
        url += ("&" if "?" in url else "?") + f"start={start}&end={datetime.now().year}999"
    try:
        html = fetch_html(url)
        page_rows = extract_rows(html)
        draw_rows = extract_draw_rows(page_rows)
        if not draw_rows:
            print("No new draw rows; existing SQLite and transaction log were preserved.")
            return 0
        source_hash = hashlib.sha256(html.encode("utf-8")).hexdigest()
        fetched, inserted = persist_draws(draw_rows, url, source_hash, args.db, args.log, uuid.uuid4().hex)
        connection = open_store(args.db)
        stored = connection.execute("SELECT values_json FROM draws ORDER BY period DESC").fetchall()
        connection.close()
        save_csv([json.loads(item[0]) for item in stored], args.output)
    except Exception as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 1
    # Windows consoles may expose cp1252 even when the page itself is UTF-8/GBK.
    print(f"Fetched: {fetched}; newly inserted: {inserted}")
    print(f"CSV export: {args.output.resolve()}")
    print(f"SQLite store: {args.db.resolve()}")
    print(f"Audit log: {args.log.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
