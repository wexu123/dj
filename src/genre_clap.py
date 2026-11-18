# -*- coding: utf-8 -*-
"""阶段一（补）：CLAP 零样本曲风标签。

按 config.GENRE_VOCAB 的提示词对每首歌打分（余弦相似度 -> softmax），
取 top-K 写库：genre_tags。复用 mood_clap.get_model（同一 CLAP 模型跑在独显）。
"""
import numpy as np

import config
from mood_clap import get_model

TEMPERATURE = 0.1   # softmax 温度：越小标签越尖锐
TOP_K = 3           # 每首保留前 3 个标签

_text_cache = {}


def _text_matrix(model):
    if "genre" not in _text_cache:
        vocab = list(config.GENRE_VOCAB)
        embs = []
        for item in vocab:
            e = model.get_text_embedding(item["prompts"])
            v = np.mean(e, axis=0)
            embs.append(v / (np.linalg.norm(v) + 1e-9))
        _text_cache["genre"] = (vocab, np.stack(embs))
    return _text_cache["genre"]


def score_files(file_paths, model=None):
    """返回与 file_paths 等长的结果：{genre_tags: [[标签, 概率], ...]}。"""
    model = model or get_model()
    vocab, text_mat = _text_matrix(model)

    results = []
    for path in file_paths:
        audio_emb = model.get_audio_embedding_from_filelist([path])
        a = audio_emb[0]
        a = a / (np.linalg.norm(a) + 1e-9)
        sims = text_mat @ a
        probs = np.exp(sims / TEMPERATURE)
        probs = probs / probs.sum()
        order = np.argsort(-probs)[:TOP_K]
        results.append({
            "genre_tags": [[vocab[i]["tag"], round(float(probs[i]), 3)] for i in order],
        })
    return results
