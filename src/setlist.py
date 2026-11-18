# -*- coding: utf-8 -*-
"""阶段四：规则排歌器。

硬约束（过滤）：Camelot 调性兼容、BPM ±6%（含 half/double）
软目标（打分）：能量符合演出段落区间，过渡附情绪带动提示
"""
import config


def parse_camelot(code):
    if not code or len(code) < 2:
        return None
    try:
        return int(code[:-1]), code[-1].upper()
    except ValueError:
        return None


def camelot_compatible(a, b):
    """同数字（相对大小调）或同字母相邻数字（轮盘 ±1）视为兼容。"""
    pa, pb = parse_camelot(a), parse_camelot(b)
    if not pa or not pb:
        return False
    (na, la), (nb, lb) = pa, pb
    if na == nb:
        return True
    if la == lb:
        return min(abs(na - nb), 12 - abs(na - nb)) == 1
    return False


def bpm_compatible(b1, b2, tol=None):
    tol = config.BPM_TOLERANCE if tol is None else tol
    if not b1 or not b2:
        return False
    for x, y in ((b1, b2), (b1, b2 * 2), (b1 * 2, b2)):
        if abs(x - y) / y <= tol:
            return True
    return False


def energy_band(progress):
    for lo_p, hi_p, lo_e, hi_e, name in config.ENERGY_BANDS:
        if lo_p <= progress < hi_p:
            return lo_e, hi_e, name
    lo_e, hi_e, name = config.ENERGY_BANDS[-1][2:]
    return lo_e, hi_e, name


def transition_hint(prev, cur):
    delta = cur["energy"] - prev["energy"]
    if delta > config.ENERGY_DELTA_PUSH:
        direction = "推向高潮"
    elif delta < config.ENERGY_DELTA_DROP:
        direction = "落地收束"
    else:
        direction = "平稳延伸"
    return "能量 {:+.1f}，{}→{}，{}".format(
        delta, prev.get("camelot") or "?", cur.get("camelot") or "?", direction)


def generate(tracks, start_id=None, minutes=60):
    """贪心生成 setlist。返回 (entries, warnings)。

    entry: {"track": ..., "hint": ..., "progress": ..., "stage": ...}
    """
    warnings = []
    usable = [t for t in tracks if t.get("bpm") and t.get("energy") is not None]
    if not usable:
        return [], ["曲库为空或缺少 BPM/能量数据，请先运行 scan。"]

    if start_id:
        current = next((t for t in usable if t["id"] == start_id), None)
        if current is None:
            warnings.append("起始曲 {} 不存在，自动改用能量最低曲目开场。".format(start_id))
    else:
        current = None
    if current is None:
        current = min(usable, key=lambda t: t["energy"])

    target_s = minutes * 60.0
    used = {current["id"]}
    entries = [{"track": current, "hint": "开场曲", "progress": 0.0,
                "stage": energy_band(0.0)[2]}]
    total = current.get("duration") or 240.0

    while total < target_s:
        progress = min(total / target_s, 1.0)
        lo, hi, stage = energy_band(progress)
        candidates = []
        for t in usable:
            if t["id"] in used:
                continue
            if not camelot_compatible(current.get("camelot"), t.get("camelot")):
                continue
            if not bpm_compatible(current.get("bpm"), t.get("bpm")):
                continue
            if not (lo - config.BAND_BUFFER <= t["energy"] <= hi + config.BAND_BUFFER):
                continue
            candidates.append(t)
        if not candidates:
            # 能量为软约束：放宽区间但保留 Camelot/BPM 硬约束，保证 set 能排满
            for t in usable:
                if t["id"] in used:
                    continue
                if not camelot_compatible(current.get("camelot"), t.get("camelot")):
                    continue
                if not bpm_compatible(current.get("bpm"), t.get("bpm")):
                    continue
                candidates.append(t)
            if candidates:
                warnings.append(
                    "已播 {:.0f} 分钟，{} 段落无能量匹配曲目，已放宽能量约束。".format(
                        total / 60.0, stage))
        if not candidates:
            warnings.append(
                "已播 {:.0f} 分钟，硬约束下无可选曲目（{} 段落），生成提前结束。".format(
                    total / 60.0, stage))
            break
        # 软目标：能量越贴近段落区间中点越好
        mid = (lo + hi) / 2.0
        candidates.sort(key=lambda t: abs(t["energy"] - mid))
        current = candidates[0]
        used.add(current["id"])
        total += current.get("duration") or 240.0
        entries.append({
            "track": current,
            "hint": transition_hint(entries[-1]["track"], current),
            "progress": round(progress, 3),
            "stage": stage,
        })
    return entries, warnings


def format_setlist(entries, warnings):
    lines = []
    total = 0.0
    for i, e in enumerate(entries, 1):
        t = e["track"]
        total += t.get("duration") or 0
        lines.append(
            "{:02d}. {:28s} {:>5.0f} BPM  {:>4s}  能量 {:>4.1f}  [{:>2s}]  {}".format(
                i, (t.get("title") or t["id"])[:28],
                t.get("bpm") or 0, t.get("camelot") or "?",
                t.get("energy") or 0, e["stage"], e["hint"]))
    lines.append("-" * 78)
    lines.append("共 {} 首 · {:.0f} 分钟".format(len(entries), total / 60.0))
    for w in warnings:
        lines.append("⚠ " + w)
    return "\n".join(lines)
