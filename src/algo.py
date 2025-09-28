from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Tuple
import numpy as np
import pandas as pd
from .io_schema import WinningItem, BuiltSet

@dataclass
class BuildResult:
    boots: str | None
    order: List[str]
    rationale: Dict

EPS = 1e-9

def _logit(p: float) -> float:
    p = min(max(p, EPS), 1 - EPS)
    return np.log(p / (1 - p))

def load_winning_items(path: str) -> List[WinningItem]:
    df = pd.read_csv(path)
    return [
        WinningItem(
            name=row["name"],
            win_rate=float(row["win_rate"]),
            pick_rate=float(row["pick_rate"]),
            sample_size=int(row["sample_size"]),
        )
        for _, row in df.iterrows()
    ]

def load_built_sets(path: str) -> List[BuiltSet]:
    df = pd.read_csv(path)
    sets: List[BuiltSet] = []
    for _, row in df.iterrows():
        items = [s.strip() for s in str(row["items"]).split("|") if s.strip()]
        sets.append(
            BuiltSet(
                items=items,
                set_win_rate=float(row["set_win_rate"]),
                set_pick_rate=float(row["set_pick_rate"]),
                set_sample_size=int(row["set_sample_size"]),
            )
        )
    return sets

def _dynamic_candidates(winning: List[WinningItem]) -> Tuple[List[WinningItem], Dict]:
    import numpy as np
    pr = np.array([w.pick_rate for w in winning], dtype=float)
    wr = np.array([w.win_rate for w in winning], dtype=float)
    ss = np.array([w.sample_size for w in winning], dtype=float)

    P25 = float(np.percentile(pr, 25)) if pr.size else 0.0
    P50 = float(np.percentile(pr, 50)) if pr.size else 0.0
    P75 = float(np.percentile(pr, 75)) if pr.size else 0.0
    W50 = float(np.percentile(wr, 50)) if wr.size else 0.0
    W75 = float(np.percentile(wr, 75)) if wr.size else 0.0
    GlobalAvgWin = float(np.average(wr, weights=np.maximum(ss, 1))) if wr.size else 0.5
    max_pick = float(pr.max()) if pr.size else 0.0

    # 原始門檻
    PickCut = max(P50, 0.10)
    WinCut  = max(W50, GlobalAvgWin)

    def select_by(pick_cut, win_cut, cold_mult):
        C = []
        for w in winning:
            base_ok = (w.pick_rate >= pick_cut and w.win_rate >= win_cut)
            high_win_cold_fix = (w.win_rate >= W75 and w.pick_rate >= cold_mult * max_pick)
            if base_ok or high_win_cold_fix:
                C.append(w)
        return C

    C0 = select_by(PickCut, WinCut, cold_mult=0.50)

    # 回退1：若為空，放寬到 P25 與 W50，並放寬冷門修補
    if not C0:
        C0 = select_by(max(P25, 0.05), W50, cold_mult=0.30)

    # 回退2：若仍為空，取 win*pick 前 8 作為候選
    if not C0:
        C0 = sorted(winning, key=lambda w: w.win_rate * w.pick_rate, reverse=True)[:8]

    meta = dict(P25=P25, P50=P50, P75=P75, W50=W50, W75=W75,
                GlobalAvgWin=GlobalAvgWin, PickCut=PickCut, WinCut=WinCut, max_pick=max_pick)
    return C0, meta

def _topK_sets(sets: List[BuiltSet], K: int = 50, cover: float = 0.80) -> List[BuiltSet]:
    if not sets:
        return []
    import pandas as pd
    df = pd.DataFrame([{"i": i, "samples": s.set_sample_size, "pick": s.set_pick_rate} for i, s in enumerate(sets)])
    if df.empty:
        return []
    df = df.sort_values(by=["samples", "pick"], ascending=[False, False])
    ordered = [sets[int(i)] for i in df["i"].tolist()]
    out, cum_pick = [], 0.0
    for s in ordered:
        out.append(s)
        cum_pick += s.set_pick_rate
        if len(out) >= K or cum_pick >= cover:
            break
    return out


def _cooccur_freq(cands: List[WinningItem], top_sets: List[BuiltSet]) -> Dict[str, float]:
    freq: Dict[str, float] = {}
    K = max(len(top_sets), 1)
    for c in cands:
        cnt = sum(1 for s in top_sets if c.name in s.items)
        freq[c.name] = cnt / K
    return freq

def _score_item(w: WinningItem, weight: float) -> float:
    return 0.6 * _logit(w.win_rate) + 0.4 * np.log(max(w.pick_rate, EPS)) + np.log(max(weight, EPS))

def _support(selected: List[str], sets_sub: List[BuiltSet]) -> Tuple[float, List[BuiltSet]]:
    # 篩掉不含全部 selected 的套裝
    filt = [s for s in sets_sub if all(it in s.items for it in selected)]
    K = max(len(sets_sub), 1)
    return (len(filt) / K, filt)

def _conditional_choice(selected4: List[str], remain: List[WinningItem], sets_sub: List[BuiltSet]) -> str:
    # 在已選4件條件下，計算每個候選的條件 pick 與條件 win
    # 取 rank 折衷最高者
    stats = []
    cond_sets = [s for s in sets_sub if all(it in s.items for it in selected4)]
    if not cond_sets and sets_sub:
        cond_sets = sets_sub[:]  # 回退
    total_pick = sum(s.set_pick_rate for s in cond_sets) + EPS
    for w in remain:
        pick = sum(s.set_pick_rate for s in cond_sets if w.name in s.items) / total_pick
        # 以包含 w 的子集勝率與不含 w 的子集勝率比值作微調
        with_w = [s for s in cond_sets if w.name in s.items]
        without_w = [s for s in cond_sets if w.name not in s.items]
        win_with = np.average([s.set_win_rate for s in with_w]) if with_w else 0.0
        win_without = np.average([s.set_win_rate for s in without_w]) if without_w else 0.0
        lift = (win_with + EPS) / (win_without + EPS)
        stats.append((w.name, pick, win_with, lift))
    if not stats:
        return remain[0].name
    # 以 pick 與 win 排名反序名次求平均
    df = pd.DataFrame(stats, columns=["name", "pick", "win", "lift"])
    df["rpick"] = df["pick"].rank(ascending=False, method="average")
    df["rwin"] = df["win"].rank(ascending=False, method="average")
    df["score"] = 0.5 * (1.0 / df["rpick"]) + 0.5 * (1.0 / df["rwin"])
    # 若接近，選 lift 較高者
    df = df.sort_values(by=["score", "lift"], ascending=[False, False])
    return str(df.iloc[0]["name"])

def _order_by_position(final_items: List[str], sets_sub: List[BuiltSet]) -> List[str]:
    # 以包含全部 final_items 的套裝，計算每件在序列中的加權平均位次
    contain_all = [s for s in sets_sub if all(it in s.items for it in final_items)]
    if not contain_all:
        # 回退：維持原順序
        return final_items[:]
    pos_sum = {it: 0.0 for it in final_items}
    weight_sum = {it: 0.0 for it in final_items}
    for s in contain_all:
        for idx, it in enumerate(s.items, start=1):
            if it in pos_sum:
                pos_sum[it] += idx * s.set_pick_rate
                weight_sum[it] += s.set_pick_rate
    avg_pos = {it: (pos_sum[it] / max(weight_sum[it], EPS)) for it in final_items}
    return sorted(final_items, key=lambda x: avg_pos.get(x, 999.0))

def pick_build(
    winning: List[WinningItem],
    sets: List[BuiltSet],
    *,
    explain: bool = False,
    topk: int = 50,
    cover: float = 0.80
) -> BuildResult:
    trace = {}

    # 1) 動態候選池 + 回退
    C0, meta = _dynamic_candidates(winning)
    if explain:
        trace["winning_items"] = [
            {"name": w.name, "win": w.win_rate, "pick": w.pick_rate, "n": w.sample_size}
            for w in winning
        ]
        trace["C0"] = [w.name for w in C0]
        trace["thresholds"] = meta

    # 2) 取實際套裝 top-K
    top_sets = _topK_sets(sets, K=topk, cover=cover if sets else 0.10)
    if explain:
        trace["top_sets_used"] = len(top_sets)

    # 3) 共現一致性
    freq = _cooccur_freq(C0, top_sets)
    median_freq = float(np.median(list(freq.values()))) if freq else 0.0
    Tau = max(median_freq, 0.5)
    C1 = [w for w in C0 if freq.get(w.name, 0.0) >= Tau] or C0[:]
    if explain:
        trace["cooccur_freq"] = freq
        trace["Tau"] = Tau
        trace["C1"] = [w.name for w in C1]

    # 4) 迭代擴充
    selected, supports = [], []
    total_samples = sum(s.set_sample_size for s in top_sets) + EPS
    weight_by_item = {w.name: (sum(s.set_sample_size for s in top_sets if w.name in s.items) / total_samples) for w in C1}
    C1_sorted = sorted(C1, key=lambda w: _score_item(w, weight_by_item.get(w.name, 1e-6)), reverse=True)

    decisions = []
    for w in C1_sorted:
        trial = selected + [w.name]
        sup, sub_sets = _support(trial, top_sets)
        SupportCut = max(0.25, float(np.median(supports)) if supports else 1.0)
        action = "accept"
        if sup < SupportCut:
            sup0, sub0 = _support(selected, top_sets)
            win_with  = np.average([s.set_win_rate for s in sub_sets]) if sub_sets else 0.0
            win_without = np.average([s.set_win_rate for s in sub0]) if sub0 else 0.0
            lift = (win_with + EPS) / (win_without + EPS)
            if _score_item(w, weight_by_item.get(w.name, 1e-6)) > 0 and lift > 1.02:
                selected = trial
                supports.append(sup)
                action = "accept_by_lift"
            else:
                action = "reject"
        else:
            selected = trial
            supports.append(sup)
        decisions.append({"item": w.name, "sup": sup, "cut": SupportCut, "action": action})
        if len(selected) >= 4:
            break

    # 5) 最後一件
    remain = [w for w in C1_sorted if w.name not in selected]
    if len(selected) < 5 and remain:
        last = _conditional_choice(selected, remain, top_sets)
        if last not in selected:
            selected.append(last)

    # 補滿
    if len(selected) < 5:
        pool = [w for w in winning if w.name not in selected]
        pool_sorted = sorted(pool, key=lambda w: w.win_rate * w.pick_rate, reverse=True)
        for w in pool_sorted:
            selected.append(w.name)
            if len(selected) >= 5:
                break

    # 6) 位次決定
    ordered = _order_by_position(selected[:5], top_sets)

    boots = "狂戰士護脛"
    rationale = {
        "dynamic_thresholds": {
            "P50": meta.get("P50"), "P75": meta.get("P75"),
            "W50": meta.get("W50"), "W75": meta.get("W75"),
            "GlobalAvgWin": meta.get("GlobalAvgWin"),
            "PickCut": meta.get("PickCut"), "WinCut": meta.get("WinCut"),
            "Tau": Tau
        },
        "supports": supports,
        "top_sets_used": len(top_sets),
        "note": "加入 explain 軌跡與參數可調。",
    }
    if explain:
        rationale["explain"] = {
            "decisions": decisions,
            "selected_before_ordering": selected,
            "ordered_final": ordered
        }

    return BuildResult(boots=boots, order=ordered, rationale=rationale)