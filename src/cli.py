# -*- coding: utf-8 -*-
"""命令行入口。

用法：
  python src/cli.py init-db <db>
  python src/cli.py scan <db> <音频目录>
  python src/cli.py show <db>
  python src/cli.py setlist <db> [--minutes 60] [--start id]
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import audio_features
import config
import db as dbm
import setlist as sl


def cmd_init_db(args):
    conn = dbm.connect(args.db)
    conn.close()
    print("数据库已初始化：{}".format(args.db))


def cmd_scan(args):
    conn = dbm.connect(args.db)
    files = []
    for root, _dirs, names in os.walk(args.dir):
        for n in sorted(names):
            if n.lower().endswith(config.AUDIO_EXTS):
                files.append(os.path.join(root, n))
    if not files:
        print("目录中未发现音频文件：{}".format(args.dir))
        return
    print("发现 {} 个音频文件，开始提取…".format(len(files)))
    ok, fail = 0, 0
    for i, path in enumerate(files, 1):
        tid = "trk_{:04d}".format(i)
        try:
            feat = audio_features.extract(path)
        except Exception as e:  # 单曲失败不中断整库
            print("  [{}] 提取失败 {}: {}".format(i, os.path.basename(path), e))
            fail += 1
            continue
        rec = {"id": tid, "file_path": path,
               "title": os.path.splitext(os.path.basename(path))[0]}
        rec.update(feat)
        dbm.upsert(conn, rec)
        ok += 1
        print("  [{}/{}] {:28s} {:>5.0f} BPM  {:>4s}  能量 {:>4.1f}".format(
            i, len(files), rec["title"][:28], feat["bpm"],
            feat["camelot"] or "?", feat["energy"]))
    print("完成：成功 {} · 失败 {}".format(ok, fail))
    conn.close()


def cmd_show(args):
    conn = dbm.connect(args.db)
    rows = dbm.fetch_all(conn)
    if not rows:
        print("曲库为空，请先运行 scan。")
        return
    print("{:10s} {:28s} {:>6s} {:>5s} {:>6s}".format(
        "id", "title", "bpm", "key", "energy"))
    for r in rows:
        title = os.path.splitext(os.path.basename(r["file_path"]))[0]
        print("{:10s} {:28s} {:>6.0f} {:>5s} {:>6.1f}".format(
            r["id"], title[:28], r.get("bpm") or 0,
            r.get("camelot") or "?", r.get("energy") or 0))
    conn.close()


def cmd_genre(args):
    import genre_clap
    conn = dbm.connect(args.db)
    rows = dbm.fetch_all(conn)
    if not rows:
        print("曲库为空，请先运行 scan。")
        return
    print("加载 CLAP 模型，为 {} 首歌零样本打曲风标签…".format(len(rows)))
    model = genre_clap.get_model()
    ok, fail = 0, 0
    for r in rows:
        try:
            res = genre_clap.score_files([r["file_path"]], model=model)[0]
        except Exception as e:
            print("  打分失败 {}: {}".format(r["id"], e))
            fail += 1
            continue
        r.update(res)
        dbm.upsert(conn, r)
        ok += 1
        top = ", ".join("{} {:.2f}".format(t, p) for t, p in res["genre_tags"])
        print("  {}  {}".format(r["id"], top))
    print("完成：成功 {} · 失败 {}".format(ok, fail))
    conn.close()


def cmd_mood(args):
    import mood_clap
    conn = dbm.connect(args.db)
    rows = dbm.fetch_all(conn)
    if not rows:
        print("曲库为空，请先运行 scan。")
        return
    print("加载 CLAP 模型，为 {} 首歌零样本打听感标签…".format(len(rows)))
    model = mood_clap.get_model()
    ok, fail = 0, 0
    for r in rows:
        try:
            res = mood_clap.score_files([r["file_path"]], model=model)[0]
        except Exception as e:
            print("  打分失败 {}: {}".format(r["id"], e))
            fail += 1
            continue
        r.update(res)
        dbm.upsert(conn, r)
        ok += 1
        top = ", ".join("{} {:.2f}".format(t, p) for t, p in res["mood_tags"])
        print("  {}  {}  (唤醒 {:+.2f} / 效价 {:+.2f})".format(
            r["id"], top, res["arousal"], res["valence"]))
    print("完成：成功 {} · 失败 {}".format(ok, fail))
    conn.close()


def cmd_genre_online(args):
    import online_genre
    conn = dbm.connect(args.db)
    rows = dbm.fetch_all(conn)
    if not rows:
        print("曲库为空，请先运行 scan。")
        return
    fp = "启用" if online_genre._acoustid_key() else "未配置（可写入 acoustid.key）"
    print("联网曲风纠正（MusicBrainz + iTunes，AcoustID 指纹：{}）…".format(fp))
    ok, miss = online_genre.correct_all(conn, rows)
    print("完成：已纠正 {} · 无匹配 {}".format(ok, miss))
    conn.close()


def cmd_train(args):
    import trainer
    conn = dbm.connect(args.db)
    print("训练分类器（冻结 CLAP 嵌入 + 小分类头，数据 = 人工校正标签）…")
    for kind, rep in trainer.train(conn).items():
        print("  " + rep["message"])
    conn.close()


def cmd_predict(args):
    import classifier
    conn = dbm.connect(args.db)
    print("智能补标（kNN，基于人工校正标签）…")
    info = classifier.predict(conn)
    print(info["message"])
    conn.close()


def cmd_export_labels(args):
    import label_io
    n = label_io.export_csv(args.db, args.csv)
    print("已导出 {} 首 -> {}".format(n, args.csv))
    print("改 genre_final / mood_final 两列（分号分隔多个标签，留空=不改动），")
    print("改完运行: python src/cli.py import-labels {} {}".format(args.db, args.csv))


def cmd_import_labels(args):
    import label_io
    ok, skip, warn = label_io.import_csv(args.db, args.csv)
    print("完成：已更新 {} · 未改动 {} · 词表外警告 {}".format(ok, skip, warn))


def cmd_setlist(args):
    conn = dbm.connect(args.db)
    rows = dbm.fetch_all(conn)
    for r in rows:
        r["title"] = os.path.splitext(os.path.basename(r["file_path"]))[0]
    entries, warnings = sl.generate(rows, start_id=args.start, minutes=args.minutes)
    if not entries:
        print("未能生成 setlist：" + "；".join(warnings))
        return
    print(sl.format_setlist(entries, warnings))
    conn.close()


def main():
    p = argparse.ArgumentParser(description="DJ 排歌工作流工具")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init-db", help="初始化曲库数据库")
    s.add_argument("db")
    s.set_defaults(func=cmd_init_db)

    s = sub.add_parser("scan", help="扫描目录并提取属性/结构/切点")
    s.add_argument("db")
    s.add_argument("dir")
    s.set_defaults(func=cmd_scan)

    s = sub.add_parser("show", help="查看曲库")
    s.add_argument("db")
    s.set_defaults(func=cmd_show)

    s = sub.add_parser("genre", help="CLAP 零样本曲风标签（阶段一）")
    s.add_argument("db")
    s.set_defaults(func=cmd_genre)

    s = sub.add_parser("mood", help="CLAP 零样本听感标签（阶段二）")
    s.add_argument("db")
    s.set_defaults(func=cmd_mood)

    s = sub.add_parser("genre-online", help="联网曲风纠正（元数据 + AcoustID 指纹）")
    s.add_argument("db")
    s.set_defaults(func=cmd_genre_online)

    s = sub.add_parser("train", help="用人工校正标签训练分类器（路线 A）")
    s.add_argument("db")
    s.set_defaults(func=cmd_train)

    s = sub.add_parser("predict", help="智能补标（训练模型优先，kNN 兜底）")
    s.add_argument("db")
    s.set_defaults(func=cmd_predict)

    s = sub.add_parser("export-labels", help="导出标签 CSV 供人工校正")
    s.add_argument("db")
    s.add_argument("csv")
    s.set_defaults(func=cmd_export_labels)

    s = sub.add_parser("import-labels", help="把人工校正结果回写入库")
    s.add_argument("db")
    s.add_argument("csv")
    s.set_defaults(func=cmd_import_labels)

    s = sub.add_parser("setlist", help="生成 setlist")
    s.add_argument("db")
    s.add_argument("--minutes", type=float, default=60.0)
    s.add_argument("--start", default=None, help="起始曲 id")
    s.set_defaults(func=cmd_setlist)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
