# -*- coding: utf-8 -*-
"""阶段一 / 阶段三：属性与结构提取（librosa 后端）。

产出：bpm / bpm_conf / key / camelot / energy / structure / cue_points
后续阶段二接入 Essentia + Discogs-EffNet / CLAP 时，只需在此扩展提取器。
"""
import numpy as np
import librosa

import config

PITCH_CLASSES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Krumhansl-Schmuckler 调性轮廓
_MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09,
                           2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53,
                           2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


def detect_key(y, sr):
    """Krumhansl-Schmuckler 相关匹配，返回 (调性名, camelot, 置信度)。"""
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr).mean(axis=1)
    best_name, best_corr = "", -2.0
    for mode, profile in (("major", _MAJOR_PROFILE), ("minor", _MINOR_PROFILE)):
        for root in range(12):
            rolled = np.roll(chroma, -root)
            corr = float(np.corrcoef(rolled, profile)[0, 1])
            if corr > best_corr:
                best_corr = corr
                best_name = "{} {}".format(PITCH_CLASSES[root], mode)
    camelot = config.CAMELOT.get(best_name)
    conf = max(0.0, best_corr) if np.isfinite(best_corr) else 0.0
    return best_name, camelot, round(conf, 3)


def _block_energies(y, sr, beats, rms, frame_times):
    """按 8 小节（BEATS_PER_BLOCK 拍）块聚合能量。"""
    if len(beats) < config.BEATS_PER_BLOCK + 1:
        return [], []
    edges = []
    for i in range(0, len(beats) - config.BEATS_PER_BLOCK, config.BEATS_PER_BLOCK):
        edges.append((beats[i], beats[i + config.BEATS_PER_BLOCK]))
    energies = []
    for (t0, t1) in edges:
        mask = (frame_times >= t0) & (frame_times < t1)
        energies.append(float(rms[mask].mean()) if mask.any() else 0.0)
    return edges, energies


def _segments_from_labels(edges, labels):
    """合并同标签连续块 -> 段落，按位置命名 intro/build/drop/breakdown/outro。"""
    if not edges:
        return []
    first_high = next((i for i, l in enumerate(labels) if l == "high"), None)
    last_high = None
    if first_high is not None:
        last_high = len(labels) - 1 - next(
            i for i, l in enumerate(reversed(labels)) if l == "high")

    def name(i, label):
        if label == "high":
            return "drop"
        before = first_high is None or i < first_high
        after = last_high is None or i > last_high
        if label == "low":
            return "intro" if before else ("outro" if after else "breakdown")
        return "build" if before else ("outro" if after else "breakdown")

    sections = []
    cur_name = name(0, labels[0])
    cur_start = edges[0][0]
    for i in range(1, len(labels)):
        n = name(i, labels[i])
        if n != cur_name:
            sections.append({"section": cur_name,
                             "start": round(cur_start, 1),
                             "end": round(edges[i][0], 1)})
            cur_name, cur_start = n, edges[i][0]
    sections.append({"section": cur_name,
                     "start": round(cur_start, 1),
                     "end": round(edges[-1][1], 1)})
    return sections


def _cue_points(sections, duration, bpm):
    cue = [{"type": "mix_in", "time": 0.0}]
    outro = next((s for s in reversed(sections) if s["section"] == "outro"), None)
    if outro:
        cue.append({"type": "mix_out", "time": outro["start"]})
    else:
        cue.append({"type": "mix_out", "time": round(duration * 0.85, 1)})
    brk = next((s for s in sections if s["section"] == "breakdown"), None)
    if brk and bpm > 0:
        t = brk["start"] - config.BARS_BEFORE_BREAK * 4 * 60.0 / bpm
        if t > 0:
            cue.append({"type": "break", "time": round(t, 1)})
    return cue


def extract(file_path):
    """提取单曲全部属性，返回可直接写库的 dict。"""
    y, sr = librosa.load(file_path, sr=22050, mono=True)
    duration = float(len(y) / sr)

    # --- 阶段一：BPM / 调性 / 能量 ---
    tempo, beats = librosa.beat.beat_track(y=y, sr=sr, units="time")
    bpm = float(np.atleast_1d(tempo)[0])
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    bpm_conf = round(float(np.clip(onset_env.std() / (onset_env.mean() + 1e-9), 0, 1)), 3)
    key_name, camelot, key_conf = detect_key(y, sr)
    rms = librosa.feature.rms(y=y)[0]
    energy = float(np.clip(rms.mean() * 20.0, 0, 10))

    # --- 阶段三：段落结构与切点 ---
    frame_times = librosa.times_like(rms, sr=sr, hop_length=512)
    edges, block_e = _block_energies(y, sr, np.asarray(beats, dtype=float), rms, frame_times)
    if block_e:
        lo, hi = np.percentile(block_e, [33, 67])
        labels = ["low" if e < lo else ("high" if e > hi else "mid") for e in block_e]
        structure = _segments_from_labels(edges, labels)
    else:
        structure = [{"section": "intro", "start": 0.0, "end": round(duration, 1)}]
    cue_points = _cue_points(structure, duration, bpm)

    return {
        "duration": round(duration, 2),
        "bpm": round(bpm, 2),
        "bpm_conf": bpm_conf,
        "key": key_name,
        "camelot": camelot,
        "energy": round(energy, 1),
        "key_conf": key_conf,
        "structure": structure,
        "cue_points": cue_points,
    }
