import json
from .algo import load_winning_items, load_built_sets, pick_build

def run(winning_csv: str, sets_csv: str, out_json: str, *, explain: bool, topk: int, cover: float) -> None:
    winning = load_winning_items(winning_csv)
    sets = load_built_sets(sets_csv)
    if not winning or not sets:
        raise SystemExit(f"[error] empty input: winning={len(winning)} sets={len(sets)}. Please re-run scraper.")
    result = pick_build(winning, sets, explain=explain, topk=topk, cover=cover)
    payload = {
        "spec": {"mode": "ARAM", "tier": "d2_plus", "window": "7d"},
        "build": {"boots": result.boots, "order": result.order},
        "rationale": result.rationale,
    }
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
