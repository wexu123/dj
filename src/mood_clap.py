# -*- coding: utf-8 -*-
"""阶段二 A：CLAP 零样本听感标签。

按 config.MOOD_VOCAB 的提示词对每首歌打分（余弦相似度 -> softmax），
得到 mood_tags，并映射唤醒度 x 效价坐标。写库：mood_tags / arousal / valence。
"""
import numpy as np
import os

import config

TEMPERATURE = 0.1   # softmax 温度：越小标签越尖锐
TOP_K = 3           # 每首保留前 3 个标签

_model = None
_text_cache = {}


def _ensure_ckpt():
    """确保 CLAP 权重就位；缺失时自动下载（约 1.8GB，仅首次）。"""
    import laion_clap
    from pathlib import Path
    path = Path(laion_clap.__file__).parent / "630k-audioset-best.pt"
    if path.exists():
        return
    url = os.environ.get(
        "DJ_CLAP_CKPT_URL",
        "https://hf-mirror.com/lukewys/laion_clap/resolve/main/"
        "630k-audioset-best.pt?download=true",
    )
    print("首次运行：下载 CLAP 权重（约 1.8GB，只需一次）…")
    import urllib.request

    def _hook(blocks, bs, total):
        done = blocks * bs
        if total > 0 and done % (256 * 1024 * 1024) < bs:
            print("  下载 {:.0f}%".format(done * 100.0 / total))

    tmp = str(path) + ".part"
    urllib.request.urlretrieve(url, tmp, reporthook=_hook)
    os.replace(tmp, str(path))
    print("下载完成。")


def get_model():
    global _model
    if _model is None:
        # huggingface.co 直连不通时走国内镜像；可用环境变量 HF_ENDPOINT 覆盖
        os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
        os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
        import torch
        from laion_clap import CLAP_Module

        # 默认自动用独显（cuda:0），可用环境变量 DJ_CLAP_DEVICE 强制指定（如 cpu / cuda:1）
        device = os.environ.get("DJ_CLAP_DEVICE") or (
            "cuda:0" if torch.cuda.is_available() else "cpu"
        )
        _ensure_ckpt()
        _model = CLAP_Module(enable_fusion=False, device=device)
        _model.load_ckpt()
        gpu = torch.cuda.get_device_name(0) if device.startswith("cuda") else ""
        print(f"CLAP 运行设备: {device}" + (f"（{gpu}）" if gpu else ""))
    return _model


def _text_matrix(model):
    """每个标签的多条提示词取平均嵌入，返回 (标签列表, 归一化文本矩阵)。缓存复用。"""
    if "mood" not in _text_cache:
        tags = list(config.MOOD_VOCAB)
        embs = []
        for item in tags:
            e = model.get_text_embedding(item["prompts"])
            v = np.mean(e, axis=0)
            embs.append(v / (np.linalg.norm(v) + 1e-9))
        _text_cache["mood"] = (tags, np.stack(embs))
    return _text_cache["mood"]


def score_files(file_paths, model=None):
    """返回与 file_paths 等长的结果：{mood_tags, arousal, valence}。"""
    model = model or get_model()
    tags, text_mat = _text_matrix(model)

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
            "mood_tags": [[tags[i]["tag"], round(float(probs[i]), 3)] for i in order],
            "arousal": round(float(sum(p * t["arousal"] for p, t in zip(probs, tags))), 3),
            "valence": round(float(sum(p * t["valence"] for p, t in zip(probs, tags))), 3),
            # 顺手缓存归一化嵌入向量，供「找相似」与 kNN 使用
            "audio_emb": [round(float(x), 5) for x in a],
        })
    return results
