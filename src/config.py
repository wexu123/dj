# -*- coding: utf-8 -*-
"""全局配置：听感词表、Camelot 映射、排歌参数。"""

# 听感受控词表（第一版 7 个标签）
# prompts 留给阶段二 CLAP 零样本打分使用；坐标为唤醒度 x 效价（与实现计划图 2 一致）
MOOD_VOCAB = [
    {"tag": "热情/燃",   "arousal":  0.85, "valence":  0.60,
     "prompts": ["passionate energetic driving track", "热情 燃 高能量"]},
    {"tag": "欢快",      "arousal":  0.42, "valence":  0.78,
     "prompts": ["happy upbeat cheerful", "欢快 阳光"]},
    {"tag": "律动 groove", "arousal": 0.18, "valence":  0.42,
     "prompts": ["groovy rhythmic bouncy track", "律动 groove 有弹性"]},
    {"tag": "舒缓/梦幻", "arousal": -0.60, "valence":  0.35,
     "prompts": ["soft dreamy mellow", "舒缓 梦幻 柔和"]},
    {"tag": "空灵/氛围", "arousal": -0.86, "valence":  0.08,
     "prompts": ["ambient ethereal spacious", "空灵 氛围"]},
    {"tag": "emo/低沉",  "arousal": -0.52, "valence": -0.62,
     "prompts": ["melancholic emo dark sad", "emo 低沉 忧郁"]},
    {"tag": "紧张/暗黑", "arousal":  0.72, "valence": -0.48,
     "prompts": ["tense dark driving", "紧张 暗黑"]},
]

# 曲风受控词表（23 个标签：12 个电子大类 + 11 个日常曲风）
GENRE_VOCAB = [
    # —— DJ 电子大类 ——
    {"tag": "techno",              "prompts": ["a techno track", "dark driving techno"]},
    {"tag": "tech house",          "prompts": ["a tech house track", "tech house groove"]},
    {"tag": "deep house",          "prompts": ["a deep house track", "deep house smooth bassline"]},
    {"tag": "melodic/progressive", "prompts": ["a melodic house track", "progressive house melodic"]},
    {"tag": "trance",              "prompts": ["a trance track", "uplifting trance"]},
    {"tag": "drum & bass",         "prompts": ["a drum and bass track", "fast breakbeat drum and bass"]},
    {"tag": "dubstep/bass",        "prompts": ["a dubstep track", "heavy bass music"]},
    {"tag": "disco/funk",          "prompts": ["a disco track", "funk groove boogie"]},
    {"tag": "minimal",             "prompts": ["a minimal techno track", "minimal repetitive groove"]},
    {"tag": "ambient/downtempo",   "prompts": ["an ambient track", "downtempo chillout"]},
    {"tag": "hip-hop/beats",       "prompts": ["a hip hop beat", "boom bap instrumental beat"]},
    {"tag": "hardstyle/hard techno", "prompts": ["a hardstyle track", "hard techno pounding kick"]},
    # —— 日常曲风 ——
    {"tag": "pop",                 "prompts": ["a pop song with vocals", "catchy mainstream pop"]},
    {"tag": "c-pop",               "prompts": ["a mandopop song", "chinese pop song with vocals"]},
    {"tag": "j-pop",               "prompts": ["a j-pop song", "japanese anime pop song"]},
    {"tag": "k-pop",               "prompts": ["a k-pop song", "korean pop dance song"]},
    {"tag": "rock",                "prompts": ["a rock song", "electric guitar rock band"]},
    {"tag": "indie/alternative",   "prompts": ["an indie alternative song", "indie rock band"]},
    {"tag": "folk/acoustic",       "prompts": ["a folk song", "acoustic guitar singer songwriter"]},
    {"tag": "r&b/soul",            "prompts": ["an r&b soul song", "smooth rnb groove vocals"]},
    {"tag": "jazz/blues",          "prompts": ["a jazz track with saxophone", "blues guitar shuffle"]},
    {"tag": "latin",               "prompts": ["a latin pop song", "reggaeton latin rhythm"]},
    {"tag": "classical/instrumental", "prompts": ["a classical piece", "piano orchestral instrumental"]},
]

# Camelot 轮盘：调性名 -> 编号（相对大小调共享数字）
# 含等音别名（KS 算法输出升号拼写，如 A# 实际为 Bb）
CAMELOT = {
    "C major": "8B",  "G major": "9B",  "D major": "10B", "A major": "11B",
    "E major": "12B", "B major": "1B",  "F# major": "2B", "Db major": "3B",
    "Ab major": "4B", "Eb major": "5B", "Bb major": "6B", "F major": "7B",
    "A minor": "8A",  "E minor": "9A",  "B minor": "10A", "F# minor": "11A",
    "C# minor": "12A", "G# minor": "1A", "D# minor": "2A", "Bb minor": "3A",
    "F minor": "4A",  "C minor": "5A",  "G minor": "6A",  "D minor": "7A",
    # 等音别名
    "C# major": "3B", "G# major": "4B", "A# major": "6B", "D# major": "5B",
    "A# minor": "3A",
}

# 排歌参数（初始值，可调）
BPM_TOLERANCE = 0.06   # 硬约束：BPM ±6%（自动识别 half/double 变体）

# 演出段落 -> 能量区间（软约束，允许 ±1.5 缓冲）：(起, 止, 低, 高, 名称)
ENERGY_BANDS = [
    (0.00, 0.33, 3,  5,  "暖场"),
    (0.33, 0.66, 5,  7,  "爬升"),
    (0.66, 0.90, 8,  10, "peak"),
    (0.90, 1.01, 4,  6,  "收尾"),
]
BAND_BUFFER = 1.5    # 能量区间软缓冲

# 过渡情绪带动判定阈值
ENERGY_DELTA_PUSH = 1.5   # 相邻两首能量差超过 +1.5 视为「推向高潮」
ENERGY_DELTA_DROP = -1.5  # 低于 -1.5 视为「落地收束」

AUDIO_EXTS = (".wav", ".flac", ".ogg", ".mp3", ".aiff", ".aif")

# 阶段三结构分析参数
BEATS_PER_BLOCK = 32   # 1 个分析块 = 8 小节（4/4）
BARS_BEFORE_BREAK = 8  # break 切点取 breakdown 前 8 小节
