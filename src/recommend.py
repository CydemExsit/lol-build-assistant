from __future__ import annotations

import json
import math
from itertools import combinations
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .compliance import freeze_static_recommendation
from .health import assess_recommendation_data
from .items import enrich_item, is_boot, is_completed_non_boot_item, load_items_map
from .live_client import build_match_context, build_match_key, load_snapshot
from .lolalytics import (
    DEFAULT_MODE,
    DEFAULT_PATCH,
    DEFAULT_TIER,
    built_sets_cache_path_for,
    fetch_actual_built_sets_5,
    fetch_boot_pair_stats,
    fetch_boot_stats,
    fetch_item_stats,
    load_best_build,
)


MAGIC_THREATS = {
    "akali",
    "ahri",
    "amumu",
    "anivia",
    "annie",
    "aurora",
    "aurelionsol",
    "azir",
    "blitzcrank",
    "brand",
    "cassiopeia",
    "chogath",
    "diana",
    "drmundo",
    "ekko",
    "elise",
    "evelynn",
    "fiddlesticks",
    "fizz",
    "galio",
    "gragas",
    "gwen",
    "hwei",
    "heimerdinger",
    "ivern",
    "janna",
    "karma",
    "karthus",
    "kassadin",
    "katarina",
    "kayle",
    "kennen",
    "kogmaw",
    "leblanc",
    "lillia",
    "lissandra",
    "lulu",
    "lux",
    "malphite",
    "malzahar",
    "maokai",
    "mordekaiser",
    "morgana",
    "nami",
    "nautilus",
    "neeko",
    "nidalee",
    "nunu",
    "orianna",
    "rammus",
    "rumble",
    "ryze",
    "seraphine",
    "sejuani",
    "shyvana",
    "singed",
    "sona",
    "soraka",
    "swain",
    "sylas",
    "syndra",
    "taliyah",
    "tahmkench",
    "teemo",
    "twistedfate",
    "veigar",
    "velkoz",
    "vex",
    "viktor",
    "vladimir",
    "volibear",
    "xerath",
    "ziggs",
    "zoe",
    "zac",
    "zilean",
    "zyra",
}

PHYSICAL_THREATS = {
    "aatrox",
    "akshan",
    "aphelios",
    "ashe",
    "belveth",
    "briar",
    "caitlyn",
    "camille",
    "darius",
    "draven",
    "ezreal",
    "fiora",
    "gangplank",
    "garen",
    "gnar",
    "graves",
    "hecarim",
    "illaoi",
    "irelia",
    "jarvaniv",
    "jax",
    "jayce",
    "jinx",
    "kaisa",
    "kalista",
    "kindred",
    "ksante",
    "kogmaw",
    "lucian",
    "leesin",
    "masteryi",
    "missfortune",
    "nasus",
    "naafiri",
    "nilah",
    "nocturne",
    "olaf",
    "pantheon",
    "poppy",
    "pyke",
    "qiyana",
    "quinn",
    "rengar",
    "reksai",
    "renekton",
    "riven",
    "samira",
    "senna",
    "sett",
    "sion",
    "sivir",
    "smolder",
    "talon",
    "tristana",
    "trundle",
    "tryndamere",
    "twitch",
    "varus",
    "vayne",
    "viego",
    "vi",
    "volibear",
    "urgot",
    "wukong",
    "xayah",
    "xinzhao",
    "yasuo",
    "yone",
    "zed",
    "zeri",
}

TANKS = {
    "alistar",
    "amumu",
    "braum",
    "chogath",
    "drmundo",
    "galio",
    "gragas",
    "ksante",
    "leona",
    "malphite",
    "maokai",
    "nautilus",
    "nunu",
    "ornn",
    "poppy",
    "rammus",
    "rell",
    "sejuani",
    "shen",
    "sion",
    "skarner",
    "tahmkench",
    "taric",
    "zac",
}

HARD_CC = {
    "amumu",
    "annie",
    "ashe",
    "brand",
    "galio",
    "gragas",
    "karma",
    "leona",
    "lissandra",
    "malphite",
    "morgana",
    "nautilus",
    "nasus",
    "rell",
    "sejuani",
    "seraphine",
    "twistedfate",
    "veigar",
}

SHIELDS = {"ivern", "janna", "karma", "lulu", "milio", "morgana", "orianna", "seraphine", "shen", "sona", "tahmkench"}
HEALING = {"aatrox", "briar", "drmundo", "fiora", "illaoi", "maokai", "nasus", "nilah", "soraka", "swain", "vladimir", "yuumi"}

VAYNE_CORE = [3153, 3006, 3124]
BOOT_OPTION_IDS = [3006, 3008, 3158, 3111, 3047, 3009, 3020]
COMMON_BOOT_IDS = BOOT_OPTION_IDS
POKE_ITEM_IDS = {126697, 6697, 3004, 6676, 6694, 3814, 3142, 6696, 6699, 3179, 6695, 6693}
ON_HIT_ITEM_IDS = {3153, 3124, 3091, 3302, 6672, 3085, 3095, 6675, 3004}
CRIT_ITEM_IDS = {3031, 3036, 3033, 6672, 6673, 6676, 3085, 3095, 3508, 3032}
DEFENSIVE_ITEM_IDS = {6665, 3072, 3139, 3143, 3156, 3078, 2502, 2504, 2501, 3742}
MARKSMAN_CHAMPIONS = {
    "akshan",
    "aphelios",
    "ashe",
    "caitlyn",
    "corki",
    "draven",
    "ezreal",
    "graves",
    "jhin",
    "jinx",
    "kaisa",
    "kalista",
    "kindred",
    "kogmaw",
    "lucian",
    "missfortune",
    "nilah",
    "quinn",
    "samira",
    "senna",
    "sivir",
    "smolder",
    "tristana",
    "twitch",
    "varus",
    "vayne",
    "xayah",
    "zeri",
}
OFFENSIVE_ITEM_TAGS = {
    "Damage",
    "AttackSpeed",
    "CriticalStrike",
    "SpellDamage",
    "OnHit",
    "ArmorPenetration",
    "MagicPenetration",
}
PHYSICAL_OUTPUT_TAGS = {"Damage", "AttackSpeed", "CriticalStrike", "OnHit", "ArmorPenetration"}
DEFENSIVE_ITEM_TAGS = {"Health", "Armor", "SpellBlock", "MagicResist"}
TEAR_ITEM_ID = 3070
TEAR_UPGRADE_ITEM_IDS = {3003, 3004, 3040, 3042, 3121}
DEFAULT_STARTER_BUDGET = 1400
MULTI_ROUTE_CHAMPIONS = {
    "ashe",
    "ezreal",
    "jinx",
    "kaisa",
    "kayle",
    "kogmaw",
    "missfortune",
    "teemo",
    "twitch",
    "varus",
    "zeri",
}
ARCHETYPE_LABELS = {
    "poke": "穿甲 Poke",
    "on_hit": "命中特效 AD",
    "crit": "暴擊 AD",
    "defensive": "防禦續戰",
    "balanced": "穩定輸出",
}
MIN_ROUTE_PICK_RATE = 0.0005
MIN_ROUTE_CANDIDATE_PICK_RATE = 0.0003
MEDIUM_CONFIDENCE_GAMES = 8
HIGH_CONFIDENCE_PICK_RATE = 0.001
HIGH_CONFIDENCE_GAMES = 75
DEFAULT_USER_PREFERENCES_PATH = Path("data/ref/user_preferences.json")
DEFAULT_USER_PREFERENCES = {
    "item_score_adjustments": {"3153": 1.6, "3072": 1.6, "3157": -3.0, "3139": -2.7},
    "extreme_damage_enemy_count": 4,
    "extreme_pure_defense_item_bonus": 1.8,
    "extreme_multi_defense_route_bonus": 1.5,
    "marksman_full_ap_min_items": 4,
    "marksman_full_ap_route_penalty": 6.0,
}


@dataclass(frozen=True)
class ThreatProfile:
    magic_count: int
    physical_count: int
    tank_count: int
    cc_count: int
    shield_count: int
    healing_count: int

    def to_dict(self) -> dict[str, int]:
        return {
            "magic_count": self.magic_count,
            "physical_count": self.physical_count,
            "tank_count": self.tank_count,
            "cc_count": self.cc_count,
            "shield_count": self.shield_count,
            "healing_count": self.healing_count,
        }


@dataclass(frozen=True)
class AllyProfile:
    magic_count: int
    physical_count: int
    frontline_count: int
    cc_count: int
    sustain_count: int

    def to_dict(self) -> dict[str, int]:
        return {
            "magic_count": self.magic_count,
            "physical_count": self.physical_count,
            "frontline_count": self.frontline_count,
            "cc_count": self.cc_count,
            "sustain_count": self.sustain_count,
        }


def load_user_preferences(path: str | Path = DEFAULT_USER_PREFERENCES_PATH) -> dict[str, Any]:
    preferences = {
        **DEFAULT_USER_PREFERENCES,
        "item_score_adjustments": dict(DEFAULT_USER_PREFERENCES["item_score_adjustments"]),
    }
    preference_path = Path(path)
    if not preference_path.exists():
        return preferences

    loaded = json.loads(preference_path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"user preferences must be a JSON object: {preference_path}")

    adjustments = loaded.get("item_score_adjustments")
    if isinstance(adjustments, dict):
        preferences["item_score_adjustments"].update(
            {
                str(item_id): float(adjustment)
                for item_id, adjustment in adjustments.items()
                if isinstance(adjustment, (int, float))
            }
        )
    for key, default in DEFAULT_USER_PREFERENCES.items():
        if key == "item_score_adjustments" or key not in loaded:
            continue
        value = loaded[key]
        if isinstance(default, int) and isinstance(value, int):
            preferences[key] = value
        elif isinstance(default, float) and isinstance(value, (int, float)):
            preferences[key] = float(value)
    return preferences


def _item_preference_adjustment(item_id: int, preferences: dict[str, Any]) -> float:
    adjustments = preferences.get("item_score_adjustments") or {}
    value = adjustments.get(str(item_id), adjustments.get(item_id, 0.0))
    return float(value) if isinstance(value, (int, float)) else 0.0


def _extreme_damage_type(threats: ThreatProfile, preferences: dict[str, Any]) -> str | None:
    threshold = int(preferences.get("extreme_damage_enemy_count") or 4)
    if threats.magic_count >= threshold and threats.magic_count > threats.physical_count:
        return "magic"
    if threats.physical_count >= threshold and threats.physical_count > threats.magic_count:
        return "physical"
    return None


def _is_offensive_item(item: dict[str, Any]) -> bool:
    return bool(set(item.get("tags") or []) & OFFENSIVE_ITEM_TAGS)


def _is_pure_defense_item(item: dict[str, Any], damage_type: str | None = None) -> bool:
    tags = set(item.get("tags") or [])
    if not tags & DEFENSIVE_ITEM_TAGS or tags & OFFENSIVE_ITEM_TAGS:
        return False
    if damage_type == "magic":
        return bool(tags & {"SpellBlock", "MagicResist"}) or ("Health" in tags and "Armor" not in tags)
    if damage_type == "physical":
        return "Armor" in tags or ("Health" in tags and not tags & {"SpellBlock", "MagicResist"})
    return True


def _is_full_ap_marksman_route(
    items: list[dict[str, Any]],
    champion_slug: str,
    preferences: dict[str, Any],
) -> bool:
    if champion_slug not in MARKSMAN_CHAMPIONS:
        return False
    ap_items = sum(1 for item in items if "SpellDamage" in set(item.get("tags") or []))
    physical_items = sum(1 for item in items if set(item.get("tags") or []) & PHYSICAL_OUTPUT_TAGS)
    minimum_ap_items = int(preferences.get("marksman_full_ap_min_items") or 4)
    return ap_items >= minimum_ap_items and physical_items <= 1


def _item_uses_tear(item_id: int, item_map: dict[int, dict[str, Any]]) -> bool:
    if item_id in TEAR_UPGRADE_ITEM_IDS:
        return True
    seen: set[int] = set()
    stack = [item_id]
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        for component in item_map.get(current, {}).get("from") or []:
            try:
                component_id = int(component)
            except (TypeError, ValueError):
                continue
            if component_id == TEAR_ITEM_ID:
                return True
            stack.append(component_id)
    return False


def _route_starting_reminders(
    items: list[dict[str, Any]],
    item_map: dict[int, dict[str, Any]],
) -> list[str]:
    if any(_item_uses_tear(int(item["item_id"]), item_map) for item in items):
        return ["開場先買女神之淚"]
    return []


def _route_preference_details(
    items: list[dict[str, Any]],
    threats: ThreatProfile,
    champion_slug: str,
    preferences: dict[str, Any],
) -> tuple[list[str], list[str]]:
    reasons: list[str] = []
    flags: list[str] = []
    liked = [
        item.get("zh_tw_name") or item.get("name") or str(item["item_id"])
        for item in items
        if _item_preference_adjustment(int(item["item_id"]), preferences) > 0
    ]
    disliked = [
        item.get("zh_tw_name") or item.get("name") or str(item["item_id"])
        for item in items
        if _item_preference_adjustment(int(item["item_id"]), preferences) < 0
    ]
    if liked:
        reasons.append("個人偏好加分：" + "、".join(liked))
    if disliked:
        reasons.append("個人偏好減分：" + "、".join(disliked))

    damage_type = _extreme_damage_type(threats, preferences)
    pure_defense = [
        item.get("zh_tw_name") or item.get("name") or str(item["item_id"])
        for item in items
        if _is_pure_defense_item(item, damage_type)
    ]
    if damage_type and pure_defense and sum(1 for item in items if _is_offensive_item(item)) >= 2:
        damage_label = "魔法" if damage_type == "magic" else "物理"
        reasons.append(f"敵方{damage_label}傷害極端，核心裝後補純防禦：" + "、".join(pure_defense))

    if _is_full_ap_marksman_route(items, champion_slug, preferences):
        flags.append("marksman_full_ap")
        reasons.append("個人偏好減分：射手不優先純 AP 五件套")
    return reasons, flags


def analyze_threats(context: dict[str, Any]) -> ThreatProfile:
    enemy_slugs = [p.get("champion_slug", "") for p in context.get("enemies", [])]
    return ThreatProfile(
        magic_count=sum(1 for c in enemy_slugs if c in MAGIC_THREATS),
        physical_count=sum(1 for c in enemy_slugs if c in PHYSICAL_THREATS),
        tank_count=sum(1 for c in enemy_slugs if c in TANKS),
        cc_count=sum(1 for c in enemy_slugs if c in HARD_CC),
        shield_count=sum(1 for c in enemy_slugs if c in SHIELDS),
        healing_count=sum(1 for c in enemy_slugs if c in HEALING),
    )


def analyze_allies(context: dict[str, Any]) -> AllyProfile:
    ally_slugs = [p.get("champion_slug", "") for p in context.get("allies", [])]
    return AllyProfile(
        magic_count=sum(1 for champion in ally_slugs if champion in MAGIC_THREATS),
        physical_count=sum(1 for champion in ally_slugs if champion in PHYSICAL_THREATS),
        frontline_count=sum(1 for champion in ally_slugs if champion in TANKS),
        cc_count=sum(1 for champion in ally_slugs if champion in HARD_CC),
        sustain_count=sum(1 for champion in ally_slugs if champion in SHIELDS or champion in HEALING),
    )


def _composition_notes(profile: AllyProfile) -> list[str]:
    notes: list[str] = []
    if profile.physical_count >= 4 and profile.magic_count <= 1:
        notes.append("我方陣容以物理輸出為主")
    elif profile.magic_count >= 4 and profile.physical_count <= 1:
        notes.append("我方陣容以魔法輸出為主")
    if profile.frontline_count == 0:
        notes.append("我方陣容前排較少")
    if profile.cc_count == 0:
        notes.append("我方陣容硬控制較少")
    return notes


def _team_route_adjustment(
    items: list[dict[str, Any]],
    profile: AllyProfile,
) -> tuple[float, list[str]]:
    spell_items = sum(1 for item in items if "SpellDamage" in set(item.get("tags") or []))
    physical_items = sum(
        1 for item in items if set(item.get("tags") or []) & PHYSICAL_OUTPUT_TAGS
    )
    defensive_items = sum(
        1 for item in items if set(item.get("tags") or []) & DEFENSIVE_ITEM_TAGS
    )
    score = 0.0
    reasons: list[str] = []
    if profile.physical_count >= 4 and profile.magic_count <= 1:
        if spell_items >= 3:
            score += 0.8
            reasons.append("此方案能增加我方傷害類型多樣性")
        elif physical_items >= 3:
            score -= 0.25
    elif profile.magic_count >= 4 and profile.physical_count <= 1 and physical_items >= 3:
        score += 0.55
        reasons.append("此方案能增加我方傷害類型多樣性")
    if profile.frontline_count == 0 and defensive_items >= 1:
        score += 0.3
        reasons.append("此方案保留較多自保屬性")
    return score, reasons


def _flatten_lolalytics_items(build_data: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[int] = set()
    for label in ["Core Build", "Item 4", "Item 5", "Item 6"]:
        for item in build_data.get("sections", {}).get(label, []):
            item_id = int(item["item_id"])
            if item_id not in seen:
                seen.add(item_id)
                out.append({**item, "source_section": label})
    for item in build_data.get("candidate_items", []):
        item_id = int(item["item_id"])
        if item_id not in seen:
            seen.add(item_id)
            out.append({**item, "source_section": "candidate_items"})
    return out


def _median(values: list[float]) -> float:
    if not values:
        return 0.5
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def _build_item_stats_by_id(
    popular_rows: list[dict[str, Any]],
    winning_rows: list[dict[str, Any]],
) -> dict[int, dict[str, Any]]:
    baseline_rows = [
        row
        for row in (popular_rows + winning_rows)
        if isinstance(row.get("win_rate"), (int, float))
        and isinstance(row.get("games"), int)
        and int(row.get("games") or 0) >= 40
        and float(row.get("pick_rate") or 0) >= 0.0008
    ]
    baseline = _median([float(row["win_rate"]) for row in baseline_rows])
    by_id: dict[int, dict[str, Any]] = {}
    for source, rows in (("popular", popular_rows), ("winning", winning_rows)):
        for row in rows:
            item_id = int(row["item_id"])
            entry = by_id.setdefault(
                item_id,
                {
                    "item_id": item_id,
                    "item_name": row.get("item_name"),
                    "item_stat_baseline": baseline,
                },
            )
            prefix = f"{source}_"
            entry[f"{prefix}win_rate"] = row.get("win_rate")
            entry[f"{prefix}pick_rate"] = row.get("pick_rate")
            entry[f"{prefix}games"] = row.get("games")
            entry[f"{prefix}rank"] = row.get("rank")
            entry[f"{prefix}time"] = row.get("time")

    for entry in by_id.values():
        candidates: list[dict[str, Any]] = []
        for source in ("winning", "popular"):
            win_rate = entry.get(f"{source}_win_rate")
            pick_rate = entry.get(f"{source}_pick_rate")
            games = entry.get(f"{source}_games")
            if not isinstance(win_rate, (int, float)) or not isinstance(games, int):
                continue
            candidates.append(
                {
                    "source": "Winning Items" if source == "winning" else "Popular Items",
                    "win_rate": float(win_rate),
                    "pick_rate": float(pick_rate or 0),
                    "games": int(games),
                }
            )
        if not candidates:
            continue
        chosen = max(
            candidates,
            key=lambda row: (
                (row["win_rate"] - baseline) * 100.0
                + min(row["pick_rate"] * 8.0, 0.8)
                + min(math.log10(row["games"] + 1) * 0.12, 0.5)
                + (0.35 if row["source"] == "Winning Items" else 0.0)
            ),
        )
        entry["win_rate"] = chosen["win_rate"]
        entry["pick_rate"] = chosen["pick_rate"]
        entry["games"] = chosen["games"]
        entry["stat_source"] = chosen["source"]
        entry["relative_win_rate"] = chosen["win_rate"] - baseline
    return by_id


def _merge_item_stats(
    items: list[dict[str, Any]],
    stats_by_id: dict[int, dict[str, Any]],
    item_map: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    merged_by_id = {int(item["item_id"]): item for item in items}
    for item_id, stats in stats_by_id.items():
        if item_id not in item_map:
            continue
        base = merged_by_id.get(item_id) or enrich_item({"item_id": item_id, "name": stats.get("item_name")}, item_map)
        merged_by_id[item_id] = {
            **base,
            **stats,
            "source_section": base.get("source_section") or stats.get("stat_source") or "item_stats",
        }
    return list(merged_by_id.values())


def _score_item(
    item: dict[str, Any],
    threats: ThreatProfile,
    champion_slug: str,
    preferences: dict[str, Any],
) -> tuple[float, list[str]]:
    tags = set(item.get("tags") or [])
    item_id = int(item["item_id"])
    score = 0.0
    reasons: list[str] = []

    win_rate = item.get("win_rate")
    games = item.get("games")
    pick_rate = item.get("pick_rate")
    relative_win_rate = item.get("relative_win_rate")
    baseline = item.get("item_stat_baseline")
    if isinstance(win_rate, (int, float)):
        score += (float(win_rate) - 0.5) * 18
        reasons.append(f"LoLalytics 勝率 {float(win_rate) * 100:.2f}%")
        if isinstance(relative_win_rate, (int, float)):
            score += float(relative_win_rate) * 78.0
            if isinstance(baseline, (int, float)) and float(relative_win_rate) >= 0.012:
                reasons.append(f"相對此英雄裝備中位勝率 +{float(relative_win_rate) * 100:.2f}%")
            elif isinstance(pick_rate, (int, float)) and float(pick_rate) >= 0.08 and float(relative_win_rate) < -0.004:
                score -= min(float(pick_rate) * 7.0, 1.2)
                reasons.append("選取率高但相對勝率偏低")
        if isinstance(games, int) and games >= 40 and (
            (isinstance(relative_win_rate, (int, float)) and float(relative_win_rate) >= 0.018)
            or (isinstance(games, int) and games >= 75 and float(win_rate) >= 0.56)
        ):
            score += min(max(float(win_rate) - (float(baseline) if isinstance(baseline, (int, float)) else 0.5), 0) * 58, 2.6)
            reasons.append(f"{item.get('stat_source') or 'Winning Items'} 高勝率候選")
    if isinstance(games, int) and games:
        score += min(games / 25000.0, 0.45)
        reasons.append(f"LoLalytics 樣本 {games:,} 場")
    if isinstance(pick_rate, (int, float)) and pick_rate:
        score += min(float(pick_rate) * 3.0, 0.8)

    section = item.get("source_section")
    if section == "Core Build":
        score += 4.0
        reasons.append("LoLalytics 核心出裝")
    elif section in {"Item 4", "Item 5", "Item 6"}:
        score += 2.0
        reasons.append(f"LoLalytics {section} 分支選項")

    if champion_slug == "vayne":
        if "AttackSpeed" in tags:
            score += 1.2
            reasons.append("汎很吃攻速成長")
        if "OnHit" in tags:
            score += 1.6
            reasons.append("命中特效與鬼索/聖銀弩箭相性好")
        if "LifeSteal" in tags:
            score += 0.7
            reasons.append("提供單挑續戰")
        if item_id in VAYNE_CORE:
            score += 3.0
            reasons.append("汎的基準核心裝")

    if threats.magic_count >= 3 and ("SpellBlock" in tags or "MagicResist" in tags):
        score += 2.4
        reasons.append("敵方魔法傷害偏多")
    if threats.magic_count >= 3 and item_id == 3156:
        score += 2.0
        reasons.append("魔提斯深淵適合高魔法壓力局")
    if threats.cc_count >= 2 and ("Tenacity" in tags or "Active" in tags):
        score += 1.8
        reasons.append("敵方控制威脅多")
    if threats.tank_count >= 1 and ("ArmorPenetration" in tags or "OnHit" in tags or item_id in {3153, 3302}):
        score += 1.3
        reasons.append("更適合處理前排血量與抗性")
    if threats.physical_count >= 3 and "Armor" in tags:
        score += 1.3
        reasons.append("敵方物理壓力高")
    if threats.shield_count >= 1 and item_id == 6695:
        score += 1.2
        reasons.append("敵方有護盾，可作為破盾選項")
    if threats.healing_count >= 2 and item_id == 3033:
        score += 1.4
        reasons.append("敵方回復多，可作為重創選項")
    if item_id == 3072 and isinstance(relative_win_rate, (int, float)) and float(relative_win_rate) >= 0.012:
        score += 1.2
        reasons.append("嗜血者在此英雄統計中表現突出")

    preference_adjustment = _item_preference_adjustment(item_id, preferences)
    if preference_adjustment:
        score += preference_adjustment * 0.55
        direction = "加分" if preference_adjustment > 0 else "減分"
        reasons.append(f"個人偏好{direction} {preference_adjustment:+.1f}")

    extreme_damage_type = _extreme_damage_type(threats, preferences)
    if extreme_damage_type and _is_pure_defense_item(item, extreme_damage_type):
        score += float(preferences.get("extreme_pure_defense_item_bonus") or 0.0)
        damage_label = "魔法" if extreme_damage_type == "magic" else "物理"
        reasons.append(f"敵方{damage_label}傷害極端，可作為純防禦補位")

    # Avoid low-synergy defensive tank items unless the matchup strongly demands them.
    if (
        champion_slug == "vayne"
        and not extreme_damage_type
        and not ({"Damage", "AttackSpeed", "OnHit", "CriticalStrike"} & tags)
    ):
        score -= 1.0

    return score, reasons


def _item_payload(item: dict[str, Any], *, score: float | None = None, reasons: list[str] | None = None) -> dict[str, Any]:
    payload = {
        "item_id": int(item["item_id"]),
        "display_name": item.get("zh_tw_name") or item.get("name") or str(item["item_id"]),
        "name": item.get("name") or str(item["item_id"]),
        "zh_tw_name": item.get("zh_tw_name"),
        "tags": item.get("tags") or [],
    }
    for key in ("win_rate", "pick_rate", "games"):
        if item.get(key) is not None:
            payload[key] = item.get(key)
    if score is not None:
        payload["score"] = round(score, 4)
    if reasons is not None:
        payload["reasons"] = reasons[:4]
    return payload


def _enrich_by_id(item_id: int, item_name: str, item_map: dict[int, dict[str, Any]]) -> dict[str, Any]:
    return enrich_item({"item_id": item_id, "name": item_name}, item_map)


def _is_valid_full_set(row: dict[str, Any], item_map: dict[int, dict[str, Any]]) -> bool:
    return len(_items_for_set(row, item_map)) == 5


def _items_for_set(row: dict[str, Any], item_map: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    item_ids = [int(x) for x in row.get("item_ids", [])]
    if len(item_ids) != 5 or len(set(item_ids)) != 5:
        return []
    items: list[dict[str, Any]] = []
    for item_id, item_name in zip(item_ids, row.get("item_names", []), strict=False):
        if item_id not in item_map:
            return []
        item = _enrich_by_id(item_id, str(item_name), item_map)
        if not is_completed_non_boot_item(item):
            return []
        items.append(item)
    return items


def _set_archetype(row: dict[str, Any], item_map: dict[int, dict[str, Any]], champion_slug: str) -> str | None:
    items = _items_for_set(row, item_map)
    if len(items) != 5:
        return None
    return _classify_route(items, champion_slug)


def _classify_route(items: list[dict[str, Any]], champion_slug: str) -> str:
    ids = {int(item["item_id"]) for item in items}
    tags = [tag for item in items for tag in item.get("tags", [])]
    tag_count = {tag: tags.count(tag) for tag in set(tags)}
    poke_hits = len(ids & POKE_ITEM_IDS)
    on_hit_hits = len(ids & ON_HIT_ITEM_IDS) + tag_count.get("OnHit", 0)
    crit_hits = len(ids & CRIT_ITEM_IDS) + tag_count.get("CriticalStrike", 0)
    defensive_hits = len(ids & DEFENSIVE_ITEM_IDS) + sum(
        1 for item in items if {"Armor", "SpellBlock", "MagicResist", "Health"} & set(item.get("tags") or [])
    )

    if champion_slug == "varus" and poke_hits >= 3:
        return "poke"
    if on_hit_hits >= 3 and tag_count.get("AttackSpeed", 0) >= 2:
        return "on_hit"
    if crit_hits >= 3:
        return "crit"
    if defensive_hits >= 3:
        return "defensive"
    if poke_hits >= 3 or ("Mana" in tag_count and tag_count.get("AbilityHaste", 0) >= 2):
        return "poke"
    return "balanced"


def _route_label(archetype: str, items: list[dict[str, Any]], threats: ThreatProfile) -> str:
    tags = [tag for item in items for tag in item.get("tags", [])]
    ids = {int(item["item_id"]) for item in items}
    modifiers: list[str] = []
    if threats.tank_count and ({"OnHit", "ArmorPenetration"} & set(tags) or ids & {3153, 3302, 3036, 3033}):
        modifiers.append("打坦")
    if threats.magic_count >= 3 and any({"SpellBlock", "MagicResist"} & set(item.get("tags") or []) for item in items):
        modifiers.append("抗魔")
    if threats.cc_count >= 2 and any("Tenacity" in set(item.get("tags") or []) for item in items):
        modifiers.append("抗控")
    if threats.shield_count and 6695 in ids:
        modifiers.append("破盾")
    if threats.healing_count >= 2 and 3033 in ids:
        modifiers.append("重創")

    label = ARCHETYPE_LABELS.get(archetype, ARCHETYPE_LABELS["balanced"])
    if modifiers:
        return f"{label} / {' / '.join(modifiers[:2])}"
    return label


def _route_reasons(
    row: dict[str, Any],
    archetype: str,
    items: list[dict[str, Any]],
    threats: ThreatProfile,
    winning_item_signals: list[dict[str, Any]] | None = None,
) -> list[str]:
    reasons: list[str] = []
    tags = [tag for item in items for tag in item.get("tags", [])]
    if archetype == "poke":
        reasons.append("偏穿甲與技能急速，適合 ARAM 遠距離消耗")
    elif archetype == "on_hit":
        reasons.append("偏攻速與命中特效，適合持續輸出與處理前排")
    elif archetype == "crit":
        reasons.append("偏暴擊 AD，適合穩定普攻爆發")
    elif archetype == "defensive":
        reasons.append("含較多防禦屬性，適合被強開或魔法壓力高的局")
    if threats.tank_count and ("ArmorPenetration" in tags or "OnHit" in tags):
        reasons.append("敵方有前排，穿透或命中特效價值提高")
    if threats.magic_count >= 3 and ("SpellBlock" in tags or "MagicResist" in tags):
        reasons.append("敵方魔法傷害偏多，抗魔裝備價值提高")
    if threats.magic_count >= 3 and any(int(item["item_id"]) == 3156 for item in items):
        reasons.append("對面魔法傷害占比高，魔提斯深淵是高優先度防禦輸出裝")
    if winning_item_signals:
        names = [
            f"{item['display_name']} {item['win_rate'] * 100:.2f}%/{int(item['games']):,}場"
            for item in winning_item_signals[:3]
        ]
        reasons.append("包含 Winning Items 高勝率裝備：" + "、".join(names))
    return reasons


def _adjusted_win_rate(win_rate: float, games: int, prior_rate: float = 0.5, prior_games: int = 80) -> float:
    if games <= 0:
        return prior_rate
    wins = win_rate * games
    return (wins + prior_rate * prior_games) / (games + prior_games)


def _route_confidence(row: dict[str, Any]) -> dict[str, Any]:
    games = int(row.get("games") or 0)
    pick_rate = float(row.get("pick_rate") or 0.0)
    evidence = min(games / HIGH_CONFIDENCE_GAMES, 1.0) * 0.65
    evidence += min(pick_rate / HIGH_CONFIDENCE_PICK_RATE, 1.0) * 0.35
    if games >= HIGH_CONFIDENCE_GAMES and pick_rate >= HIGH_CONFIDENCE_PICK_RATE:
        level, label = "high", "較高可信"
    elif games >= MEDIUM_CONFIDENCE_GAMES and pick_rate >= MIN_ROUTE_CANDIDATE_PICK_RATE:
        level, label = "medium", "中等可信"
    else:
        level, label = "exploratory", "探索方案"
    return {
        "level": level,
        "label": label,
        "score": round(evidence * 100),
        "games": games,
        "pick_rate": pick_rate,
    }


def _winning_item_signals(items: list[dict[str, Any]], scored_by_id: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    for item in items:
        scored = scored_by_id.get(int(item["item_id"]), {})
        win_rate = scored.get("win_rate")
        games = scored.get("games")
        relative_win_rate = scored.get("relative_win_rate")
        if not isinstance(win_rate, (int, float)) or not isinstance(games, int):
            continue
        is_high_signal = (
            (isinstance(relative_win_rate, (int, float)) and games >= 40 and float(relative_win_rate) >= 0.014)
            or (games >= 150 and win_rate >= 0.555)
            or (games >= 75 and win_rate >= 0.57)
            or (games >= 40 and win_rate >= 0.60)
        )
        if not is_high_signal:
            continue
        signals.append(
            {
                "item_id": int(item["item_id"]),
                "display_name": scored.get("zh_tw_name") or scored.get("name") or item.get("zh_tw_name") or item.get("name"),
                "win_rate": float(win_rate),
                "games": games,
                "relative_win_rate": float(relative_win_rate) if isinstance(relative_win_rate, (int, float)) else None,
            }
        )
    return sorted(signals, key=lambda x: (x.get("relative_win_rate") or 0, x["win_rate"], x["games"]), reverse=True)


def _boot_stats_by_id(rows: list[dict[str, Any]], item_map: dict[int, dict[str, Any]]) -> dict[int, dict[str, Any]]:
    stats_by_id: dict[int, dict[str, Any]] = {}
    for row in rows:
        if row.get("item_id") is not None:
            item_id = int(row.get("item_id"))
            boot_ids = [item_id] if item_id in item_map and is_boot(enrich_item({"item_id": item_id}, item_map)) and item_id != 1001 else []
        else:
            boot_ids = []
            for item_id in row.get("item_ids", []):
                item_id = int(item_id)
                if item_id in item_map and is_boot(enrich_item({"item_id": item_id}, item_map)) and item_id != 1001:
                    boot_ids.append(item_id)
        if len(boot_ids) != 1:
            continue
        boot_id = boot_ids[0]
        games = row.get("games")
        if not isinstance(games, int):
            continue
        current = stats_by_id.get(boot_id)
        if current is not None and int(current.get("games") or 0) >= games:
            continue
        stats_by_id[boot_id] = {
            "win_rate": row.get("win_rate"),
            "pick_rate": row.get("pick_rate"),
            "games": games,
            "time": row.get("time"),
            "source": row.get("source"),
        }
    return stats_by_id


def _score_route(
    row: dict[str, Any],
    items: list[dict[str, Any]],
    scored_by_id: dict[int, dict[str, Any]],
    threats: ThreatProfile,
    archetype: str,
    champion_slug: str,
    preferences: dict[str, Any],
) -> float:
    win_rate = float(row.get("win_rate") or 0.5)
    pick_rate = float(row.get("pick_rate") or 0.0)
    games = int(row.get("games") or 0)
    item_score = sum(float(scored_by_id.get(int(item["item_id"]), {}).get("score", 0.0)) for item in items) / max(len(items), 1)
    adjusted_win_rate = _adjusted_win_rate(win_rate, games)
    high_confidence = games >= HIGH_CONFIDENCE_GAMES and pick_rate >= HIGH_CONFIDENCE_PICK_RATE
    score = (adjusted_win_rate - 0.5) * 46.0
    score += math.log10(games + 1) * 1.25
    score += min(pick_rate * 90.0, 1.0)
    score += item_score * 0.85
    if high_confidence:
        score += max(0.0, win_rate - 0.54) * 42.0
        if win_rate >= 0.58:
            score += 0.8
    if pick_rate < MIN_ROUTE_PICK_RATE:
        score -= 1.5 + (MIN_ROUTE_PICK_RATE - pick_rate) * 3000.0
    for signal in _winning_item_signals(items, scored_by_id):
        score += min((signal["win_rate"] - 0.55) * 34.0, 1.4)
    ids = {int(item["item_id"]) for item in items}
    tags = {tag for item in items for tag in item.get("tags", [])}
    score += sum(_item_preference_adjustment(item_id, preferences) for item_id in ids)
    for item_id in ids:
        scored = scored_by_id.get(item_id, {})
        relative = scored.get("relative_win_rate")
        pick_rate = scored.get("pick_rate")
        if isinstance(relative, (int, float)) and float(relative) >= 0.018:
            score += min(float(relative) * 42.0, 1.4)
        if isinstance(relative, (int, float)) and isinstance(pick_rate, (int, float)) and float(pick_rate) >= 0.08 and float(relative) < -0.006:
            score -= min(float(pick_rate) * 3.5, 0.8)
    if threats.tank_count and ("OnHit" in tags or "ArmorPenetration" in tags or ids & {3153, 3302, 3036, 3033}):
        score += 0.8
    if threats.magic_count >= 3 and ("SpellBlock" in tags or "MagicResist" in tags):
        score += 0.7
    if threats.magic_count >= 3 and 3156 in ids:
        score += 1.4
    if threats.cc_count >= 2 and "Tenacity" in tags:
        score += 0.4
    if threats.shield_count and 6695 in ids:
        score += 0.5
    if threats.healing_count >= 2 and 3033 in ids:
        score += 0.6
    if archetype == "poke" and threats.tank_count == 0:
        score += 0.3
    extreme_damage_type = _extreme_damage_type(threats, preferences)
    pure_defense_count = sum(1 for item in items if _is_pure_defense_item(item, extreme_damage_type))
    offensive_count = sum(1 for item in items if _is_offensive_item(item))
    if extreme_damage_type and pure_defense_count and offensive_count >= 2:
        score += pure_defense_count * float(preferences.get("extreme_pure_defense_item_bonus") or 0.0)
        if pure_defense_count >= 2:
            score += float(preferences.get("extreme_multi_defense_route_bonus") or 0.0)
    if _is_full_ap_marksman_route(items, champion_slug, preferences):
        score -= float(preferences.get("marksman_full_ap_route_penalty") or 0.0)
    return score


def _score_boot_option(
    item: dict[str, Any],
    archetype: str,
    threats: ThreatProfile,
) -> tuple[float, list[str]]:
    item_id = int(item["item_id"])
    tags = set(item.get("tags") or [])
    score = 0.0
    reasons: list[str] = []
    win_rate = item.get("win_rate")
    games = item.get("games")
    if isinstance(win_rate, (int, float)) and isinstance(games, int) and games:
        adjusted = _adjusted_win_rate(float(win_rate), games, prior_games=60)
        score += (adjusted - 0.5) * 34.0
        score += min(math.log10(games + 1) * 0.75, 2.6)
        reasons.append(f"LoLalytics 鞋子勝率 {float(win_rate) * 100:.2f}% / {games:,} 場")
        if games >= 60 and float(win_rate) >= 0.55:
            score += min((float(win_rate) - 0.54) * 42.0, 2.0)
            reasons.append("Winning Items 高勝率鞋子")
    else:
        reasons.append("LoLalytics 鞋子樣本不足，作為情境備選")

    section = item.get("source_section")
    if section == "Core Build":
        score += 2.0
        reasons.append("LoLalytics 核心鞋子")
    elif section in {"Item 4", "Item 5", "Item 6", "candidate_items"}:
        score += 0.8
        reasons.append("LoLalytics 常見鞋子選項")

    if item_id == 3008:
        score += 3.0
        reasons.append("貪婪護脛提供普攻/技能吸血，新鞋低選取但高勝率觀察值得獨立考慮")
        if archetype in {"on_hit", "crit", "balanced"}:
            score += 0.6
            reasons.append("AD 持續輸出路線可用續戰換攻速")
    if archetype in {"on_hit", "crit", "balanced"} and item_id == 3006:
        score += 1.6
        reasons.append("攻速路線最穩定的輸出鞋")
    if archetype == "poke" and item_id == 3158:
        score += 1.8
        reasons.append("Poke 路線重視技能急速")
    if threats.magic_count >= 3 and item_id == 3111:
        score += 1.5
        reasons.append("敵方魔法傷害偏多")
    if threats.cc_count >= 3 and item_id == 3111:
        score += 1.3
        reasons.append("敵方控制偏多")
    if threats.physical_count >= 3 and item_id == 3047:
        score += 1.4
        reasons.append("敵方物理壓力偏高")
    if threats.cc_count >= 2 and item_id == 3009:
        score += 0.7
        reasons.append("需要移速與緩速應對時可考慮")
    if archetype == "poke" and item_id == 3020:
        score += 0.5
        reasons.append("魔法傷害或混傷 poke 可考慮")
    if "LifeSteal" in tags and threats.healing_count == 0:
        score += 0.2
    return score, reasons


def _build_boot_options(
    archetype: str,
    build_data: dict[str, Any],
    item_map: dict[int, dict[str, Any]],
    threats: ThreatProfile,
    boot_stats_by_id: dict[int, dict[str, Any]] | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    candidates: dict[int, dict[str, Any]] = {}
    for item in _flatten_lolalytics_items(build_data):
        enriched = enrich_item(item, item_map) | {"source_section": item.get("source_section")}
        if is_boot(enriched) and int(enriched["item_id"]) != 1001:
            candidates[int(enriched["item_id"])] = enriched
    for item_id in BOOT_OPTION_IDS:
        if item_id in item_map and item_id not in candidates:
            candidates[item_id] = enrich_item({"item_id": item_id}, item_map) | {"source_section": "common_boots"}
    for item_id, stats in (boot_stats_by_id or {}).items():
        if item_id not in item_map:
            continue
        base = candidates.get(item_id) or enrich_item({"item_id": item_id}, item_map)
        candidates[item_id] = {
            **base,
            "win_rate": stats.get("win_rate"),
            "pick_rate": stats.get("pick_rate"),
            "games": stats.get("games"),
            "source_section": stats.get("source") or "Boots",
        }

    options: list[dict[str, Any]] = []
    for item in candidates.values():
        score, reasons = _score_boot_option(item, archetype, threats)
        payload = _item_payload(item, score=score)
        payload["sort_score"] = round(score, 4)
        options.append(payload)

    selected = sorted(options, key=lambda x: x.get("sort_score", 0), reverse=True)[:limit]
    for option in selected:
        option.pop("sort_score", None)
        option.pop("score", None)
    return selected


def _select_boots(
    archetype: str,
    build_data: dict[str, Any],
    item_map: dict[int, dict[str, Any]],
    threats: ThreatProfile,
    boot_stats_by_id: dict[int, dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    options = _build_boot_options(archetype, build_data, item_map, threats, boot_stats_by_id=boot_stats_by_id, limit=1)
    return options[0] if options else None


def _starter_item_payload(item: dict[str, Any]) -> dict[str, Any]:
    payload = _item_payload(item)
    payload["gold_total"] = int(item.get("gold_total") or 0)
    return payload


def _starting_items(
    build_data: dict[str, Any],
    item_map: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    options: list[dict[str, Any]] = []
    seen: set[int] = set()
    for raw_item in build_data.get("sections", {}).get("Starting Items", []):
        item_id = int(raw_item["item_id"])
        if item_id in seen:
            continue
        seen.add(item_id)
        options.append(enrich_item(raw_item, item_map))
    return options


def _starter_budget(starting_items: list[dict[str, Any]]) -> int:
    total = sum(int(item.get("gold_total") or 0) for item in starting_items)
    return total if 800 <= total <= 1800 else DEFAULT_STARTER_BUDGET


def _component_ids(item_id: int, item_map: dict[int, dict[str, Any]]) -> set[int]:
    found: set[int] = set()
    stack = [item_id]
    while stack:
        current = stack.pop()
        for raw_component in item_map.get(current, {}).get("from") or []:
            try:
                component_id = int(raw_component)
            except (TypeError, ValueError):
                continue
            if component_id in found:
                continue
            found.add(component_id)
            stack.append(component_id)
    return found


def _starter_candidate(item_id: int, item_map: dict[int, dict[str, Any]]) -> dict[str, Any] | None:
    metadata = item_map.get(item_id)
    if not metadata:
        return None
    if metadata.get("gold_purchasable") is False:
        return None
    if set(metadata.get("tags") or []) & {"Consumable", "Trinket"}:
        return None
    gold = int(metadata.get("gold_total") or 0)
    if gold <= 0:
        return None
    return enrich_item(
        {"item_id": item_id, "name": metadata.get("en_name") or str(item_id)},
        item_map,
    )


def _best_direct_component_package(
    target_item_id: int,
    item_map: dict[int, dict[str, Any]],
    budget: int,
) -> list[dict[str, Any]]:
    direct: list[dict[str, Any]] = []
    for raw_component in item_map.get(target_item_id, {}).get("from") or []:
        try:
            component_id = int(raw_component)
        except (TypeError, ValueError):
            continue
        candidate = _starter_candidate(component_id, item_map)
        if candidate is not None:
            direct.append(candidate)

    best: list[dict[str, Any]] = []
    best_total = 0
    for size in range(1, min(3, len(direct)) + 1):
        for package in combinations(direct, size):
            total = sum(int(item.get("gold_total") or 0) for item in package)
            if total <= budget and total > best_total:
                best = list(package)
                best_total = total
    if best:
        return best

    descendants = [
        candidate
        for component_id in _component_ids(target_item_id, item_map)
        if (candidate := _starter_candidate(component_id, item_map)) is not None
        and int(candidate.get("gold_total") or 0) <= budget
    ]
    return [max(descendants, key=lambda item: int(item.get("gold_total") or 0))] if descendants else []


def _route_starter_option(
    route_items: list[dict[str, Any]],
    build_data: dict[str, Any],
    item_map: dict[int, dict[str, Any]],
) -> dict[str, Any] | None:
    if not route_items:
        return None
    first_item = route_items[0]
    target_item_id = int(first_item["item_id"])
    common_start = _starting_items(build_data, item_map)
    budget = _starter_budget(common_start)

    if any(_item_uses_tear(int(item["item_id"]), item_map) for item in route_items):
        tear = _starter_candidate(TEAR_ITEM_ID, item_map)
        if tear is not None:
            return {
                "items": [_starter_item_payload(tear)],
                "total_gold": int(tear.get("gold_total") or 0),
                "budget": budget,
                "source": "route_requirement",
                "target": _item_payload(first_item),
                "reason": "此路線包含女神之淚升級裝，開場優先疊層",
            }

    target_components = _component_ids(target_item_id, item_map)
    matching_common = [item for item in common_start if int(item["item_id"]) in target_components]
    if matching_common:
        common_total = sum(int(item.get("gold_total") or 0) for item in common_start)
        if common_total <= budget:
            package = common_start
        else:
            package = sorted(
                matching_common,
                key=lambda item: int(item.get("gold_total") or 0),
                reverse=True,
            )
            boots = next((item for item in common_start if is_boot(item)), None)
            package_total = sum(int(item.get("gold_total") or 0) for item in package)
            if boots is not None and package_total + int(boots.get("gold_total") or 0) <= budget:
                package.append(boots)
        package_total = sum(int(item.get("gold_total") or 0) for item in package)
        win_rate = next(
            (float(item["win_rate"]) for item in common_start if isinstance(item.get("win_rate"), (int, float))),
            None,
        )
        option = {
            "items": [_starter_item_payload(item) for item in package],
            "total_gold": package_total,
            "budget": budget,
            "source": "lolalytics_starting_items",
            "target": _item_payload(first_item),
            "reason": f"LoLalytics 常見起手可直接銜接{first_item.get('zh_tw_name') or first_item.get('name')}",
        }
        if win_rate is not None:
            option["win_rate"] = win_rate
        return option

    package = _best_direct_component_package(target_item_id, item_map, budget)
    if not package:
        return None
    package_total = sum(int(item.get("gold_total") or 0) for item in package)
    common_boots = next((item for item in common_start if is_boot(item)), None)
    if common_boots is not None and package_total + int(common_boots.get("gold_total") or 0) <= budget:
        package.append(common_boots)
        package_total += int(common_boots.get("gold_total") or 0)
    return {
        "items": [_starter_item_payload(item) for item in package],
        "total_gold": package_total,
        "budget": budget,
        "source": "data_dragon_component_tree",
        "target": _item_payload(first_item),
        "reason": f"依合成樹優先銜接{first_item.get('zh_tw_name') or first_item.get('name')}",
    }


def _route_candidate_sets(built_sets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates = [
        row for row in built_sets if float(row.get("pick_rate") or 0.0) >= MIN_ROUTE_CANDIDATE_PICK_RATE
    ]
    return candidates or built_sets


def _build_routes(
    built_sets: list[dict[str, Any]],
    item_map: dict[int, dict[str, Any]],
    scored_by_id: dict[int, dict[str, Any]],
    build_data: dict[str, Any],
    threats: ThreatProfile,
    allies: AllyProfile,
    champion_slug: str,
    preferences: dict[str, Any],
    boot_stats_by_id: dict[int, dict[str, Any]] | None = None,
    limit: int = 3,
) -> list[dict[str, Any]]:
    best_by_combo: dict[tuple[int, ...], dict[str, Any]] = {}
    candidate_sets = _route_candidate_sets(built_sets)
    for row in candidate_sets:
        items = _items_for_set(row, item_map)
        if len(items) != 5:
            continue
        archetype = _classify_route(items, champion_slug)
        route_score = _score_route(row, items, scored_by_id, threats, archetype, champion_slug, preferences)
        team_score, team_reasons = _team_route_adjustment(items, allies)
        route_score += team_score
        winning_item_signals = _winning_item_signals(items, scored_by_id)
        boots = _select_boots(archetype, build_data, item_map, threats, boot_stats_by_id=boot_stats_by_id)
        preference_reasons, preference_flags = _route_preference_details(
            items,
            threats,
            champion_slug,
            preferences,
        )
        starter_option = _route_starter_option(items, build_data, item_map)
        route = {
            "label": _route_label(archetype, items, threats),
            "archetype": archetype,
            "score": round(route_score, 4),
            "boots": boots,
            "items": [
                _item_payload(
                    item,
                    score=float(scored_by_id.get(int(item["item_id"]), {}).get("score", 0.0)),
                    reasons=scored_by_id.get(int(item["item_id"]), {}).get("reasons", []),
                )
                for item in items
            ],
            "set_stats": {
                "win_rate": row.get("win_rate"),
                "pick_rate": row.get("pick_rate"),
                "games": row.get("games"),
            },
            "confidence": _route_confidence(row),
            "sequence_basis": "LoLalytics Actually Built Sets item order",
            "source": {
                "lolalytics_params": row.get("source_params") or build_data.get("params"),
                "built_sets_tab": "Actually Built Sets: 5",
            },
            "winning_item_signals": winning_item_signals,
            "starting_reminders": _route_starting_reminders(items, item_map),
            "starter_option": starter_option,
            "preference_flags": preference_flags,
            "source_priority": int(row.get("source_priority") or 0),
            "reasons": preference_reasons
            + team_reasons
            + _route_reasons(row, archetype, items, threats, winning_item_signals),
        }
        combo_key = tuple(sorted(int(item["item_id"]) for item in items))
        current = best_by_combo.get(combo_key)
        if current is None or route["source_priority"] < current.get("source_priority", 0) or (
            route["source_priority"] == current.get("source_priority", 0) and route["score"] > current["score"]
        ):
            best_by_combo[combo_key] = route

    ranked = sorted(best_by_combo.values(), key=lambda x: x["score"], reverse=True)
    preference_matched = [route for route in ranked if "marksman_full_ap" not in route["preference_flags"]]
    selection_pool = preference_matched if len(preference_matched) >= limit else ranked
    selected: list[dict[str, Any]] = []
    seen_archetypes: set[str] = set()
    for route in selection_pool:
        if route["archetype"] in seen_archetypes and len(seen_archetypes) < min(limit, 3):
            continue
        selected.append(route)
        seen_archetypes.add(route["archetype"])
        if len(selected) >= limit:
            for selected_route in selected:
                selected_route.pop("source_priority", None)
            return selected
    for route in selection_pool:
        if route not in selected:
            selected.append(route)
        if len(selected) >= limit:
            break
    for route in selected:
        route.pop("source_priority", None)
    return selected


def recommend_build(
    context: dict[str, Any],
    *,
    cache_dir: str | Path = "data/cache",
    refresh_lolalytics: bool = False,
    items_map_path: str | Path = "data/ref/items_map.csv",
    preferences_path: str | Path = DEFAULT_USER_PREFERENCES_PATH,
    mode: str = DEFAULT_MODE,
    tier: str = DEFAULT_TIER,
    min_champions_analysed: int = 1_000_000,
    learned_item_adjustments: dict[int, float] | None = None,
    learned_feedback_events: int = 0,
) -> dict[str, Any]:
    active = context.get("active_player") or {}
    champion_slug = active.get("champion_slug") or ""
    if not champion_slug:
        raise ValueError("match context has no active champion")

    build_data = load_best_build(
        champion_slug,
        cache_dir=cache_dir,
        refresh=refresh_lolalytics,
        mode=mode,
        tier=tier,
        patches=(DEFAULT_PATCH, "14", "30"),
        min_champions_analysed=min_champions_analysed,
    )
    item_map = load_items_map(items_map_path)
    preferences = load_user_preferences(preferences_path)
    for item_id, adjustment in (learned_item_adjustments or {}).items():
        key = str(int(item_id))
        current = float((preferences.get("item_score_adjustments") or {}).get(key, 0.0))
        preferences["item_score_adjustments"][key] = round(current + float(adjustment), 3)
    threats = analyze_threats(context)
    allies = analyze_allies(context)

    built_set_params = build_data.get("params") or {"mode": mode, "tier": tier, "patch": DEFAULT_PATCH}
    primary_raw_sets = fetch_actual_built_sets_5(
        champion_slug,
        cache_dir=cache_dir,
        refresh=refresh_lolalytics,
        mode=built_set_params.get("mode", mode),
        tier=built_set_params.get("tier", tier),
        patch=built_set_params.get("patch", DEFAULT_PATCH),
    )
    built_sets = [{**row, "source_params": built_set_params, "source_priority": 0} for row in primary_raw_sets]
    built_set_windows = [{"params": built_set_params, "raw_sets": len(primary_raw_sets), "added_sets": len(primary_raw_sets)}]
    try:
        boot_stat_rows = fetch_boot_stats(
            champion_slug,
            cache_dir=cache_dir,
            refresh=refresh_lolalytics,
            mode=built_set_params.get("mode", mode),
            tier=built_set_params.get("tier", tier),
            patch=built_set_params.get("patch", DEFAULT_PATCH),
        )
    except Exception:
        boot_stat_rows = []
    if not boot_stat_rows:
        try:
            boot_stat_rows = fetch_boot_pair_stats(
                champion_slug,
                cache_dir=cache_dir,
                refresh=refresh_lolalytics,
                mode=built_set_params.get("mode", mode),
                tier=built_set_params.get("tier", tier),
                patch=built_set_params.get("patch", DEFAULT_PATCH),
            )
        except Exception:
            boot_stat_rows = []
    boot_stats_by_id = _boot_stats_by_id(boot_stat_rows, item_map)
    try:
        popular_item_rows = fetch_item_stats(
            champion_slug,
            table="Popular Items",
            cache_dir=cache_dir,
            refresh=refresh_lolalytics,
            mode=built_set_params.get("mode", mode),
            tier=built_set_params.get("tier", tier),
            patch=built_set_params.get("patch", DEFAULT_PATCH),
        )
    except Exception:
        popular_item_rows = []
    try:
        winning_item_rows = fetch_item_stats(
            champion_slug,
            table="Winning Items",
            cache_dir=cache_dir,
            refresh=refresh_lolalytics,
            mode=built_set_params.get("mode", mode),
            tier=built_set_params.get("tier", tier),
            patch=built_set_params.get("patch", DEFAULT_PATCH),
        )
    except Exception:
        winning_item_rows = []
    item_stats_by_id = _build_item_stats_by_id(popular_item_rows, winning_item_rows)
    seen_archetypes = {
        archetype
        for row in built_sets
        if (archetype := _set_archetype(row, item_map, champion_slug)) is not None
    }
    if champion_slug in MULTI_ROUTE_CHAMPIONS and len(seen_archetypes) < 2:
        for extra_patch in ("14", "30"):
            if str(extra_patch) == str(built_set_params.get("patch", DEFAULT_PATCH)):
                continue
            extra_params = {
                "mode": built_set_params.get("mode", mode),
                "tier": built_set_params.get("tier", tier),
                "patch": extra_patch,
            }
            extra_raw_sets = fetch_actual_built_sets_5(
                champion_slug,
                cache_dir=cache_dir,
                refresh=refresh_lolalytics,
                mode=extra_params["mode"],
                tier=extra_params["tier"],
                patch=extra_params["patch"],
            )
            added_sets: list[dict[str, Any]] = []
            for row in extra_raw_sets:
                archetype = _set_archetype(row, item_map, champion_slug)
                if archetype is None or archetype in seen_archetypes:
                    continue
                added_sets.append({**row, "source_params": extra_params, "source_priority": 1})
            built_sets.extend(added_sets)
            seen_archetypes.update(
                archetype
                for row in added_sets
                if (archetype := _set_archetype(row, item_map, champion_slug)) is not None
            )
            built_set_windows.append({"params": extra_params, "raw_sets": len(extra_raw_sets), "added_sets": len(added_sets)})
            if len(seen_archetypes) >= 2:
                break

    enriched = [enrich_item(item, item_map) | {"source_section": item.get("source_section")} for item in _flatten_lolalytics_items(build_data)]
    enriched_ids = {int(item["item_id"]) for item in enriched}
    for row in built_sets:
        for item_id, item_name in zip(row.get("item_ids", []), row.get("item_names", []), strict=False):
            if int(item_id) not in enriched_ids:
                enriched.append(_enrich_by_id(int(item_id), str(item_name), item_map) | {"source_section": "Actually Built Sets 5"})
                enriched_ids.add(int(item_id))
    enriched = _merge_item_stats(enriched, item_stats_by_id, item_map)

    scored: list[dict[str, Any]] = []
    for item in enriched:
        score, reasons = _score_item(item, threats, champion_slug, preferences)
        scored.append({**item, "score": round(score, 4), "reasons": reasons})

    by_id = {int(item["item_id"]): item for item in scored}
    routes = _build_routes(
        built_sets,
        item_map,
        by_id,
        build_data,
        threats,
        allies,
        champion_slug,
        preferences,
        boot_stats_by_id=boot_stats_by_id,
        limit=3,
    )
    if not routes:
        raise RuntimeError(
            "LoLalytics Actually Built Sets 5 did not contain a valid five completed-item set "
            f"for {champion_slug} with params {built_set_params}."
        )
    primary_route = routes[0]
    boot_options = _build_boot_options(
        primary_route.get("archetype", "balanced"),
        build_data,
        item_map,
        threats,
        boot_stats_by_id=boot_stats_by_id,
        limit=5,
    )
    primary_boots = boot_options[0] if boot_options else primary_route.get("boots")
    primary_items = primary_route.get("items", [])
    order = ([primary_boots] if primary_boots else []) + primary_items

    enemies = [
        {
            "champion": p.get("champion_id") or p.get("champion_name"),
            "slug": p.get("champion_slug"),
            "position": p.get("position"),
        }
        for p in context.get("enemies", [])
    ]
    ally_team = [
        {
            "champion": p.get("champion_id") or p.get("champion_name"),
            "slug": p.get("champion_slug"),
            "position": p.get("position"),
            "is_active": bool(p.get("is_active")),
        }
        for p in context.get("allies", [])
    ]
    data_health = assess_recommendation_data(
        fetched_at=build_data.get("fetched_at"),
        champions_analysed=int(build_data.get("champions_analysed") or 0),
        built_sets=len(primary_raw_sets),
        boots=len(boot_stat_rows),
        popular_items=len(popular_item_rows),
        winning_items=len(winning_item_rows),
    )

    return {
        "active_player": active,
        "game": context.get("game"),
        "ally_team": ally_team,
        "enemy_team": enemies,
        "threat_profile": threats.to_dict(),
        "ally_profile": allies.to_dict(),
        "composition_notes": _composition_notes(allies),
        "build": {
            "boots": primary_boots,
            "boot_options": boot_options,
            "items": primary_items,
            "routes": routes,
            "order": order,
            "source": {
                "lolalytics_url": build_data.get("source_url"),
                "lolalytics_patch": build_data.get("patch"),
                "lolalytics_params": build_data.get("params"),
                "champions_analysed": build_data.get("champions_analysed"),
                "data_fetched_at": build_data.get("fetched_at"),
                "data_health": data_health,
                "fallback_attempts": build_data.get("fallback_attempts"),
                "lolalytics_cache": build_data.get("cache_path"),
                "built_sets_cache": str(
                    built_sets_cache_path_for(
                        champion_slug,
                        cache_dir,
                        mode=built_set_params.get("mode", mode),
                        tier=built_set_params.get("tier", tier),
                        patch=built_set_params.get("patch", DEFAULT_PATCH),
                    )
                ),
                "built_sets_tab": "Actually Built Sets: 5",
                "built_sets_available": len(primary_raw_sets),
                "built_sets_considered": len(_route_candidate_sets(built_sets)),
                "route_candidate_min_pick_rate": MIN_ROUTE_CANDIDATE_PICK_RATE,
                "user_preferences_path": str(preferences_path),
                "user_preferences": preferences,
                "learned_feedback_events": int(learned_feedback_events),
                "built_set_windows": built_set_windows,
                "boot_stats_available": len(boot_stat_rows),
                "popular_items_available": len(popular_item_rows),
                "winning_items_available": len(winning_item_rows),
                "set_constraint": "five non-boot completed items must appear together in LoLalytics Actually Built Sets tab 5",
            },
        },
        "alternatives": [
            {
                "item_id": item["item_id"],
                "display_name": item.get("zh_tw_name") or item["name"],
                "name": item["name"],
                "zh_tw_name": item.get("zh_tw_name"),
                "score": item["score"],
                "reasons": item["reasons"][:3],
            }
            for item in sorted(scored, key=lambda x: x["score"], reverse=True)[:12]
        ],
        "compliance": {
            "data_used": [
                "Riot local Live Client Data API visible in-game player/champion/team data",
                "LoLalytics aggregate champion build statistics",
                "Riot Data Dragon public item metadata",
            ],
            "not_used": [
                "hidden player identification",
                "enemy summoner profile analysis",
                "private account or match-history scraping",
            ],
        },
    }


def recommend_from_snapshot(
    snapshot_path: str | Path,
    *,
    out_path: str | Path | None = None,
    refresh_lolalytics: bool = False,
    mode: str = DEFAULT_MODE,
    tier: str = DEFAULT_TIER,
    min_champions_analysed: int = 1_000_000,
    match_key: str | None = None,
    learned_item_adjustments: dict[int, float] | None = None,
    learned_feedback_events: int = 0,
) -> dict[str, Any]:
    snapshot = load_snapshot(snapshot_path)
    captured_at = None
    captured_text = (snapshot.get("snapshot_meta") or {}).get("captured_at")
    if captured_text:
        try:
            captured_at = datetime.fromisoformat(str(captured_text).replace("Z", "+00:00"))
        except ValueError:
            captured_at = None
    static_match_key = match_key or build_match_key(snapshot, captured_at=captured_at)
    context = build_match_context(snapshot, source_path=str(snapshot_path))
    result = recommend_build(
        context,
        refresh_lolalytics=refresh_lolalytics,
        mode=mode,
        tier=tier,
        min_champions_analysed=min_champions_analysed,
        learned_item_adjustments=learned_item_adjustments,
        learned_feedback_events=learned_feedback_events,
    )
    result = freeze_static_recommendation(result, match_key=static_match_key)
    if out_path:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result
