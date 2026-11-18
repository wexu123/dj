# -*- coding: utf-8 -*-
"""以歌选歌：为指定核心歌曲推荐相似参考曲。

相似度得分 = EMBED_W × 音频嵌入余弦相似度 + ATTR_W × 混音属性分
（调性兼容 / BPM 接近 / 能量接近），并输出「为什么相似」标签。
嵌入缺失时自动提取并缓存进库。
"""
import numpy as np

import classifier
import db as dbm
import setlist as sl

EMBED_W = 0.65   # 听感相似权重
ATTR_W = 0.35    # 混音属性权重
DEFAULT_N = 12
LISTEN_COS = 0.45  # 余弦超过该值追加「听感相近」标签


def _attr_score(prev, cur):
    """混音属性分 (0-1) 及原因标签。"""
    score = 0.0
    reasons = []
    if sl.camelot_compatible(prev.get("camelot"), cur.get("camelot")):
        score += 0.4
        reasons.append("调性兼容")
    if sl.bpm_compatible(prev.get("bpm"), cur.get("bpm")):
        score += 0.35
        reasons.append("BPM 接近")
    pe, ce = prev.get("energy"), cur.get("energy")
    if pe is not None and ce is not None and abs(pe - ce) <= 1.5:
        score += 0.25
        reasons.append("能量接近")
    return score, reasons


def similar_tracks(conn, track_id, n=DEFAULT_N):
    """返回 (target, results)；results 每项 (track, score, reasons, cos)。"""
    rows = dbm.fetch_all(conn)
    target = next((r for r in rows if r["id"] == track_id), None)
    if target is None:
        return None

    from mood_clap import get_model
    model = get_model()
    t_emb = classifier.get_embedding(conn, target, model)

    results = []
    for r in rows:
        if r["id"] == track_id:
            continue
        emb = classifier.get_embedding(conn, r, model)
        cos = float(t_emb @ emb)
        attr, reasons = _attr_score(target, r)
        if cos >= LISTEN_COS:
            reasons = ["听感相近"] + reasons
        score = EMBED_W * max(cos, 0.0) + ATTR_W * attr
        results.append((r, score, reasons, cos))
    results.sort(key=lambda x: -x[1])
    return target, results[:n]
