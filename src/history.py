from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_HISTORY_PATH = Path("data/history/assistant.db")


def route_key(route: dict[str, Any]) -> str:
    return "-".join(str(int(item["item_id"])) for item in route.get("items", []) if item.get("item_id") is not None)


def _connect(path: str | Path = DEFAULT_HISTORY_PATH) -> sqlite3.Connection:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(target, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS recommendations (
            match_key TEXT PRIMARY KEY,
            generated_at TEXT NOT NULL,
            champion TEXT NOT NULL,
            champion_slug TEXT NOT NULL,
            allies_json TEXT NOT NULL,
            enemies_json TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            outcome INTEGER,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS route_feedback (
            match_key TEXT NOT NULL,
            route_key TEXT NOT NULL,
            sentiment REAL NOT NULL,
            label TEXT NOT NULL,
            item_ids_json TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (match_key, route_key),
            FOREIGN KEY (match_key) REFERENCES recommendations(match_key) ON DELETE CASCADE
        );
        """
    )
    return connection


def record_recommendation(result: dict[str, Any], path: str | Path = DEFAULT_HISTORY_PATH) -> None:
    session = result.get("session") or {}
    match_key = str(session.get("match_key") or "")
    if not match_key:
        raise ValueError("recommendation has no match key")
    active = result.get("active_player") or {}
    champion = str(active.get("champion_id") or active.get("champion_name") or "unknown")
    champion_slug = str(active.get("champion_slug") or champion).lower()
    timestamp = str(session.get("generated_at") or datetime.now(timezone.utc).astimezone().isoformat())
    allies = result.get("ally_team") or []
    enemies = result.get("enemy_team") or []
    with _connect(path) as connection:
        connection.execute(
            """
            INSERT INTO recommendations (
                match_key, generated_at, champion, champion_slug, allies_json,
                enemies_json, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(match_key) DO UPDATE SET
                generated_at=excluded.generated_at,
                champion=excluded.champion,
                champion_slug=excluded.champion_slug,
                allies_json=excluded.allies_json,
                enemies_json=excluded.enemies_json,
                payload_json=excluded.payload_json
            """,
            (
                match_key,
                timestamp,
                champion,
                champion_slug,
                json.dumps(allies, ensure_ascii=False),
                json.dumps(enemies, ensure_ascii=False),
                json.dumps(result, ensure_ascii=False),
                datetime.now(timezone.utc).astimezone().isoformat(),
            ),
        )


def _load_payload(connection: sqlite3.Connection, match_key: str) -> dict[str, Any]:
    row = connection.execute(
        "SELECT payload_json FROM recommendations WHERE match_key = ?",
        (match_key,),
    ).fetchone()
    if row is None:
        raise KeyError(f"unknown recommendation: {match_key}")
    return json.loads(row["payload_json"])


def stored_recommendation(
    match_key: str,
    path: str | Path = DEFAULT_HISTORY_PATH,
) -> dict[str, Any] | None:
    with _connect(path) as connection:
        row = connection.execute(
            "SELECT payload_json FROM recommendations WHERE match_key = ?",
            (match_key,),
        ).fetchone()
    return json.loads(row["payload_json"]) if row is not None else None


def record_route_feedback(
    match_key: str,
    selected_route_key: str,
    sentiment: float,
    path: str | Path = DEFAULT_HISTORY_PATH,
) -> dict[str, Any]:
    if not -1.0 <= float(sentiment) <= 1.0:
        raise ValueError("sentiment must be between -1 and 1")
    with _connect(path) as connection:
        payload = _load_payload(connection, match_key)
        route = next(
            (
                candidate
                for candidate in payload.get("build", {}).get("routes", [])
                if route_key(candidate) == selected_route_key
            ),
            None,
        )
        if route is None:
            raise ValueError("route does not belong to the stored recommendation")
        if float(sentiment) == 0.0:
            connection.execute(
                "DELETE FROM route_feedback WHERE match_key = ? AND route_key = ?",
                (match_key, selected_route_key),
            )
        else:
            item_ids = [int(item["item_id"]) for item in route.get("items", [])]
            connection.execute(
                """
                INSERT INTO route_feedback (
                    match_key, route_key, sentiment, label, item_ids_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(match_key, route_key) DO UPDATE SET
                    sentiment=excluded.sentiment,
                    label=excluded.label,
                    item_ids_json=excluded.item_ids_json,
                    updated_at=excluded.updated_at
                """,
                (
                    match_key,
                    selected_route_key,
                    float(sentiment),
                    str(route.get("label") or ""),
                    json.dumps(item_ids),
                    datetime.now(timezone.utc).astimezone().isoformat(),
                ),
            )
        return route


def record_outcome(
    match_key: str,
    outcome: int | None,
    path: str | Path = DEFAULT_HISTORY_PATH,
) -> None:
    if outcome not in (None, -1, 1):
        raise ValueError("outcome must be 1, -1, or null")
    with _connect(path) as connection:
        cursor = connection.execute(
            "UPDATE recommendations SET outcome = ? WHERE match_key = ?",
            (outcome, match_key),
        )
        if cursor.rowcount != 1:
            raise KeyError(f"unknown recommendation: {match_key}")


def learned_item_adjustments(
    path: str | Path = DEFAULT_HISTORY_PATH,
) -> tuple[dict[int, float], int]:
    with _connect(path) as connection:
        rows = connection.execute(
            "SELECT sentiment, item_ids_json FROM route_feedback"
        ).fetchall()
    totals: dict[int, float] = {}
    counts: dict[int, int] = {}
    for row in rows:
        sentiment = float(row["sentiment"])
        for raw_item_id in json.loads(row["item_ids_json"]):
            item_id = int(raw_item_id)
            totals[item_id] = totals.get(item_id, 0.0) + sentiment
            counts[item_id] = counts.get(item_id, 0) + 1
    adjustments = {
        item_id: round(max(-1.2, min(1.2, 1.8 * total / (counts[item_id] + 3))), 3)
        for item_id, total in totals.items()
        if not math.isclose(total, 0.0)
    }
    return adjustments, len(rows)


def list_history(
    path: str | Path = DEFAULT_HISTORY_PATH,
    *,
    limit: int = 30,
) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 200))
    with _connect(path) as connection:
        rows = connection.execute(
            """
            SELECT match_key, generated_at, champion, champion_slug, allies_json,
                   enemies_json, outcome, payload_json
            FROM recommendations
            ORDER BY generated_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        feedback_rows = connection.execute(
            "SELECT match_key, route_key, sentiment, label FROM route_feedback"
        ).fetchall()
    feedback_by_match: dict[str, list[dict[str, Any]]] = {}
    for feedback in feedback_rows:
        feedback_by_match.setdefault(feedback["match_key"], []).append(
            {
                "route_key": feedback["route_key"],
                "sentiment": feedback["sentiment"],
                "label": feedback["label"],
            }
        )
    history = []
    for row in rows:
        payload = json.loads(row["payload_json"])
        routes = payload.get("build", {}).get("routes") or []
        history.append(
            {
                "match_key": row["match_key"],
                "generated_at": row["generated_at"],
                "champion": row["champion"],
                "champion_slug": row["champion_slug"],
                "allies": json.loads(row["allies_json"]),
                "enemies": json.loads(row["enemies_json"]),
                "outcome": row["outcome"],
                "routes": [
                    {
                        "route_key": route_key(route),
                        "label": route.get("label"),
                        "item_ids": [int(item["item_id"]) for item in route.get("items", [])],
                    }
                    for route in routes
                ],
                "feedback": feedback_by_match.get(row["match_key"], []),
            }
        )
    return history


def history_metrics(path: str | Path = DEFAULT_HISTORY_PATH) -> dict[str, int]:
    with _connect(path) as connection:
        recommendations = connection.execute("SELECT COUNT(*) FROM recommendations").fetchone()[0]
        feedback = connection.execute("SELECT COUNT(*) FROM route_feedback").fetchone()[0]
        wins = connection.execute("SELECT COUNT(*) FROM recommendations WHERE outcome = 1").fetchone()[0]
        losses = connection.execute("SELECT COUNT(*) FROM recommendations WHERE outcome = -1").fetchone()[0]
    return {
        "recommendations": int(recommendations),
        "feedback": int(feedback),
        "wins": int(wins),
        "losses": int(losses),
    }
