from __future__ import annotations

import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from .live_client import capture_snapshot
from .lolalytics import DEFAULT_TIER
from .recommend import recommend_from_snapshot


DEFAULT_OUT = Path("data/processed/live_recommendation.json")
WEB_ROOT = Path("web")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _safe_snapshot_path(value: str) -> Path:
    root = Path("data/raw").resolve()
    target = Path(value).resolve()
    if root != target and root not in target.parents:
        raise ValueError("snapshot path must be inside data/raw")
    return target


def _list_snapshots() -> list[dict[str, str]]:
    root = Path("data/raw")
    if not root.exists():
        return []
    out = []
    for path in sorted(root.glob("live_*"), reverse=True):
        if path.is_dir():
            out.append({"name": path.name, "path": str(path)})
    return out


def _make_handler(
    *,
    out_path: Path,
    static_root: Path,
    mode: str,
    tier: str,
    min_champions_analysed: int,
    refresh_lolalytics: bool,
):
    class Handler(BaseHTTPRequestHandler):
        server_version = "LolBuildAssistant/0.1"

        def log_message(self, fmt: str, *args: object) -> None:
            print(f"[server] {self.address_string()} - {fmt % args}")

        def _send_json(self, data: Any, status: int = 200) -> None:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_error_json(self, message: str, status: int = 500) -> None:
            self._send_json({"ok": False, "error": message}, status=status)

        def _read_body(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0:
                return {}
            raw = self.rfile.read(length).decode("utf-8")
            return json.loads(raw or "{}")

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            if path == "/api/recommendation":
                if not out_path.exists():
                    self._send_json({"ok": True, "data": None})
                    return
                self._send_json({"ok": True, "data": _read_json(out_path)})
                return
            if path == "/api/snapshots":
                self._send_json({"ok": True, "snapshots": _list_snapshots()})
                return
            self._serve_static(path)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            try:
                if parsed.path == "/api/recommend-live":
                    snapshot = capture_snapshot()
                    result = recommend_from_snapshot(
                        snapshot,
                        out_path=out_path,
                        refresh_lolalytics=refresh_lolalytics,
                        mode=mode,
                        tier=tier,
                        min_champions_analysed=min_champions_analysed,
                    )
                    self._send_json({"ok": True, "snapshot": str(snapshot), "data": result})
                    return
                if parsed.path == "/api/recommend-snapshot":
                    body = self._read_body()
                    snapshot = _safe_snapshot_path(str(body.get("snapshot") or ""))
                    result = recommend_from_snapshot(
                        snapshot,
                        out_path=out_path,
                        refresh_lolalytics=refresh_lolalytics,
                        mode=mode,
                        tier=tier,
                        min_champions_analysed=min_champions_analysed,
                    )
                    self._send_json({"ok": True, "snapshot": str(snapshot), "data": result})
                    return
                self._send_error_json("not found", status=404)
            except Exception as exc:
                self._send_error_json(str(exc), status=500)

        def _serve_static(self, request_path: str) -> None:
            rel = "index.html" if request_path in {"", "/"} else unquote(request_path.lstrip("/"))
            target = (static_root / rel).resolve()
            root = static_root.resolve()
            if root != target and root not in target.parents:
                self.send_error(403)
                return
            if not target.exists() or not target.is_file():
                self.send_error(404)
                return
            content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
            body = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def serve(
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    out_path: str | Path = DEFAULT_OUT,
    static_root: str | Path = WEB_ROOT,
    mode: str = "aram",
    tier: str = DEFAULT_TIER,
    min_champions_analysed: int = 1_000_000,
    refresh_lolalytics: bool = False,
) -> None:
    handler = _make_handler(
        out_path=Path(out_path),
        static_root=Path(static_root),
        mode=mode,
        tier=tier,
        min_champions_analysed=min_champions_analysed,
        refresh_lolalytics=refresh_lolalytics,
    )
    httpd = ThreadingHTTPServer((host, port), handler)
    print(f"[ok] ui -> http://{host}:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[ok] server stopped")
    finally:
        httpd.server_close()
