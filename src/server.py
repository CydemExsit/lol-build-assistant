from __future__ import annotations

import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from .lolalytics import DEFAULT_TIER
from .runtime_state import write_status
from .service import RecommendationService


DEFAULT_OUT = Path("data/processed/live_recommendation.json")
WEB_ROOT = Path("web")
MAX_BODY_BYTES = 64 * 1024


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_snapshot_path(value: str) -> Path:
    root = Path("data/raw").resolve()
    target = Path(value).resolve()
    if root != target and root not in target.parents:
        raise ValueError("snapshot path must be inside data/raw")
    if not target.exists():
        raise ValueError("snapshot does not exist")
    return target


def _list_snapshots() -> list[dict[str, str]]:
    root = Path("data/raw")
    if not root.exists():
        return []
    return [
        {"name": path.name, "path": str(path)}
        for path in sorted(root.glob("live_*"), reverse=True)
        if path.is_dir()
    ]


def _make_handler(*, service: RecommendationService, static_root: Path):
    class Handler(BaseHTTPRequestHandler):
        server_version = "LolBuildAssistant/1.0"

        def log_message(self, fmt: str, *args: object) -> None:
            print(f"[server] {self.address_string()} - {fmt % args}")

        def _send_json(self, data: Any, status: int = 200) -> None:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_error_json(self, message: str, status: int = 500) -> None:
            self._send_json({"ok": False, "error": message}, status=status)

        def _read_body(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY_BYTES:
                raise ValueError("request body is too large")
            if length <= 0:
                return {}
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            if not isinstance(payload, dict):
                raise ValueError("request body must be a JSON object")
            return payload

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            if path == "/api/recommendation":
                data = _read_json(service.out_path) if service.out_path.exists() else None
                self._send_json({"ok": True, "data": data})
                return
            if path == "/api/status":
                self._send_json({"ok": True, "status": service.status()})
                return
            if path == "/api/health":
                self._send_json({"ok": True, "health": service.health()})
                return
            if path == "/api/history":
                query = parse_qs(parsed.query)
                limit = int((query.get("limit") or [30])[0])
                self._send_json({"ok": True, "history": service.history(limit=limit)})
                return
            if path == "/api/snapshots":
                self._send_json({"ok": True, "snapshots": _list_snapshots()})
                return
            self._serve_static(path)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            try:
                if parsed.path == "/api/recommend-live":
                    snapshot, result = service.capture_and_recommend()
                    self._send_json({"ok": True, "snapshot": str(snapshot), "data": result})
                    return
                if parsed.path == "/api/recommend-snapshot":
                    body = self._read_body()
                    snapshot = _safe_snapshot_path(str(body.get("snapshot") or ""))
                    result = service.recommend_snapshot(snapshot)
                    self._send_json({"ok": True, "snapshot": str(snapshot), "data": result})
                    return
                if parsed.path == "/api/feedback":
                    body = self._read_body()
                    route = service.feedback(
                        str(body.get("match_key") or ""),
                        str(body.get("route_key") or ""),
                        float(body.get("sentiment", 0)),
                    )
                    self._send_json({"ok": True, "route": route})
                    return
                if parsed.path == "/api/outcome":
                    body = self._read_body()
                    raw_outcome = body.get("outcome")
                    outcome = None if raw_outcome is None else int(raw_outcome)
                    service.outcome(str(body.get("match_key") or ""), outcome)
                    self._send_json({"ok": True})
                    return
                self._send_error_json("not found", status=404)
            except (ValueError, KeyError, json.JSONDecodeError) as exc:
                self._send_error_json(str(exc), status=400)
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
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def create_server(
    service: RecommendationService,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    static_root: str | Path = WEB_ROOT,
) -> ThreadingHTTPServer:
    handler = _make_handler(service=service, static_root=Path(static_root))
    return ThreadingHTTPServer((host, port), handler)


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
    service: RecommendationService | None = None,
) -> None:
    active_service = service or RecommendationService(
        out_path=out_path,
        mode=mode,
        tier=tier,
        min_champions_analysed=min_champions_analysed,
        refresh_lolalytics=refresh_lolalytics,
    )
    write_status(
        {
            "state": "manual",
            "message": "瀏覽器介面已啟動，背景偵測未開啟",
            "service_mode": "manual",
        },
        active_service.status_path,
    )
    httpd = create_server(active_service, host=host, port=port, static_root=static_root)
    print(f"[ok] ui -> http://{host}:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[ok] server stopped")
    finally:
        httpd.server_close()
