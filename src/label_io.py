# -*- coding: utf-8 -*-
"""人工校正工具：导出自动标签为 CSV，人工改完后回写入库。

流程：
  1. export_csv  导出 id/属性/自动标签，final 列预填 top-1 供快速确认或修改
  2. 用 Excel/记事本改 genre_final / mood_final（多个标签用分号分隔，留空=不改动）
  3. import_csv  回写 genre_tags_final / mood_tags_final
"""
import csv
import os

import config
import db as dbm

HEADER = ["id", "title", "bpm", "camelot", "energy",
          "genre_auto", "mood_auto", "genre_final", "mood_final"]


def _fmt(tags):
    return "; ".join("{} {:.2f}".format(t, p) for t, p in (tags or []))


def _top1(tags):
    return tags[0][0] if tags else ""


def export_csv(db_path, csv_path):
    conn = dbm.connect(db_path)
    rows = dbm.fetch_all(conn)
    conn.close()
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        for r in rows:
            title = os.path.splitext(os.path.basename(r["file_path"]))[0]
            # 已确认过的带出原值，未确认的预填自动 top-1，减少输入
            genre_final = _top1(r.get("genre_tags_final")) or _top1(r.get("genre_tags"))
            mood_final = _top1(r.get("mood_tags_final")) or _top1(r.get("mood_tags"))
            w.writerow([
                r["id"], title, r.get("bpm") or "", r.get("camelot") or "",
                round(r["energy"], 1) if r.get("energy") else "",
                _fmt(r.get("genre_tags")), _fmt(r.get("mood_tags")),
                genre_final, mood_final,
            ])
    return len(rows)


def import_csv(db_path, csv_path):
    conn = dbm.connect(db_path)
    known = {t["tag"] for t in config.MOOD_VOCAB} | {t["tag"] for t in config.GENRE_VOCAB}
    ok, skip, warn = 0, 0, 0
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            r = dbm.fetch_one(conn, row["id"])
            if not r:
                print("  跳过未知 id: {}".format(row["id"]))
                skip += 1
                continue
            changed = False
            for col, key in (("genre_tags_final", "genre_final"),
                             ("mood_tags_final", "mood_final")):
                raw = (row.get(key) or "").strip()
                if not raw:
                    continue  # 留空 = 保持库内现状
                tags = [t.strip() for t in raw.replace("；", ";").split(";") if t.strip()]
                unknown = [t for t in tags if t not in known]
                if unknown:
                    print("  [{}] 词表外标签（仍写入）: {}".format(
                        row["id"], ", ".join(unknown)))
                    warn += 1
                r[col] = [[t, 1.0] for t in tags]
                changed = True
            if changed:
                dbm.upsert(conn, r)
                ok += 1
            else:
                skip += 1
    conn.close()
    return ok, skip, warn
