# -*- coding: utf-8 -*-
"""个性化分类器：基于人工校正标签（*_final）的 kNN 补标。

特征 = CLAP 音频嵌入（归一化）。对未人工确认的曲目，取最相似的 K 首
已确认曲目加权投票，输出 genre_tags / mood_tags，并回算唤醒度/效价。
校正数据越多越准——这就是「越用越懂你」的部分。
"""
import numpy as np

import config
import db as dbm
import mood_clap

K = 5          # 投票邻居数
TOP_K = 3      # 每首保留前 3 个标签
MIN_REFS = 3   # 一类标签的参考少于该数不做补标：避免单条错误校正污染整个曲库


def get_embedding(conn, row, model):
    """取归一化 CLAP 音频嵌入，首次提取后缓存进库（audio_emb 列）。"""
    if row.get("audio_emb"):
        v = np.asarray(row["audio_emb"], dtype=np.float32)
        return v / (float(np.linalg.norm(v)) + 1e-9)
    emb = np.asarray(model.get_audio_embedding_from_filelist([row["file_path"]])[0],
                     dtype=np.float32)
    emb = emb / (float(np.linalg.norm(emb)) + 1e-9)
    row["audio_emb"] = [round(float(x), 5) for x in emb]
    dbm.upsert(conn, row)
    return emb


def _knn_votes(emb, ref_embs, ref_tags):
    sims = ref_embs @ emb
    order = np.argsort(-sims)[:min(K, len(sims))]
    votes = {}
    for i in order:
        w = max(float(sims[i]), 0.0) + 1e-6
        for tag in ref_tags[i]:
            votes[tag] = votes.get(tag, 0.0) + w
    total = sum(votes.values()) or 1.0
    ranked = sorted(votes.items(), key=lambda kv: -kv[1])[:TOP_K]
    return [[t, round(v / total, 3)] for t, v in ranked]


def _coords(mood_tags):
    """由标签分布回算唤醒度/效价（词表外标签不参与坐标）。"""
    lut = {t["tag"]: (t["arousal"], t["valence"]) for t in config.MOOD_VOCAB}
    a = v = den = 0.0
    for tag, p in mood_tags:
        if tag in lut:
            a += p * lut[tag][0]
            v += p * lut[tag][1]
            den += p
    if den <= 0:
        return None, None
    return round(a / den, 3), round(v / den, 3)


def predict(conn, model=None):
    """对缺少人工确认标签的曲目补标：有训练模型用模型，否则 kNN。"""
    import trainer
    if trainer.has_trained():
        return trainer.predict_with_trained(conn)
    return predict_knn(conn, model=model)


def predict_knn(conn, model=None):
    """kNN 补标（冷启动/兜底）。返回统计信息 dict。"""
    rows = dbm.fetch_all(conn)
    refs_g = [r for r in rows if r.get("genre_tags_final")]
    refs_m = [r for r in rows if r.get("mood_tags_final")]
    if not refs_g and not refs_m:
        return {"predicted": 0,
                "message": "还没有人工确认标签（genre_final/mood_final），"
                           "请先校正几首再智能补标。"}

    # 参考不足时宁缺毋滥：单条/少量错误校正不该被放大到整个曲库
    notes = []
    if refs_g and len(refs_g) < MIN_REFS:
        notes.append("曲风参考仅 {} 首（少于 {} 首），跳过曲风补标".format(
            len(refs_g), MIN_REFS))
        refs_g = []
    if refs_m and len(refs_m) < MIN_REFS:
        notes.append("听感参考仅 {} 首（少于 {} 首），跳过听感补标".format(
            len(refs_m), MIN_REFS))
        refs_m = []
    if not refs_g and not refs_m:
        return {"predicted": 0, "message": "；".join(notes)}

    model = model or mood_clap.get_model()

    def _pack(refs, key):
        embs, tags = [], []
        for r in refs:
            embs.append(get_embedding(conn, r, model))
            tags.append([t for t, _p in (r.get(key) or [])])
        return np.stack(embs), tags

    ref_embs_g = ref_tags_g = None
    if refs_g:
        ref_embs_g, ref_tags_g = _pack(refs_g, "genre_tags_final")
    ref_embs_m = ref_tags_m = None
    if refs_m:
        ref_embs_m, ref_tags_m = _pack(refs_m, "mood_tags_final")

    n = 0
    for r in rows:
        need_g = bool(refs_g) and not r.get("genre_tags_final")
        need_m = bool(refs_m) and not r.get("mood_tags_final")
        if not (need_g or need_m):
            continue
        emb = get_embedding(conn, r, model)
        if need_g:
            r["genre_tags"] = _knn_votes(emb, ref_embs_g, ref_tags_g)
        if need_m:
            r["mood_tags"] = _knn_votes(emb, ref_embs_m, ref_tags_m)
            r["arousal"], r["valence"] = _coords(r["mood_tags"])
        dbm.upsert(conn, r)
        n += 1
    return {"predicted": n,
            "message": "已按 {} 首曲风 / {} 首听感校正数据，补标 {} 首。{}".format(
                len(refs_g), len(refs_m), n,
                ("；" + "；".join(notes)) if notes else "")}
