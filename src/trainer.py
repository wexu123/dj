# -*- coding: utf-8 -*-
"""路线 A：冻结 CLAP 嵌入 + 训练小分类头（多标签逻辑回归，纯 numpy）。

数据 = 库里的人工校正标签（*_final）+ audio_emb 嵌入向量。
训练后模型保存到 models/，classifier.predict 自动优先使用、kNN 兜底；
校正数据不足时给出明确的最低数量提示，攒够再训。
"""
import json
import os
import time

import numpy as np

import classifier
import db as dbm

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(BASE, "models")

MIN_TOTAL = 30       # 最低校正曲目数
MIN_PER_CLASS = 3    # 每个标签最低样本数（不足的类不进模型，会提示）
HOLDOUT = 0.25       # 留出验证比例
EPOCHS = 400         # 训练轮数（小数据很快）
LR = 0.05
L2 = 1e-3
BATCH = 32

KINDS = {
    "genre": "genre_tags_final",
    "mood": "mood_tags_final",
}


def collect(conn, key):
    """收集训练数据 (X, tag_lists)；嵌入缺失时自动提取并缓存。"""
    import mood_clap
    clap = mood_clap.get_model()
    rows = dbm.fetch_all(conn)
    X, tag_lists = [], []
    for r in rows:
        final = r.get(key)
        if not final:
            continue
        X.append(classifier.get_embedding(conn, r, clap))
        tag_lists.append([t for t, _p in final])
    return (np.stack(X) if X else np.zeros((0, 512), dtype=np.float32)), tag_lists


def _fit(X, Y, seed=42):
    """sigmoid + BCE + Adam，多标签逻辑回归。返回 (W, b)。"""
    n, d = X.shape
    C = Y.shape[1]
    rng = np.random.default_rng(seed)
    W = rng.normal(0, 0.01, (d, C))
    b = np.zeros(C)
    mW = np.zeros_like(W); vW = np.zeros_like(W)
    mb = np.zeros_like(b); vb = np.zeros_like(b)
    t = 0
    for _epoch in range(EPOCHS):
        idx = rng.permutation(n)
        for s in range(0, n, BATCH):
            bidx = idx[s:s + BATCH]
            xb, yb = X[bidx], Y[bidx]
            p = 1.0 / (1.0 + np.exp(-(xb @ W + b)))
            gW = xb.T @ (p - yb) / len(xb) + L2 * W
            gb = (p - yb).mean(axis=0)
            t += 1
            mW = 0.9 * mW + 0.1 * gW;  vW = 0.999 * vW + 0.001 * gW * gW
            mb = 0.9 * mb + 0.1 * gb;  vb = 0.999 * vb + 0.001 * gb * gb
            W -= LR * (mW / (1 - 0.9 ** t)) / (np.sqrt(vW / (1 - 0.999 ** t)) + 1e-8)
            b -= LR * (mb / (1 - 0.9 ** t)) / (np.sqrt(vb / (1 - 0.999 ** t)) + 1e-8)
    return W, b


def _sigmoid_scores(X, W, b):
    return 1.0 / (1.0 + np.exp(-(X @ W + b)))


def _eval(Xte, Yte, W, b, top_k=3):
    if len(Xte) == 0:
        return {}
    S = _sigmoid_scores(Xte, W, b)
    order = np.argsort(-S, axis=1)
    true = {i: set(np.flatnonzero(Yte[i])) for i in range(len(Yte))}
    top1 = np.mean([1.0 if order[i][0] in true[i] else 0.0 for i in range(len(Xte))])
    topk = np.mean([
        1.0 if true[i] & set(order[i][:top_k]) else 0.0 for i in range(len(Xte))])
    subset = np.mean([
        1.0 if set(np.flatnonzero(S[i] >= 0.5)) == true[i] else 0.0
        for i in range(len(Xte))])
    return {"top1": round(float(top1), 3), "top3": round(float(topk), 3),
            "subset": round(float(subset), 3), "n_test": len(Xte)}


def train(conn):
    """训练曲风/听感分类器。返回 report dict（每个 kind 的结果或跳过原因）。"""
    report = {}
    os.makedirs(MODELS_DIR, exist_ok=True)
    for kind, key in KINDS.items():
        X, tag_lists = collect(conn, key)
        n = len(tag_lists)
        classes = sorted({t for tags in tag_lists for t in tags})
        counts = {c: sum(1 for tags in tag_lists if c in tags) for c in classes}
        keep = [c for c in classes if counts[c] >= MIN_PER_CLASS]
        dropped = {c: counts[c] for c in classes if counts[c] < MIN_PER_CLASS}

        if n < MIN_TOTAL or not keep:
            miss = "，".join("{}({}/{})".format(c, counts[c], MIN_PER_CLASS)
                            for c in classes) or "无"
            report[kind] = {
                "ok": False,
                "message": ("{}分类器：校正数据不足（当前 {} 首，需 ≥{} 且每类 ≥{} 首）。"
                            "类样本量：{}。继续在校正列确认标签后重试。").format(
                    "曲风" if kind == "genre" else "听感",
                    n, MIN_TOTAL, MIN_PER_CLASS, miss),
            }
            continue

        cidx = {c: i for i, c in enumerate(keep)}
        Y = np.zeros((n, len(keep)))
        for i, tags in enumerate(tag_lists):
            for t in tags:
                if t in cidx:
                    Y[i, cidx[t]] = 1.0

        rng = np.random.default_rng(42)
        idx = rng.permutation(n)
        n_test = max(1, int(round(n * HOLDOUT)))
        te, tr = idx[:n_test], idx[n_test:]
        W, b = _fit(X[tr], Y[tr])
        metrics = _eval(X[te], Y[te], W, b)

        meta = {
            "kind": kind, "classes": keep, "dropped": dropped,
            "n_train": int(len(tr)), "n_test": int(len(te)),
            "metrics": metrics,
            "trained_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        np.savez(os.path.join(MODELS_DIR, kind + "_clf.npz"), W=W, b=b)
        with open(os.path.join(MODELS_DIR, kind + "_clf.json"), "w",
                  encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=1)

        m = metrics
        report[kind] = {
            "ok": True,
            "message": ("{}分类器：{} 首训练（{} 类）· 留出 {} 首验证 "
                        "top-1 {:.0%} · top-3 {:.0%} · 子集 {:.0%}").format(
                "曲风" if kind == "genre" else "听感",
                len(tr), len(keep), len(te),
                m.get("top1", 0), m.get("top3", 0), m.get("subset", 0)),
            "meta": meta,
        }
    return report


def has_trained():
    """返回已训练模型的 meta 列表（genre/mood 各自判断）。"""
    out = {}
    for kind in KINDS:
        npz = os.path.join(MODELS_DIR, kind + "_clf.npz")
        meta = os.path.join(MODELS_DIR, kind + "_clf.json")
        if os.path.exists(npz) and os.path.exists(meta):
            with open(meta, encoding="utf-8") as f:
                out[kind] = json.load(f)
    return out


def predict_with_trained(conn):
    """用已训练分类器补标（多标签 sigmoid，top-3）。返回 {predicted, message}。"""
    import mood_clap
    metas = has_trained()
    rows = dbm.fetch_all(conn)
    clap = mood_clap.get_model()
    n = 0
    for r in rows:
        changed = False
        emb = None
        for kind in KINDS:
            if kind == "genre" and r.get("genre_tags_final"):
                continue
            if kind == "mood" and r.get("mood_tags_final"):
                continue
            if kind not in metas:
                continue
            if emb is None:
                emb = classifier.get_embedding(conn, r, clap)
            meta = metas[kind]
            npz = np.load(os.path.join(MODELS_DIR, kind + "_clf.npz"))
            W, b = npz["W"], npz["b"]
            scores = 1.0 / (1.0 + np.exp(-(emb @ W + b)))
            order = np.argsort(-scores)[::-1][:3]
            tags = [[meta["classes"][i], round(float(scores[i]), 3)]
                    for i in order if scores[i] > 0.2]
            if kind == "genre":
                r["genre_tags"] = tags or [[meta["classes"][int(order[0])],
                                            round(float(scores[order[0]]), 3)]]
            else:
                r["mood_tags"] = tags or [[meta["classes"][int(order[0])],
                                           round(float(scores[order[0]]), 3)]]
                r["arousal"], r["valence"] = classifier._coords(r["mood_tags"])
            changed = True
        if changed:
            dbm.upsert(conn, r)
            n += 1
    src = "、".join("{}(训练 {} 首)".format(
        "曲风" if k == "genre" else "听感", m.get("n_train", 0))
        for k, m in metas.items())
    return {"predicted": n,
            "message": "已用训练分类器[{}]补标 {} 首。".format(src, n)}
