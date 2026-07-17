from __future__ import annotations

import html as html_lib
import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_BASE_URL = "https://lolalytics.com"
DEFAULT_ITEM_SET_API_URL = "https://a1.lolalytics.com/mega/"
DEFAULT_MODE = "aram"
DEFAULT_TIER = "gold_plus"
DEFAULT_PATCH = "7"
SECTION_ORDER = ["Starting Items", "Core Build", "Item 4", "Item 5", "Item 6", "LEGEND:"]
BANNED_SET_ITEM_IDS = {2003, 2031, 2138, 2139, 2140, 1055, 1054, 1056, 1082, 1101, 1102, 1103, 1104, 1042, 1036}
IMG_RE = re.compile(
    r"<img[^>]+item64/(?P<id>\d+)\.webp[^>]+alt=\"(?P<name>[^\"]*)\"[^>]*>",
    re.DOTALL,
)
DATA_ID_IMG_RE = re.compile(
    r"<img[^>]+item64/(?P<id>\d+)\.webp[^>]+alt=\"(?P<name>[^\"]*)\"[^>]*data-id=\"(?P=id)\"[^>]*>",
    re.DOTALL,
)


@dataclass(frozen=True)
class LolalyticsItem:
    item_id: int
    name: str
    win_rate: float | None = None
    games: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "name": self.name,
            "win_rate": self.win_rate,
            "games": self.games,
        }


@dataclass(frozen=True)
class LolalyticsBuiltSet:
    item_ids: list[int]
    item_names: list[str]
    win_rate: float
    pick_rate: float
    games: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_ids": self.item_ids,
            "item_names": self.item_names,
            "win_rate": self.win_rate,
            "pick_rate": self.pick_rate,
            "games": self.games,
        }


def lolalytics_url(
    champion_slug: str,
    *,
    mode: str = DEFAULT_MODE,
    tier: str = DEFAULT_TIER,
    patch: str = DEFAULT_PATCH,
    lane: str | None = None,
) -> str:
    mode = (mode or "").lower()
    path = f"/lol/{champion_slug}/build/"
    if mode and mode not in {"classic", "ranked", "sr", "summoners_rift"}:
        path = f"/lol/{champion_slug}/{mode}/build/"

    params = []
    if tier:
        params.append(f"tier={tier}")
    if patch:
        params.append(f"patch={patch}")
    if lane and mode in {"", "classic", "ranked", "sr", "summoners_rift"}:
        params.append(f"lane={lane.lower()}")
    query = "?" + "&".join(params) if params else ""
    return f"{DEFAULT_BASE_URL}{path}{query}"


def cache_path_for(
    champion_slug: str,
    cache_dir: str | Path = "data/cache",
    *,
    mode: str = DEFAULT_MODE,
    tier: str = DEFAULT_TIER,
    patch: str = DEFAULT_PATCH,
) -> Path:
    return Path(cache_dir) / f"lolalytics_{champion_slug}_{mode}_{tier}_{patch}.html"


def build_summary_cache_path_for(
    champion_slug: str,
    cache_dir: str | Path = "data/cache",
    *,
    mode: str = DEFAULT_MODE,
    tier: str = DEFAULT_TIER,
    patch: str = DEFAULT_PATCH,
) -> Path:
    html_path = cache_path_for(champion_slug, cache_dir, mode=mode, tier=tier, patch=patch)
    return html_path.with_name(f"{html_path.stem}_build.json")


def built_sets_cache_path_for(
    champion_slug: str,
    cache_dir: str | Path = "data/cache",
    *,
    mode: str = DEFAULT_MODE,
    tier: str = DEFAULT_TIER,
    patch: str = DEFAULT_PATCH,
) -> Path:
    return Path(cache_dir) / f"lolalytics_{champion_slug}_{mode}_{tier}_{patch}_sets5.json"


def boot_pair_stats_cache_path_for(
    champion_slug: str,
    cache_dir: str | Path = "data/cache",
    *,
    mode: str = DEFAULT_MODE,
    tier: str = DEFAULT_TIER,
    patch: str = DEFAULT_PATCH,
) -> Path:
    return Path(cache_dir) / f"lolalytics_{champion_slug}_{mode}_{tier}_{patch}_boots_ab2.json"


def boot_stats_cache_path_for(
    champion_slug: str,
    cache_dir: str | Path = "data/cache",
    *,
    mode: str = DEFAULT_MODE,
    tier: str = DEFAULT_TIER,
    patch: str = DEFAULT_PATCH,
) -> Path:
    return Path(cache_dir) / f"lolalytics_{champion_slug}_{mode}_{tier}_{patch}_boots.json"


def item_stats_cache_path_for(
    champion_slug: str,
    cache_dir: str | Path = "data/cache",
    *,
    table: str,
    mode: str = DEFAULT_MODE,
    tier: str = DEFAULT_TIER,
    patch: str = DEFAULT_PATCH,
) -> Path:
    safe_table = re.sub(r"[^a-z0-9]+", "_", table.lower()).strip("_")
    return Path(cache_dir) / f"lolalytics_{champion_slug}_{mode}_{tier}_{patch}_{safe_table}.json"


def fetch_build_html(
    champion_slug: str,
    *,
    cache_dir: str | Path = "data/cache",
    refresh: bool = False,
    mode: str = DEFAULT_MODE,
    tier: str = DEFAULT_TIER,
    patch: str = DEFAULT_PATCH,
) -> Path:
    target = cache_path_for(champion_slug, cache_dir, mode=mode, tier=tier, patch=patch)
    if target.exists() and not refresh:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    source_url = lolalytics_url(champion_slug, mode=mode, tier=tier, patch=patch)
    req = urllib.request.Request(
        source_url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0 Safari/537.36"
            )
        },
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        body = response.read().decode("utf-8", errors="replace")
    target.write_text(body, encoding="utf-8")
    (target.with_suffix(".meta.json")).write_text(
        json.dumps(
            {
                "source_url": source_url,
                "fetched_at": datetime.now(timezone.utc).astimezone().isoformat(),
                "mode": mode,
                "tier": tier,
                "patch": patch,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return target


def _section_slice(markup: str, label: str) -> str:
    start = markup.find(label)
    if start < 0:
        return ""
    end = len(markup)
    for next_label in SECTION_ORDER[SECTION_ORDER.index(label) + 1 :] if label in SECTION_ORDER else []:
        idx = markup.find(next_label, start + len(label))
        if idx >= 0:
            end = min(end, idx)
    return markup[start:end]


def _parse_stats(after_img: str) -> tuple[float | None, int | None]:
    pct_match = re.search(r"<!--t=[^>]+-->\s*([\d.]+)\s*<!---->\s*%", after_img)
    if not pct_match:
        pct_match = re.search(r">\s*([\d.]+)\s*</span>\s*%?", after_img)
    games_match = re.search(r">\s*([\d,]+)\s*</span>", after_img)
    win_rate = float(pct_match.group(1)) / 100.0 if pct_match else None
    games = int(games_match.group(1).replace(",", "")) if games_match else None
    return win_rate, games


def _items_from_section(markup: str) -> list[LolalyticsItem]:
    matches = list(IMG_RE.finditer(markup))
    out: list[LolalyticsItem] = []
    seen: set[int] = set()
    for idx, match in enumerate(matches):
        item_id = int(match.group("id"))
        if item_id in seen:
            continue
        seen.add(item_id)
        stop = matches[idx + 1].start() if idx + 1 < len(matches) else min(len(markup), match.end() + 1000)
        win_rate, games = _parse_stats(markup[match.end() : stop])
        out.append(
            LolalyticsItem(
                item_id=item_id,
                name=html_lib.unescape(match.group("name")),
                win_rate=win_rate,
                games=games,
            )
        )
    return out


def parse_build_html(markup: str) -> dict[str, Any]:
    title = re.search(r"<title[^>]*>(.*?)</title>", markup, re.DOTALL)
    patch = re.search(r"Patch</div>.*?<!--t=[^>]+-->([\d.]+)", markup, re.DOTALL)
    if not patch:
        patch = re.search(r"LoL Patch\s+([\d.]+)", markup, re.DOTALL)
    analysed = re.search(r"Champions Analysed:\s*<!--t=[^>]+-->\s*([\d,]+)", markup, re.DOTALL)
    sections = {
        label: [item.to_dict() for item in _items_from_section(_section_slice(markup, label))]
        for label in ["Starting Items", "Core Build", "Item 4", "Item 5", "Item 6"]
    }

    candidate_items: list[dict[str, Any]] = []
    seen: set[int] = set()
    for match in DATA_ID_IMG_RE.finditer(markup):
        item_id = int(match.group("id"))
        if item_id in seen:
            continue
        seen.add(item_id)
        candidate_items.append({"item_id": item_id, "name": html_lib.unescape(match.group("name"))})

    return {
        "title": html_lib.unescape(title.group(1)) if title else None,
        "patch": patch.group(1) if patch else None,
        "champions_analysed": int(analysed.group(1).replace(",", "")) if analysed else None,
        "sections": sections,
        "candidate_items": candidate_items,
    }


def load_or_fetch_build(
    champion_slug: str,
    *,
    cache_dir: str | Path = "data/cache",
    refresh: bool = False,
    mode: str = DEFAULT_MODE,
    tier: str = DEFAULT_TIER,
    patch: str = DEFAULT_PATCH,
) -> dict[str, Any]:
    summary_path = build_summary_cache_path_for(
        champion_slug,
        cache_dir,
        mode=mode,
        tier=tier,
        patch=patch,
    )
    if summary_path.exists() and not refresh:
        try:
            cached = json.loads(summary_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            cached = None
        if isinstance(cached, dict) and isinstance(cached.get("sections"), dict):
            cached["cache_path"] = str(summary_path)
            return cached

    path = fetch_build_html(champion_slug, cache_dir=cache_dir, refresh=refresh, mode=mode, tier=tier, patch=patch)
    parsed = parse_build_html(path.read_text(encoding="utf-8"))
    parsed["source_url"] = lolalytics_url(champion_slug, mode=mode, tier=tier, patch=patch)
    parsed["params"] = {"mode": mode, "tier": tier, "patch": patch}
    summary_path.write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
    parsed["cache_path"] = str(summary_path)
    return parsed


def load_best_build(
    champion_slug: str,
    *,
    cache_dir: str | Path = "data/cache",
    refresh: bool = False,
    mode: str = DEFAULT_MODE,
    tier: str = DEFAULT_TIER,
    patches: tuple[str, ...] = ("7", "14", "30"),
    min_champions_analysed: int = 1_000_000,
) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    for patch in patches:
        data = load_or_fetch_build(
            champion_slug,
            cache_dir=cache_dir,
            refresh=refresh,
            mode=mode,
            tier=tier,
            patch=patch,
        )
        attempts.append(
            {
                "params": data["params"],
                "champions_analysed": data.get("champions_analysed"),
                "source_url": data.get("source_url"),
            }
        )
        if (data.get("champions_analysed") or 0) >= min_champions_analysed:
            data["fallback_attempts"] = attempts
            return data
    data["fallback_attempts"] = attempts
    return data


def _to_float(value: Any) -> float | None:
    try:
        return float(str(value).replace(",", "").replace("%", "").strip())
    except Exception:
        return None


def _to_int(value: Any) -> int | None:
    try:
        return int(float(str(value).replace(",", "").strip()))
    except Exception:
        return None


def item_sets_api_url(
    champion_slug: str,
    *,
    mode: str = DEFAULT_MODE,
    tier: str = DEFAULT_TIER,
    patch: str = DEFAULT_PATCH,
) -> str:
    query = urllib.parse.urlencode(
        {
            "ep": "build-itemset",
            "v": "1",
            "patch": patch,
            "c": champion_slug,
            "lane": "all",
            "tier": tier,
            "queue": mode,
            "region": "all",
        }
    )
    return f"{DEFAULT_ITEM_SET_API_URL}?{query}"


def _fetch_item_sets_api_payload(
    champion_slug: str,
    *,
    mode: str,
    tier: str,
    patch: str,
) -> dict[str, Any]:
    request = urllib.request.Request(
        item_sets_api_url(champion_slug, mode=mode, tier=tier, patch=patch),
        headers={
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/121.0",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    response_meta = payload.get("response") if isinstance(payload, dict) else None
    if not isinstance(response_meta, dict) or not response_meta.get("valid"):
        return {}
    return payload


def _normalize_item_sets_api_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    item_sets = payload.get("itemSets")
    if not isinstance(item_sets, dict):
        return []

    total_games = 0
    for item_count in range(1, 6):
        rows = item_sets.get(f"itemSet{item_count}") or []
        for row in rows:
            games = _to_int(row[1]) if isinstance(row, list) and len(row) >= 2 else None
            if games and games > 0:
                total_games += games
    if total_games <= 0:
        return []

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in item_sets.get("itemSet5") or []:
        if not isinstance(row, list) or len(row) < 3:
            continue
        item_ids = [_to_int(value) for value in str(row[0]).split("_")]
        games = _to_int(row[1])
        wins = _to_int(row[2])
        if (
            len(item_ids) != 5
            or any(item_id is None for item_id in item_ids)
            or len(set(item_ids)) != 5
            or any(item_id in BANNED_SET_ITEM_IDS for item_id in item_ids)
            or games is None
            or games <= 0
            or wins is None
            or wins < 0
            or wins > games
        ):
            continue
        normalized_ids = [int(item_id) for item_id in item_ids if item_id is not None]
        key = "|".join(str(item_id) for item_id in normalized_ids)
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                **LolalyticsBuiltSet(
                    item_ids=normalized_ids,
                    item_names=[str(item_id) for item_id in normalized_ids],
                    win_rate=wins / games,
                    pick_rate=games / total_games,
                    games=games,
                ).to_dict(),
                "data_source": "build_itemset_api",
            }
        )
    return out


def _item_id_from_src(src: str) -> int | None:
    match = re.search(r"item64/(\d+)\.webp", src or "")
    return int(match.group(1)) if match else None


def _scroll_collect_stat_cards_script() -> str:
    return """
    async ({label}) => {
      const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
      const norm = (value) => (value || '').replace(/\\s+/g, ' ').trim();
      const findTable = () => {
        const labels = Array.from(document.querySelectorAll('div'))
          .filter((el) => norm(el.innerText) === label);
        for (const labelEl of labels) {
          let row = labelEl;
          for (let depth = 0; row && depth < 7; depth++, row = row.parentElement) {
            const text = row.innerText || '';
            if (
              text.includes('Win Rate') &&
              text.includes('Pick Rate') &&
              text.includes('Games') &&
              row.querySelector('.overflow-x-scroll')
            ) {
              return row;
            }
          }
        }
        return null;
      };
      const table = findTable();
      const scroller = table?.querySelector('.overflow-x-scroll');
      if (!scroller) return [];
      table.scrollIntoView({block: 'center'});
      await sleep(350);

      const seen = new Map();
      const collect = () => {
        for (const img of Array.from(scroller.querySelectorAll('img[src*="/item64/"]'))) {
          const idMatch = (img.getAttribute('src') || '').match(/item64\\/(\\d+)\\.webp/);
          if (!idMatch) continue;
          let card = img.parentElement;
          for (let depth = 0; card && depth < 7 && scroller.contains(card); depth++, card = card.parentElement) {
            const stats = Array.from(card.querySelectorAll('div.my-1'))
              .map((el) => (el.textContent || '').trim())
              .filter(Boolean)
              .slice(0, 3);
            if (stats.length < 3) continue;
            const timeEl = Array.from(card.children || [])
              .filter((el) => !el.querySelector?.('img') && !(String(el.className || '').includes('my-1')))
              .at(-1);
            const itemId = Number(idMatch[1]);
            if (!seen.has(itemId)) {
              seen.set(itemId, {
                item_id: itemId,
                item_name: img.alt || '',
                stats,
                time: (timeEl?.textContent || '').trim()
              });
            }
            break;
          }
        }
      };

      const maxScroll = Math.max(0, scroller.scrollWidth - scroller.clientWidth);
      const step = Math.max(240, Math.floor(scroller.clientWidth * 0.75));
      for (let pos = 0; pos <= maxScroll; pos += step) {
        scroller.scrollLeft = pos;
        await sleep(90);
        collect();
      }
      scroller.scrollLeft = maxScroll;
      await sleep(140);
      collect();
      return Array.from(seen.values());
    }
    """


def _scroll_collect_sets_script() -> str:
    return """
    async () => {
      const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
      const norm = (value) => (value || '').replace(/\\s+/g, ' ').trim();
      const numeric = (value) => /^\\d+(?:\\.\\d+)?(?:,\\d{3})*$/.test((value || '').trim());
      const findSection = () => {
        const label = Array.from(document.querySelectorAll('div'))
          .find((el) => norm(el.innerText) === 'Sets With Boots');
        const header = label?.parentElement;
        const parent = header?.parentElement;
        const index = parent && header ? Array.from(parent.children).indexOf(header) : -1;
        return index >= 0 ? parent.children[index + 2] || null : null;
      };
      const collectFrom = (scroller) => {
        const rows = [];
        const seen = new Set();
        for (const img0 of Array.from(scroller.querySelectorAll('img[data-id^="0_"]'))) {
          let row = img0.parentElement;
          for (let depth = 0; row && depth < 8 && scroller.contains(row); depth++, row = row.parentElement) {
            const imgs = [];
            for (let k = 0; k < 5; k++) {
              const img = row.querySelector(`img[data-id^="${k}_"]`);
              if (!img) {
                imgs.length = 0;
                break;
              }
              const rawId = img.getAttribute('data-id') || '';
              imgs.push({
                item_id: Number(rawId.split('_')[1]),
                name: img.alt || ''
              });
            }
            if (imgs.length !== 5) continue;
            const stats = Array.from(row.querySelectorAll('div.my-1'))
              .map((el) => (el.textContent || '').trim())
              .filter(numeric)
              .slice(0, 3);
            if (stats.length < 3) continue;
            const key = imgs.map((img) => img.item_id).join('|') + ':' + stats.join('|');
            if (seen.has(key)) break;
            seen.add(key);
            rows.push({
              item_ids: imgs.map((img) => img.item_id),
              item_names: imgs.map((img) => img.name),
              stats
            });
            break;
          }
        }
        return rows;
      };

      let section = findSection();
      if (!section) return [];
      section.scrollIntoView({block: 'center'});
      let scroller = null;
      for (let attempt = 0; attempt < 30; attempt++) {
        await sleep(200);
        section = findSection();
        scroller = section?.querySelector('.overflow-x-scroll');
        if (scroller?.querySelector('img[data-id^="0_"]')) break;
        if (attempt % 5 === 4) section?.scrollIntoView({block: 'center'});
      }
      if (!scroller) return [];
      scroller.scrollLeft = 0;
      await sleep(180);

      const byKey = new Map();
      const collect = () => {
        for (const row of collectFrom(scroller)) {
          const key = row.item_ids.join('|') + ':' + row.stats.join('|');
          byKey.set(key, row);
        }
      };
      collect();
      const maxScroll = Math.max(0, scroller.scrollWidth - scroller.clientWidth);
      const step = Math.max(240, Math.floor(scroller.clientWidth * 0.75));
      for (let pos = 0; pos <= maxScroll; pos += step) {
        scroller.scrollLeft = pos;
        await sleep(85);
        collect();
      }
      scroller.scrollLeft = maxScroll;
      await sleep(140);
      collect();
      return Array.from(byKey.values());
    }
    """


def _normalize_playwright_sets(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        item_ids = [int(x) for x in row.get("item_ids", [])]
        if len(item_ids) != 5 or len(set(item_ids)) != 5 or any(item_id in BANNED_SET_ITEM_IDS for item_id in item_ids):
            continue
        stats = row.get("stats") or []
        win_rate = _to_float(stats[0]) if len(stats) >= 1 else None
        pick_rate = _to_float(stats[1]) if len(stats) >= 2 else None
        games = _to_int(stats[2]) if len(stats) >= 3 else None
        if win_rate is None or pick_rate is None or games is None:
            continue
        key = "|".join(str(x) for x in item_ids)
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                **LolalyticsBuiltSet(
                    item_ids=item_ids,
                    item_names=[html_lib.unescape(str(x)) for x in row.get("item_names", [])],
                    win_rate=win_rate / 100.0,
                    pick_rate=pick_rate / 100.0,
                    games=games,
                ).to_dict(),
                "data_source": "page_scroll",
            }
        )
    return out


def _normalize_playwright_pair_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        item_ids = [int(x) for x in row.get("item_ids", [])]
        if len(item_ids) != 2 or len(set(item_ids)) != 2:
            continue
        stats = row.get("stats") or []
        win_rate = _to_float(stats[0]) if len(stats) >= 1 else None
        pick_rate = _to_float(stats[1]) if len(stats) >= 2 else None
        games = _to_int(stats[2]) if len(stats) >= 3 else None
        if win_rate is None or pick_rate is None or games is None:
            continue
        key = "|".join(str(x) for x in item_ids)
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "item_ids": item_ids,
                "item_names": [html_lib.unescape(str(x)) for x in row.get("item_names", [])],
                "win_rate": win_rate / 100.0,
                "pick_rate": pick_rate / 100.0,
                "games": games,
                "source": "Sets With Boots Actually Built Sets 2+",
            }
        )
    return out


def _normalize_playwright_boot_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[int] = set()
    for row in rows:
        try:
            item_id = int(row.get("item_id"))
        except Exception:
            continue
        if item_id in seen:
            continue
        stats = row.get("stats") or []
        win_rate = _to_float(stats[0]) if len(stats) >= 1 else None
        pick_rate = _to_float(stats[1]) if len(stats) >= 2 else None
        games = _to_int(stats[2]) if len(stats) >= 3 else None
        time = _to_int(row.get("time"))
        if win_rate is None or pick_rate is None or games is None:
            continue
        seen.add(item_id)
        payload = {
            "item_id": item_id,
            "item_name": html_lib.unescape(str(row.get("item_name") or "")),
            "win_rate": win_rate / 100.0,
            "pick_rate": pick_rate / 100.0,
            "games": games,
            "source": "Boots",
        }
        if time is not None:
            payload["time"] = time
        out.append(payload)
    return out


def _normalize_playwright_item_rows(rows: list[dict[str, Any]], *, source: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[int] = set()
    for index, row in enumerate(rows, start=1):
        try:
            item_id = int(row.get("item_id"))
        except Exception:
            continue
        if item_id in seen:
            continue
        stats = row.get("stats") or []
        win_rate = _to_float(stats[0]) if len(stats) >= 1 else None
        pick_rate = _to_float(stats[1]) if len(stats) >= 2 else None
        games = _to_int(stats[2]) if len(stats) >= 3 else None
        time = _to_int(row.get("time"))
        if win_rate is None or pick_rate is None or games is None:
            continue
        seen.add(item_id)
        payload = {
            "item_id": item_id,
            "item_name": html_lib.unescape(str(row.get("item_name") or "")),
            "win_rate": win_rate / 100.0,
            "pick_rate": pick_rate / 100.0,
            "games": games,
            "source": source,
            "rank": index,
        }
        if time is not None:
            payload["time"] = time
        out.append(payload)
    return out


def fetch_boot_stats(
    champion_slug: str,
    *,
    cache_dir: str | Path = "data/cache",
    refresh: bool = False,
    mode: str = DEFAULT_MODE,
    tier: str = DEFAULT_TIER,
    patch: str = DEFAULT_PATCH,
) -> list[dict[str, Any]]:
    target = boot_stats_cache_path_for(champion_slug, cache_dir, mode=mode, tier=tier, patch=patch)
    if target.exists() and not refresh:
        cached = json.loads(target.read_text(encoding="utf-8"))
        if cached:
            return cached

    from playwright.sync_api import sync_playwright

    source_url = lolalytics_url(champion_slug, mode=mode, tier=tier, patch=patch)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1600}, locale="en-US")
        page.goto(source_url, wait_until="domcontentloaded", timeout=60000)
        try:
            page.wait_for_load_state("networkidle", timeout=60000)
        except Exception:
            pass
        rows = page.evaluate(_scroll_collect_stat_cards_script(), {"label": "Boots"})
        browser.close()

    stats = _normalize_playwright_boot_rows(rows)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    return stats


def fetch_item_stats(
    champion_slug: str,
    *,
    table: str,
    cache_dir: str | Path = "data/cache",
    refresh: bool = False,
    mode: str = DEFAULT_MODE,
    tier: str = DEFAULT_TIER,
    patch: str = DEFAULT_PATCH,
) -> list[dict[str, Any]]:
    target = item_stats_cache_path_for(champion_slug, cache_dir, table=table, mode=mode, tier=tier, patch=patch)
    if target.exists() and not refresh:
        cached = json.loads(target.read_text(encoding="utf-8"))
        if cached:
            return cached

    from playwright.sync_api import sync_playwright

    source_url = lolalytics_url(champion_slug, mode=mode, tier=tier, patch=patch)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1600}, locale="en-US")
        page.goto(source_url, wait_until="domcontentloaded", timeout=60000)
        try:
            page.wait_for_load_state("networkidle", timeout=60000)
        except Exception:
            pass
        rows = page.evaluate(_scroll_collect_stat_cards_script(), {"label": table})
        browser.close()

    stats = _normalize_playwright_item_rows(rows, source=table)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    return stats


def fetch_boot_pair_stats(
    champion_slug: str,
    *,
    cache_dir: str | Path = "data/cache",
    refresh: bool = False,
    mode: str = DEFAULT_MODE,
    tier: str = DEFAULT_TIER,
    patch: str = DEFAULT_PATCH,
) -> list[dict[str, Any]]:
    target = boot_pair_stats_cache_path_for(champion_slug, cache_dir, mode=mode, tier=tier, patch=patch)
    if target.exists() and not refresh:
        cached = json.loads(target.read_text(encoding="utf-8"))
        if cached:
            return cached

    from playwright.sync_api import sync_playwright

    source_url = lolalytics_url(champion_slug, mode=mode, tier=tier, patch=patch)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1600}, locale="en-US")
        page.goto(source_url, wait_until="domcontentloaded", timeout=60000)
        try:
            page.wait_for_load_state("networkidle", timeout=60000)
        except Exception:
            pass
        page.locator('[data-type="ab_2"]').first.click(timeout=15000)
        page.wait_for_timeout(1500)
        rows = page.evaluate(
            """
            () => {
              const numeric = (value) => /^\\d+(?:\\.\\d+)?(?:,\\d{3})*$/.test((value || '').trim());
              const label = Array.from(document.querySelectorAll('div'))
                .find((el) => (el.innerText || '').trim() === 'Sets With\\nBoots');
              const header = label?.parentElement;
              const parent = header?.parentElement;
              const idx = parent ? Array.from(parent.children).indexOf(header) : -1;
              const section = idx >= 0 ? parent?.children[idx + 2] : null;
              const out = [];
              const seen = new Set();
              if (!section) return out;
              for (const img0 of Array.from(section.querySelectorAll('img[data-id^="0_"]'))) {
                let row = img0.parentElement;
                for (let depth = 0; row && depth < 8 && section.contains(row); depth++, row = row.parentElement) {
                  const imgs = [];
                  for (let k = 0; k < 2; k++) {
                    const img = row.querySelector(`img[data-id^="${k}_"]`);
                    if (!img) {
                      imgs.length = 0;
                      break;
                    }
                    const rawId = img.getAttribute('data-id') || '';
                    imgs.push({
                      item_id: Number(rawId.split('_')[1]),
                      name: img.alt || ''
                    });
                  }
                  if (imgs.length !== 2) continue;
                  const stats = Array.from(row.querySelectorAll('div.my-1'))
                    .map((el) => (el.textContent || '').trim())
                    .filter(numeric)
                    .slice(0, 3);
                  if (stats.length < 3) continue;
                  const key = imgs.map((img) => img.item_id).join('|') + ':' + stats.join('|');
                  if (seen.has(key)) break;
                  seen.add(key);
                  out.push({
                    item_ids: imgs.map((img) => img.item_id),
                    item_names: imgs.map((img) => img.name),
                    stats
                  });
                  break;
                }
              }
              return out;
            }
            """
        )
        browser.close()

    stats = _normalize_playwright_pair_rows(rows)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    return stats


def fetch_actual_built_sets_5(
    champion_slug: str,
    *,
    cache_dir: str | Path = "data/cache",
    refresh: bool = False,
    mode: str = DEFAULT_MODE,
    tier: str = DEFAULT_TIER,
    patch: str = DEFAULT_PATCH,
) -> list[dict[str, Any]]:
    target = built_sets_cache_path_for(champion_slug, cache_dir, mode=mode, tier=tier, patch=patch)
    if target.exists() and not refresh:
        cached = json.loads(target.read_text(encoding="utf-8"))
        if cached and all(row.get("data_source") == "build_itemset_api" for row in cached):
            return cached

    try:
        payload = _fetch_item_sets_api_payload(champion_slug, mode=mode, tier=tier, patch=patch)
        sets = _normalize_item_sets_api_payload(payload)
    except (OSError, TypeError, ValueError):
        sets = []
    if sets:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(sets, ensure_ascii=False, indent=2), encoding="utf-8")
        return sets

    from playwright.sync_api import sync_playwright

    source_url = lolalytics_url(champion_slug, mode=mode, tier=tier, patch=patch)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1600}, locale="en-US")
        page.goto(source_url, wait_until="domcontentloaded", timeout=60000)
        control = page.locator('[data-type="a_5"]').first
        control.scroll_into_view_if_needed(timeout=15000)
        control.click(timeout=15000)
        rows = page.evaluate(f"({_scroll_collect_sets_script()})()")
        browser.close()

    sets = _normalize_playwright_sets(rows)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(sets, ensure_ascii=False, indent=2), encoding="utf-8")
    return sets
