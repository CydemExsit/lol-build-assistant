from __future__ import annotations

from pathlib import Path


def _name(item: dict) -> str:
    return str(item.get("display_name") or item.get("zh_tw_name") or item.get("name") or item.get("item_id"))


def _percent(value) -> str:
    return f"{float(value) * 100:.2f}%" if isinstance(value, (int, float)) else "-"


def write_recommendation_markdown(result: dict, out_path: str | Path) -> None:
    active = result.get("active_player") or {}
    session = result.get("session") or {}
    source = result.get("build", {}).get("source", {})
    lines = [
        "# LoL Build Assistant 賽前方案",
        "",
        f"- 英雄：{active.get('champion_id') or active.get('champion_name')}",
        f"- 產生時間：{session.get('generated_at')}",
        "- 狀態：本場靜態方案已凍結，遊戲中不更新",
        f"- LoLalytics 樣本：{int(source.get('champions_analysed') or 0):,}",
        "",
        "## 我方陣容",
        "",
    ]
    lines.extend(f"- {player.get('champion')}" for player in result.get("ally_team", []))
    lines.extend(["", "## 敵方陣容", ""])
    lines.extend(f"- {player.get('champion')}" for player in result.get("enemy_team", []))
    damage = result.get("damage_analysis") or {}
    mix = damage.get("damage_mix") or {}
    if mix:
        lines.extend(
            [
                "",
                "## 敵方傷害輪廓",
                "",
                (
                    f"- 估算：物理 {_percent(mix.get('physical'))} / "
                    f"魔法 {_percent(mix.get('magic'))} / 真實 {_percent(mix.get('true'))}"
                ),
                f"- 整隊輸出權重：{_percent(damage.get('output_weight'))}",
                f"- 判斷：{damage.get('label', '-')}；{damage.get('defense_label', '-')}",
            ]
        )
        defensive_options = result.get("build", {}).get("defensive_options") or []
        if defensive_options:
            lines.append(
                "- 大型防裝備選："
                + "、".join(
                    f"{_name(item)}（{item.get('reason', '')}）"
                    for item in defensive_options
                )
            )
    lines.extend(["", "## 鞋子統計", ""])
    for index, boot in enumerate(result.get("build", {}).get("boot_options", []), start=1):
        lines.append(
            f"{index}. {_name(boot)}：勝率 {_percent(boot.get('win_rate'))} / "
            f"選取率 {_percent(boot.get('pick_rate'))} / {int(boot.get('games') or 0):,} 場"
        )
    lines.extend(["", "## 五件套方案", ""])
    for index, route in enumerate(result.get("build", {}).get("routes", []), start=1):
        stats = route.get("set_stats") or {}
        confidence = route.get("confidence") or {}
        lines.append(f"### 方案 {index}：{route.get('label')}")
        lines.append("")
        lines.append("- 順序：" + " > ".join(_name(item) for item in route.get("items", [])))
        starter = route.get("starter_option") or {}
        if starter.get("items"):
            starter_names = " + ".join(_name(item) for item in starter["items"])
            lines.append(f"- 起手銜接：{starter_names}（{int(starter.get('total_gold') or 0):,} 金）")
        lines.append(
            f"- 統計：勝率 {_percent(stats.get('win_rate'))} / "
            f"選取率 {_percent(stats.get('pick_rate'))} / {int(stats.get('games') or 0):,} 場"
        )
        lines.append(f"- 可信度：{confidence.get('label', '-')}")
        for reminder in route.get("starting_reminders", []):
            lines.append(f"- 開場提醒：{reminder}")
        for reason in route.get("reasons", []):
            lines.append(f"- {reason}")
        lines.append("")
    lines.extend(
        [
            "## 合規邊界",
            "",
            "- 推薦只使用賽前可見英雄陣容、聚合統計、靜態物品資料與過往本機回饋。",
            "- 不使用當場金錢、物品、分數、事件、冷卻或位置，也不在遊戲中更新方案。",
            "- 所有方案保留玩家選擇，不替玩家執行或下達即時指令。",
            "",
            str((result.get("compliance") or {}).get("legal_notice") or ""),
        ]
    )
    target = Path(out_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
