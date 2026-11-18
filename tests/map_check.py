# -*- coding: utf-8 -*-
"""MAP_RULES 映射单测：验证子串陷阱与规则顺序。

改动 src/online_genre.py 的 MAP_RULES 后跑一下，确认顺序没被破坏：
    python tests/map_check.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))
from online_genre import map_to_vocab  # noqa: E402

CASES = [
    # (在线曲风字符串, 期望标签) —— 子串陷阱都是真实存在的
    ("Tech House", "tech house"),
    ("techno", "techno"),
    ("melodic techno", "melodic/progressive"),
    ("hard techno", "hardstyle/hard techno"),
    ("minimal techno", "minimal"),
    ("minimal house", "minimal"),
    ("deep house", "deep house"),
    ("soulful house", "deep house"),
    ("afro house", "deep house"),
    ("house", "deep house"),
    ("funky house", "deep house"),
    ("latin house", "deep house"),
    ("progressive house", "melodic/progressive"),
    ("progressive trance", "trance"),
    ("progressive rock", "rock"),
    ("hardcore punk", "rock"),
    ("hardcore hip hop", "hip-hop/beats"),
    ("hardcore", "hardstyle/hard techno"),
    ("trap", "dubstep/bass"),
    ("latin trap", "dubstep/bass"),
    ("rap", "hip-hop/beats"),
    ("boom bap", "hip-hop/beats"),
    ("drill and bass", "drum & bass"),
    ("jungle", "drum & bass"),
    ("pop punk", "rock"),
    ("britpop", "rock"),
    ("j-pop", "j-pop"),
    ("J-Pop", "j-pop"),
    ("anime", "j-pop"),
    ("city pop", "j-pop"),
    ("mandopop", "c-pop"),
    ("cantopop", "c-pop"),
    ("chinese pop", "c-pop"),
    ("k-pop", "k-pop"),
    ("kpop", "k-pop"),
    ("synthpop", "pop"),
    ("indie pop", "indie/alternative"),
    ("indie rock", "rock"),
    ("indie folk", "folk/acoustic"),
    ("chamber pop", "pop"),
    ("baroque pop", "pop"),
    ("latin pop", "latin"),
    ("latin jazz", "jazz/blues"),
    ("reggaeton", "latin"),
    ("rhythm and blues", "r&b/soul"),
    ("neo soul", "r&b/soul"),
    ("soul jazz", "r&b/soul"),
    ("blues", "jazz/blues"),
    ("blues rock", "rock"),
    ("jazz", "jazz/blues"),
    ("jazz-funk", "disco/funk"),
    ("funk", "disco/funk"),
    ("disco", "disco/funk"),
    ("folk", "folk/acoustic"),
    ("folk rock", "rock"),
    ("singer-songwriter", "folk/acoustic"),
    ("country", "folk/acoustic"),
    ("alternative", "indie/alternative"),
    ("lo-fi hip hop", "hip-hop/beats"),
    ("classical", "classical/instrumental"),
    ("soundtrack", "classical/instrumental"),
    ("piano sonata", "classical/instrumental"),
    ("symphonic metal", "rock"),
    ("ambient", "ambient/downtempo"),
    ("new age", "ambient/downtempo"),
]


def main():
    fail = 0
    for raw, want in CASES:
        votes = map_to_vocab({raw})
        got = votes.most_common(1)[0][0] if votes else None
        ok = got == want
        if not ok:
            fail += 1
        print("{:<24} -> {:<24} {}{}".format(
            raw, got or "(无)", "OK" if ok else "FAIL",
            "" if ok else "  期望 " + want))
    print("\n{} 个用例，失败 {}".format(len(CASES), fail))
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
