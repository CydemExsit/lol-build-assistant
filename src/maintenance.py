from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path


CANONICAL_PROCESSED_FILES = {"live_recommendation.json", "live_recommendation.md"}


@dataclass(frozen=True)
class CleanupEntry:
    path: Path
    size_bytes: int
    reason: str


@dataclass(frozen=True)
class CleanupPlan:
    root: Path
    entries: tuple[CleanupEntry, ...]

    @property
    def total_bytes(self) -> int:
        return sum(entry.size_bytes for entry in self.entries)


def _path_size(path: Path) -> int:
    if path.is_symlink() or path.is_file():
        try:
            return path.stat().st_size
        except OSError:
            return 0
    return sum(
        child.stat().st_size
        for child in path.rglob("*")
        if child.is_file() and not child.is_symlink()
    )


def _is_within(root: Path, path: Path) -> bool:
    resolved = path.resolve()
    return resolved != root and root in resolved.parents


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None


def _is_empty_json_cache(path: Path) -> bool:
    payload = _read_json(path)
    return payload in (None, [], {})


def _is_obsolete_sets_cache(path: Path) -> bool:
    if not path.name.endswith("_sets5.json"):
        return False
    payload = _read_json(path)
    return isinstance(payload, list) and bool(payload) and any(
        not isinstance(row, dict) or row.get("data_source") != "build_itemset_api"
        for row in payload
    )


def build_cleanup_plan(
    root: str | Path = ".",
    *,
    keep_snapshots: int = 5,
) -> CleanupPlan:
    if keep_snapshots < 0:
        raise ValueError("keep_snapshots must be zero or greater")

    workspace = Path(root).resolve()
    candidates: dict[Path, str] = {}

    def add(path: Path, reason: str) -> None:
        if path.exists() and _is_within(workspace, path):
            # Keep the lexical path so applying a plan unlinks a symlink instead
            # of accidentally operating on its resolved target.
            candidates[path.absolute()] = reason

    raw_root = workspace / "data" / "raw"
    if raw_root.exists():
        snapshots = sorted(
            (path for path in raw_root.glob("live_*") if path.is_dir()),
            key=lambda path: path.name,
            reverse=True,
        )
        for path in snapshots[keep_snapshots:]:
            add(path, f"snapshot retention: keep latest {keep_snapshots}")
        for path in raw_root.iterdir():
            if path.is_file():
                add(path, "legacy raw artifact")

    cache_root = workspace / "data" / "cache"
    if cache_root.exists():
        for path in cache_root.glob("*.html"):
            add(path, "re-creatable LoLalytics HTML cache")
        for path in cache_root.glob("*.json"):
            if _is_empty_json_cache(path):
                add(path, "empty JSON cache")
            elif _is_obsolete_sets_cache(path):
                add(path, "obsolete page-scroll sets cache")

    processed_root = workspace / "data" / "processed"
    if processed_root.exists():
        for path in processed_root.iterdir():
            if path.is_file() and path.name not in CANONICAL_PROCESSED_FILES:
                add(path, "non-canonical generated output")

    runtime_root = workspace / "data" / "runtime"
    if runtime_root.exists():
        for path in runtime_root.iterdir():
            if path.is_file() and path.name != "status.json":
                add(path, "runtime log or QA artifact")

    for parent in (workspace / "src", workspace / "tests", workspace / "scripts"):
        if parent.exists():
            for path in parent.rglob("__pycache__"):
                add(path, "Python bytecode cache")
    add(workspace / ".pytest_cache", "pytest cache")

    entries = tuple(
        CleanupEntry(path=path, size_bytes=_path_size(path), reason=reason)
        for path, reason in sorted(candidates.items(), key=lambda item: str(item[0]).lower())
    )
    return CleanupPlan(root=workspace, entries=entries)


def apply_cleanup_plan(plan: CleanupPlan) -> CleanupPlan:
    removed: list[CleanupEntry] = []
    for entry in plan.entries:
        path = entry.path.absolute()
        if not _is_within(plan.root, path):
            raise ValueError(f"refusing to remove path outside workspace: {path}")
        if not path.exists():
            continue
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)
        removed.append(entry)
    return CleanupPlan(root=plan.root, entries=tuple(removed))


def format_bytes(size: int) -> str:
    if size >= 1024**2:
        return f"{size / 1024**2:.2f} MiB"
    if size >= 1024:
        return f"{size / 1024:.1f} KiB"
    return f"{size} B"
