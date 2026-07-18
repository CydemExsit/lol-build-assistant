import json
import threading
import urllib.request

from src.server import create_server
from src.service import RecommendationService


def test_server_exposes_runtime_status(tmp_path):
    web_root = tmp_path / "web"
    web_root.mkdir()
    (web_root / "index.html").write_text("ok", encoding="utf-8")
    service = RecommendationService(
        out_path=tmp_path / "recommendation.json",
        out_markdown_path=tmp_path / "recommendation.md",
        history_path=tmp_path / "history.db",
        status_path=tmp_path / "status.json",
    )
    server = create_server(service, port=0, static_root=web_root)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        with urllib.request.urlopen(f"http://{host}:{port}/api/status", timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))
        assert payload["ok"] is True
        assert payload["status"]["state"] == "offline"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
