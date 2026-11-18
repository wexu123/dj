# -*- coding: utf-8 -*-
"""联网曲风纠正：元数据匹配为主，AcoustID 音频指纹兜底。

流程（对每首歌）：
  1. 识别曲目：读 ID3 标签（mutagen），否则按「艺人 - 歌名」解析文件名
  2. 联网查询：MusicBrainz（免费无需 key）+ iTunes Search（备选）
     · 配置 AcoustID key 后启用音频指纹识别（不依赖文件名，最准）
  3. 在线曲风映射回 GENRE_VOCAB 词表，与 CLAP 结果合并：
     在线高置信标签置顶并标注来源；查不到就保持 CLAP 结果
写库：genre_tags / genre_source。不影响人工确认列（genre_tags_final）。
"""
import difflib
import json
import os
import re
import time
import urllib.parse
import urllib.request
from collections import Counter

import db as dbm

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FPCALC = os.path.join(BASE, "tools", "fpcalc.exe")

MB_SEARCH = "https://musicbrainz.org/ws/2/recording/?query={}&fmt=json&limit=5"
MB_LOOKUP = "https://musicbrainz.org/ws/2/recording/{}?inc=genres+tags+releases&fmt=json"
MB_RG_LOOKUP = "https://musicbrainz.org/ws/2/release-group/{}?inc=genres+tags&fmt=json"
ITUNES_SEARCH = "https://itunes.apple.com/search?{}"

_UA = "DJSetlistWorkflow/1.0 (personal tool)"

# 在线曲风 -> GENRE_VOCAB 映射（顺序敏感：第一条命中即生效）
# 排序原则：具体/复合词在前，宽波单词在后。真实的子串陷阱：
#   "rap" ⊂ "trap"、"drill" ⊂ "drill and bass"、"pop" ⊂ "mandopop/j-pop/britpop"、
#   "blues" ⊂ "rhythm and blues"、"funk" ⊂ "funky house"、"soul" ⊂ "soulful house"、
#   "house" ⊂ "tech/melodic/minimal house"、"hardcore" ⊂ "hardcore punk/hip hop"
# 混合词（"X Y"）归属：舞曲核心（house/trap/jazz…）优先，拉丁只兜纯拉丁。
MAP_RULES = [
    ("tech house",           ["tech house", "tech-house"]),
    # rock 在 hardstyle 前（"hardcore punk"）、melodic 前（"progressive rock"）、
    # pop 前（"pop punk"/"britpop"）、folk 前（"folk rock"）
    ("rock",                 ["rock", "punk", "metal", "britpop", "grunge",
                              "shoegaze", "new wave"]),
    # trance 在 melodic 前："progressive trance" 是 trance
    ("trance",               ["trance", "psytrance", "psy trance"]),
    # melodic 在 deep house 前（"melodic house"）、techno 前（"melodic techno"）
    ("melodic/progressive",  ["melodic", "progressive", "organic house"]),
    # minimal 在 deep house 前（"minimal house"）、techno 前（"minimal techno"）
    ("minimal",              ["minimal"]),
    # deep house 兜住所有 house 变体（tech/melodic/minimal house 已被前面拦走）；
    # 必须在 r&b 前（"soulful house"）、jazz 前（"jazz house"）等之前
    ("deep house",           ["deep house", "soulful house", "afro house",
                              "future house", "bass house", "french house",
                              "filter house", "latin house", "jazz house",
                              "house"]),
    # dubstep 在 hip-hop 前（"trap" ⊃ "rap"）、latin 前（"latin trap" 是 trap）
    ("dubstep/bass",         ["dubstep", "grime", "trap", "future bass",
                              "bassline", "uk garage", "future garage",
                              "2-step garage", "speed garage"]),
    # drum & bass 在 hip-hop 前（"drill and bass" ⊃ "drill"）
    ("drum & bass",          ["drum and bass", "drum & bass", "dnb", "jungle",
                              "drill and bass", "drill'n'bass"]),
    # hip-hop 在 hardstyle 前（"hardcore hip hop"）、indie 前（"lo-fi hip hop"）
    ("hip-hop/beats",        ["hip hop", "hip-hop", "hiphop", "rap", "boom bap",
                              "drill"]),
    ("hardstyle/hard techno", ["hardstyle", "hard techno", "hardcore", "gabber",
                               "hard dance", "rawstyle"]),
    ("ambient/downtempo",    ["ambient", "downtempo", "chillout", "chill out",
                              "drone", "new age"]),
    # r&b 在 jazz 前（"rhythm and blues" ⊃ "blues"）、"soul jazz" 是 R&B
    ("r&b/soul",             ["r&b", "rnb", "r'n'b", "rhythm and blues", "soul",
                              "motown", "neo soul", "gospel"]),
    # disco/funk 在 jazz 前："jazz-funk" 是 funk
    ("disco/funk",           ["disco", "funk", "boogie"]),
    ("jazz/blues",           ["jazz", "blues", "bebop", "swing", "lounge",
                              "big band"]),
    # folk 在 indie 前（"indie folk" 是 folk）
    ("folk/acoustic",        ["folk", "acoustic", "singer-songwriter",
                              "singer songwriter", "country"]),
    ("indie/alternative",    ["indie", "alternative", "alt-rock", "alt rock",
                              "lo-fi", "lofi"]),
    # 亚洲流行在宽泛 pop 前："mandopop"/"city pop"/"k-pop" 都含 "pop"
    ("c-pop",                ["mandopop", "c-pop", "c pop", "cantopop",
                              "canto pop", "chinese pop", "mandarin pop",
                              "taiwanese pop", "hong kong pop"]),
    ("j-pop",                ["j-pop", "jpop", "japanese pop", "city pop",
                              "anime", "anisong"]),
    ("k-pop",                ["k-pop", "kpop", "korean pop"]),
    # latin 在 pop 前（"latin pop" 是拉丁）、jazz/deep house/dubstep 之后
    # （"latin jazz"/"latin house"/"latin trap" 归各自舞曲核心）
    ("latin",                ["latin", "reggaeton", "salsa", "samba", "cumbia",
                              "bachata", "merengue", "flamenco", "bossa nova"]),
    ("pop",                  ["pop"]),
    # classical 在 pop 后："chamber pop"/"baroque pop" 是 pop
    ("classical/instrumental", ["classical", "orchestral", "orchestra",
                                "baroque", "chamber music", "sonata",
                                "concerto", "symphony", "symphonic", "opera",
                                "soundtrack", "film score", "video game music",
                                "game music", "easy listening", "instrumental"]),
    ("techno",               ["techno"]),
]

_NUM_PREFIX = re.compile(r"^\s*\d{1,3}\s*[-._)]\s*")
_PAREN_SUFFIX = re.compile(r"\s*[\(\[（][^\)\]）]*[\)\]）]\s*$")


def _clean_title(title):
    """去掉歌名末尾的括号后缀（如 (Day Version)、[Radio Edit]）。"""
    return _PAREN_SUFFIX.sub("", title).strip() or title.strip()


def _http_json(url, timeout=15, retries=3):
    """GET + JSON 解析；503/429（限速）自动退避重试。"""
    import urllib.error
    for attempt in range(retries):
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < retries - 1:
                time.sleep(5 * (attempt + 1))
                continue
            raise
    raise RuntimeError("unreachable")


def identify(file_path):
    """返回 (artist, title)。ID3 优先，文件名「艺人 - 歌名」兜底。"""
    artist = title = ""
    try:
        import mutagen
        f = mutagen.File(file_path, easy=True)
        if f is not None and f.tags:
            artist = (f.tags.get("artist") or [""])[0]
            title = (f.tags.get("title") or [""])[0]
    except Exception:
        pass
    name = os.path.splitext(os.path.basename(file_path))[0]
    name = _NUM_PREFIX.sub("", name).strip()
    if not title:
        for sep in (" - ", " – ", " — ", "_-_", "｜", "|"):
            if sep in name:
                a, t = name.split(sep, 1)
                artist = artist or a.strip()
                title = t.strip()
                break
        else:
            title = name
    artist = re.split(r"[、,]", artist)[0].strip()  # 多艺人取第一个
    return artist.strip(), title.strip()


def _sim(a, b):
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


def query_musicbrainz(artist, title):
    """返回 (genre 字符串集合, 匹配分)。限速 1 次/秒。"""
    q = 'recording:"{}"'.format(title.replace('"', ""))
    if artist:
        q = 'artist:"{}" AND {}'.format(artist.replace('"', ""), q)
    data = _http_json(MB_SEARCH.format(urllib.parse.quote(q)))
    recs = data.get("recordings") or []
    if not recs:
        return set(), 0
    best = recs[0]
    if _sim(title, best.get("title") or "") < 0.6:
        return set(), 0
    if artist:
        credit = " ".join(a.get("name", "") for a in best.get("artist-credit") or [])
        if artist.lower() not in credit.lower() and _sim(artist, credit) < 0.5:
            return set(), 0  # 艺人对不上，视为错配
    time.sleep(1.1)  # MusicBrainz 限速
    detail = _http_json(MB_LOOKUP.format(best["id"]))
    names = {g["name"] for g in (detail.get("genres") or [])}
    names.update(t["name"] for t in (detail.get("tags") or [])
                 if (t.get("count") or 0) >= 1)
    # 曲目级没标签时，回退到发行组的社群曲风：
    # 跨前 3 个搜索结果收集，正式发行（无 Compilation/DJ-mix 等副类型）优先
    if not names:
        rg_ids = []

        def _collect(rec, clean_only=False):
            for r in (rec.get("releases") or []):
                rg = r.get("release-group") or {}
                rgid = rg.get("id")
                if not rgid or rgid in rg_ids:
                    continue
                if clean_only and (rg.get("secondary-types") or []):
                    continue
                rg_ids.append(rgid)

        for rec in recs[:3]:
            _collect(rec, clean_only=True)
        for rec in recs[:3]:
            _collect(rec)
        for rgid in rg_ids[:3]:
            time.sleep(1.1)
            try:
                rgd = _http_json(MB_RG_LOOKUP.format(rgid))
            except Exception:
                continue
            names |= {g["name"] for g in (rgd.get("genres") or [])}
            names.update(t["name"] for t in (rgd.get("tags") or [])
                         if (t.get("count") or 0) >= 1)
            if names:
                break
    return names, int(best.get("score") or 0)


def query_itunes(artist, title):
    """返回 genre 字符串集合（相似度不足视为无匹配）。"""
    term = urllib.parse.quote(("{} {}".format(artist, title)).strip())
    data = _http_json(ITUNES_SEARCH.format(
        "term={}&media=music&entity=song&limit=5".format(term)))
    best, best_ratio = None, 0.0
    for r in data.get("results") or []:
        ratio = _sim(title, r.get("trackName") or "")
        if artist:
            ratio = (ratio + _sim(artist, r.get("artistName") or "")) / 2
        if ratio > best_ratio:
            best, best_ratio = r, ratio
    if not best or best_ratio < 0.55:
        return set()
    names = {best.get("primaryGenreName")} - {None}
    names.update(best.get("genres") or [])
    return names


def _acoustid_key():
    key = os.environ.get("DJ_ACOUSTID_KEY", "").strip()
    if key:
        return key
    p = os.path.join(BASE, "acoustid.key")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return f.read().strip()
    return ""


def query_acoustid(file_path):
    """音频指纹识别 -> MusicBrainz 曲风。返回 (genre 集合, 状态说明)。"""
    key = _acoustid_key()
    if not key:
        return set(), "指纹识别跳过（未配置 AcoustID key）"
    if not os.path.exists(FPCALC):
        return set(), "指纹识别跳过（缺 fpcalc 组件）"
    import acoustid
    acoustid.FPCALC_COMMAND = FPCALC
    try:
        duration, fp = acoustid.fingerprint_file(file_path)
        res = acoustid.lookup(key, fp, duration, meta=["recordings"])
    except Exception as e:
        return set(), "指纹识别失败：{}".format(e)
    for item in res or []:
        if item.get("score", 0) < 0.85 or not item.get("recordings"):
            continue
        rid = item["recordings"][0].get("id")
        if not rid:
            continue
        time.sleep(1.1)
        detail = _http_json(MB_LOOKUP.format(rid))
        names = {g["name"] for g in (detail.get("genres") or [])}
        names.update(t["name"] for t in (detail.get("tags") or [])
                     if (t.get("count") or 0) >= 1)
        return names, "指纹匹配 score={:.2f}".format(item.get("score", 0))
    return set(), "指纹无匹配"


def map_to_vocab(genre_names):
    votes = Counter()
    for name in genre_names:
        low = name.lower()
        for tag, keys in MAP_RULES:
            if any(k in low for k in keys):
                votes[tag] += 1
                break
    return votes


def correct_track(row, use_fingerprint=True):
    """纠正单曲。返回 (是否纠正, 说明)。不触碰 genre_tags_final。"""
    artist, title = identify(row["file_path"])
    if not title:
        return False, "无法识别曲名，跳过"
    qtitle = _clean_title(title)
    sources, names = [], []
    notes = []
    if use_fingerprint:
        fp_names, status = query_acoustid(row["file_path"])
        if fp_names:
            sources.append("acoustid")
            names += list(fp_names)
        elif status:
            notes.append(status)

    # 文件名方向不确定（「歌名 - 艺人」/「艺人 - 歌名」），两个方向都试，
    # 靠艺人信用校验自动选对方向；能映射出词表标签即停
    candidates = [(artist, qtitle)]
    if artist and qtitle:
        candidates.append((qtitle, artist))
    for cand_artist, cand_title in candidates:
        try:
            mb_names, _score = query_musicbrainz(cand_artist, cand_title)
            if mb_names:
                sources.append("musicbrainz")
                names += list(mb_names)
        except Exception as e:
            notes.append("MusicBrainz 失败：{}".format(e))
        try:
            it_names = query_itunes(cand_artist, cand_title)
            if it_names:
                sources.append("itunes")
                names += list(it_names)
        except Exception as e:
            notes.append("iTunes 失败：{}".format(e))
        if map_to_vocab(names):
            break

    votes = map_to_vocab(names)
    if not votes:
        return False, "无在线匹配" + ("；" + "；".join(notes) if notes else "")

    sources = sorted(set(sources))
    top_tag, top_n = votes.most_common(1)[0]
    conf = 0.55 + 0.15 * min(top_n - 1, 2)
    if not artist:
        conf = min(conf, 0.62)   # 仅凭歌名匹配，置信度封顶
    if "acoustid" in sources:
        conf = min(conf + 0.05, 0.95)
    old = [[t, p] for t, p in (row.get("genre_tags") or []) if t != top_tag]
    row["genre_tags"] = [[top_tag, round(conf, 2)]] + old[:2]
    row["genre_source"] = "online:" + "+".join(sources)
    return True, "→ {}（{}）".format(top_tag, row["genre_source"])


def correct_all(conn, rows=None, use_fingerprint=True, log=print):
    rows = rows if rows is not None else dbm.fetch_all(conn)
    ok = miss = 0
    for i, r in enumerate(rows, 1):
        name = r.get("title") or os.path.splitext(
            os.path.basename(r["file_path"]))[0]
        changed, msg = correct_track(r, use_fingerprint=use_fingerprint)
        if changed:
            dbm.upsert(conn, r)
            ok += 1
        else:
            miss += 1
        log("[{}/{}] {} {}".format(i, len(rows), name, msg))
    return ok, miss
