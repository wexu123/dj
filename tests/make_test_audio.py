# -*- coding: utf-8 -*-
"""合成测试音频：生成若干风格可控的 WAV，用于端到端验证打标与排歌逻辑。

每首：噪声 kick 打拍（不污染调性）+ 三和弦持续音（确定调性）+ 目标 RMS 归一化。
"""
import os
import sys

import numpy as np
import soundfile as sf

SR = 22050
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "testdata")

# (文件名, BPM, 根音 MIDI, 是否小三和弦, 目标能量, 时长秒)
TRACKS = [
    ("t1_warmup_am.wav",  122, 57, True,  3.0, 120),   # A minor  = 8A
    ("t2_build_em.wav",   124, 52, True,  4.8, 120),   # E minor  = 9A
    ("t3_build_g.wav",    124, 55, False, 6.5, 120),   # G major  = 9B
    ("t4_peak_d.wav",     126, 50, False, 8.5, 120),   # D major  = 10B
    ("t5_peak_a.wav",     126, 57, False, 9.0, 120),   # A major  = 11B
    ("t6_close_e.wav",    124, 52, False, 4.5, 120),   # E major  = 12B
    ("t7_odd_db.wav",     132, 49, False, 6.0, 120),   # Db major = 3B（应被排歌规则过滤）
]


def midi_to_freq(m):
    return 440.0 * 2 ** ((m - 69) / 12.0)


def synth(bpm, root_midi, minor, energy, dur_s):
    n = int(SR * dur_s)
    t = np.arange(n) / SR
    y = np.zeros(n)

    # 噪声 kick：每个 1/4 拍一次，指数衰减
    beat = 60.0 / bpm
    rng = np.random.default_rng(42)
    for k in range(int(dur_s / beat)):
        i0 = int(k * beat * SR)
        seg = rng.standard_normal(int(0.08 * SR)) * np.exp(-np.linspace(0, 12, int(0.08 * SR)))
        y[i0:i0 + len(seg)] += seg * 0.9

    # 和弦：根音 + 三音 + 五音 + 高八度根音
    third = root_midi + (3 if minor else 4)
    for m in (root_midi, third, root_midi + 7, root_midi + 12):
        y += 0.25 * np.sin(2 * np.pi * midi_to_freq(m) * t)

    # 每 16 小节做一次能量包络起伏，制造段落结构
    env = 0.75 + 0.25 * np.sin(2 * np.pi * t / (16 * 4 * beat))
    y *= env

    # 归一化到目标 RMS（能量 = RMS * 20，见 audio_features.extract）
    target_rms = energy / 20.0
    y *= target_rms / (np.sqrt(np.mean(y ** 2)) + 1e-9)
    return y.astype(np.float32)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    for fname, bpm, root, minor, energy, dur in TRACKS:
        y = synth(bpm, root, minor, energy, dur)
        path = os.path.join(OUT_DIR, fname)
        sf.write(path, y, SR)
        print("生成 {}（{} BPM，能量 {}）".format(fname, bpm, energy))
    print("输出目录：{}".format(OUT_DIR))


if __name__ == "__main__":
    main()
