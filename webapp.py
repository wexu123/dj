# -*- coding: utf-8 -*-
"""DJ 排歌工作流 · 本地 Web 界面。

运行：python webapp.py  然后浏览器打开 http://localhost:8765
可选参数：--port 端口  --db 数据库路径
"""
import argparse
import os
import sys
import threading
import webbrowser

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE, "src"))

from flask import Flask, jsonify, request, send_from_directory

import audio_features
import classifier
import config
import db as dbm
import genre_clap
import mood_clap
import online_genre
import setlist as sl

app = Flask(__name__, static_folder="static", static_url_path="")

DB_PATH = os.path.join(BASE, "library.db")

STATUS = {"running": False, "step": "空闲", "done": 0, "total": 0, "log": []}


def _log(msg):
    STATUS["log"].append(str(msg))
    STATUS["log"] = STATUS["log"][-300:]


def _set(step, done=None, total=None):
    STATUS["step"] = step
    if done is not None:
        STATUS["done"] = done
    if total is not None:
        STATUS["total"] = total


def _find_audio(dir_path):
    files = []
    for root, _dirs, names in os.walk(dir_path):
        for n in sorted(names):
            if n.lower().endswith(config.AUDIO_EXTS):
                files.append(os.path.join(root, n))
    return files


def _pipeline(dir_path):
    """一键处理：扫描 -> 曲风 -> 听感 -> 智能补标。后台线程执行。"""
    try:
        STATUS.update(running=True, log=[], done=0, total=0)
        conn = dbm.connect(DB_PATH)

        files = _find_audio(dir_path)
        if not files:
            _log("目录中未发现音频文件：" + dir_path)
            return
        _log("发现 {} 个音频文件".format(len(files)))
        total = len(files) * 3
        STATUS["total"] = total

        # 1/3 属性提取
        for i, path in enumerate(files, 1):
            _set("属性提取（1/3）· {}/{}".format(i, len(files)), i)
            try:
                feat = audio_features.extract(path)
            except Exception as e:
                _log("提取失败 {}: {}".format(os.path.basename(path), e))
                continue
            rec = {"id": "trk_{:04d}".format(i), "file_path": path,
                   "title": os.path.splitext(os.path.basename(path))[0]}
            rec.update(feat)
            dbm.upsert(conn, rec)

        # 2/3 曲风 + 3/3 听感（共用一个模型）
        _set("加载 AI 模型…（首次较慢）")
        model = mood_clap.get_model()
        rows = dbm.fetch_all(conn)
        for j, r in enumerate(rows):
            _set("曲风打标（2/3）· {}/{}".format(j + 1, len(rows)),
                 len(files) + j)
            try:
                r.update(genre_clap.score_files([r["file_path"]], model=model)[0])
                dbm.upsert(conn, r)
            except Exception as e:
                _log("曲风打分失败 {}: {}".format(r["id"], e))
        for j, r in enumerate(rows):
            _set("听感打标（3/3）· {}/{}".format(j + 1, len(rows)),
                 len(files) * 2 + j)
            try:
                r.update(mood_clap.score_files([r["file_path"]], model=model)[0])
                dbm.upsert(conn, r)
            except Exception as e:
                _log("听感打分失败 {}: {}".format(r["id"], e))

        # 智能补标（有校正数据时生效）
        _set("智能补标…")
        try:
            info = classifier.predict(conn, model=model)
            _log(info["message"])
        except Exception as e:
            _log("智能补标跳过：{}".format(e))

        conn.close()
        _set("完成", total, total)
        _log("处理完成，共 {} 首。".format(len(files)))
    except Exception as e:
        _log("出错：{}".format(e))
    finally:
        STATUS["running"] = False


def _predict_only():
    try:
        STATUS.update(running=True, log=[])
        _set("智能补标…")
        conn = dbm.connect(DB_PATH)
        info = classifier.predict(conn)
        conn.close()
        _log(info["message"])
        _set("完成")
    except Exception as e:
        _log("出错：{}".format(e))
    finally:
        STATUS["running"] = False


def _genre_online():
    try:
        STATUS.update(running=True, log=[])
        conn = dbm.connect(DB_PATH)
        rows = dbm.fetch_all(conn)
        total = len(rows)
        STATUS["total"] = total
        ok = miss = 0
        for i, r in enumerate(rows, 1):
            _set("联网查证 · {}/{}".format(i, total), i)
            name = r.get("title") or os.path.splitext(
                os.path.basename(r["file_path"]))[0]
            changed, msg = online_genre.correct_track(r)
            if changed:
                dbm.upsert(conn, r)
                ok += 1
            else:
                miss += 1
            _log("[{}/{}] {} {}".format(i, total, name, msg))
        conn.close()
        _log("联网纠正完成：已纠正 {} · 无匹配 {}".format(ok, miss))
        _set("完成", total, total)
    except Exception as e:
        _log("出错：{}".format(e))
    finally:
        STATUS["running"] = False


def _tags_text(tags):
    return "; ".join(t for t, _p in (tags or []))


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/status")
def api_status():
    return jsonify(STATUS)


@app.route("/api/tracks")
def api_tracks():
    conn = dbm.connect(DB_PATH)
    rows = dbm.fetch_all(conn)
    conn.close()
    out = []
    for r in rows:
        out.append({
            "id": r["id"],
            "title": r.get("title") or os.path.splitext(
                os.path.basename(r["file_path"]))[0],
            "bpm": r.get("bpm"),
            "camelot": r.get("camelot"),
            "energy": r.get("energy"),
            "duration": r.get("duration"),
            "genre_tags": r.get("genre_tags"),
            "genre_source": r.get("genre_source"),
            "mood_tags": r.get("mood_tags"),
            "genre_final": _tags_text(r.get("genre_tags_final")),
            "mood_final": _tags_text(r.get("mood_tags_final")),
            "arousal": r.get("arousal"),
            "valence": r.get("valence"),
        })
    return jsonify(out)


@app.route("/api/pipeline", methods=["POST"])
def api_pipeline():
    if STATUS["running"]:
        return jsonify({"ok": False, "msg": "已有任务在运行"}), 409
    dir_path = (request.json or {}).get("dir", "").strip()
    if not dir_path or not os.path.isdir(dir_path):
        return jsonify({"ok": False, "msg": "目录不存在：" + dir_path}), 400
    threading.Thread(target=_pipeline, args=(dir_path,), daemon=True).start()
    return jsonify({"ok": True})


@app.route("/api/predict", methods=["POST"])
def api_predict():
    if STATUS["running"]:
        return jsonify({"ok": False, "msg": "已有任务在运行"}), 409
    threading.Thread(target=_predict_only, daemon=True).start()
    return jsonify({"ok": True})


def _train_clf():
    try:
        STATUS.update(running=True, log=[])
        _set("训练分类器…")
        import trainer
        conn = dbm.connect(DB_PATH)
        for _kind, rep in trainer.train(conn).items():
            _log(rep["message"])
        conn.close()
        _set("完成")
    except Exception as e:
        _log("出错：{}".format(e))
    finally:
        STATUS["running"] = False


@app.route("/api/train", methods=["POST"])
def api_train():
    if STATUS["running"]:
        return jsonify({"ok": False, "msg": "已有任务在运行"}), 409
    threading.Thread(target=_train_clf, daemon=True).start()
    return jsonify({"ok": True})


@app.route("/api/genre-online", methods=["POST"])
def api_genre_online():
    if STATUS["running"]:
        return jsonify({"ok": False, "msg": "已有任务在运行"}), 409
    threading.Thread(target=_genre_online, daemon=True).start()
    return jsonify({"ok": True})


@app.route("/api/settings", methods=["GET", "POST"])
def api_settings():
    key_path = os.path.join(BASE, "acoustid.key")
    if request.method == "POST":
        key = (request.json or {}).get("acoustid_key", "").strip()
        with open(key_path, "w", encoding="utf-8") as f:
            f.write(key)
        return jsonify({"ok": True})
    key = ""
    if os.path.exists(key_path):
        with open(key_path, encoding="utf-8") as f:
            key = f.read().strip()
    return jsonify({"acoustid_key": key})


@app.route("/api/export-labels")
def api_export_labels():
    import csv
    import io

    import label_io
    conn = dbm.connect(DB_PATH)
    rows = dbm.fetch_all(conn)
    conn.close()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(label_io.HEADER)
    for r in rows:
        title = os.path.splitext(os.path.basename(r["file_path"]))[0]
        genre_final = label_io._top1(r.get("genre_tags_final")) or \
            label_io._top1(r.get("genre_tags"))
        mood_final = label_io._top1(r.get("mood_tags_final")) or \
            label_io._top1(r.get("mood_tags"))
        w.writerow([
            r["id"], title, r.get("bpm") or "", r.get("camelot") or "",
            round(r["energy"], 1) if r.get("energy") else "",
            label_io._fmt(r.get("genre_tags")), label_io._fmt(r.get("mood_tags")),
            genre_final, mood_final,
        ])
    data = buf.getvalue().encode("utf-8-sig")  # BOM 让 Excel 正确识别中文
    return app.response_class(
        data, mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=labels_export.csv"})


@app.route("/api/similar")
def api_similar():
    import similarity
    tid = (request.args.get("id") or "").strip()
    n = int(request.args.get("n") or similarity.DEFAULT_N)
    conn = dbm.connect(DB_PATH)
    out = similarity.similar_tracks(conn, tid, n)
    conn.close()
    if out is None:
        return jsonify({"ok": False, "msg": "曲目不存在"}), 404
    target, results = out

    def _item(r, score, reasons, cos):
        return {
            "id": r["id"],
            "title": r.get("title") or os.path.splitext(
                os.path.basename(r["file_path"]))[0],
            "bpm": r.get("bpm"),
            "camelot": r.get("camelot"),
            "energy": r.get("energy"),
            "genre_tags": r.get("genre_tags"),
            "mood_tags": r.get("mood_tags"),
            "score": round(score, 3),
            "cos": round(cos, 3),
            "reasons": reasons,
        }

    return jsonify({
        "ok": True,
        "target": {"id": target["id"], "title": target.get("title") or
                   os.path.splitext(os.path.basename(target["file_path"]))[0]},
        "items": [_item(r, s, rs, c) for r, s, rs, c in results],
    })


@app.route("/api/modules", methods=["GET", "POST"])
def api_modules():
    conn = dbm.connect(DB_PATH)
    if request.method == "POST":
        name = ((request.json or {}).get("name") or "").strip() or "未命名模块"
        mid = dbm.create_module(conn, name)
        conn.close()
        return jsonify({"ok": True, "id": mid})
    mods = dbm.list_modules(conn)
    conn.close()
    return jsonify(mods)


@app.route("/api/modules/<mid>", methods=["DELETE"])
def api_module_delete(mid):
    conn = dbm.connect(DB_PATH)
    dbm.delete_module(conn, mid)
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/modules/<mid>/tracks/<tid>", methods=["POST", "DELETE"])
def api_module_tracks(mid, tid):
    conn = dbm.connect(DB_PATH)
    if request.method == "POST":
        dbm.module_add_track(conn, mid, tid)
    else:
        dbm.module_remove_track(conn, mid, tid)
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/modules/<mid>/export.csv")
def api_module_export(mid):
    import csv
    import io

    conn = dbm.connect(DB_PATH)
    mods = {m["id"]: m for m in dbm.list_modules(conn)}
    mod = mods.get(mid)
    if not mod:
        conn.close()
        return jsonify({"ok": False, "msg": "模块不存在"}), 404
    rows = {r["id"]: r for r in dbm.fetch_all(conn)}
    conn.close()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["序号", "id", "标题", "BPM", "调", "能量", "曲风", "听感"])
    for i, tid in enumerate(mod["track_ids"], 1):
        r = rows.get(tid)
        if not r:
            continue
        title = os.path.splitext(os.path.basename(r["file_path"]))[0]
        w.writerow([
            i, tid, title,
            round(r["bpm"]) if r.get("bpm") else "",
            r.get("camelot") or "",
            round(r["energy"], 1) if r.get("energy") is not None else "",
            "; ".join(t for t, _ in (r.get("genre_tags") or [])),
            "; ".join(t for t, _ in (r.get("mood_tags") or [])),
        ])
    data = buf.getvalue().encode("utf-8-sig")
    return app.response_class(
        data, mimetype="text/csv",
        headers={"Content-Disposition":
                 "attachment; filename=module_{}.csv".format(mid)})


@app.route("/api/labels", methods=["POST"])
def api_labels():
    data = request.json or {}
    if not data.get("id"):
        return jsonify({"ok": False, "msg": "缺少 id"}), 400
    conn = dbm.connect(DB_PATH)
    r = dbm.fetch_one(conn, data["id"])
    if not r:
        conn.close()
        return jsonify({"ok": False, "msg": "曲目不存在"}), 404
    for col, key in (("genre_tags_final", "genre_final"),
                     ("mood_tags_final", "mood_final")):
        if key in data:
            raw = (data.get(key) or "").strip()
            tags = [t.strip() for t in raw.replace("；", ";").split(";") if t.strip()]
            r[col] = [[t, 1.0] for t in tags] if tags else None
    dbm.upsert(conn, r)
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/setlist", methods=["POST"])
def api_setlist():
    data = request.json or {}
    conn = dbm.connect(DB_PATH)
    rows = dbm.fetch_all(conn)
    conn.close()
    for r in rows:
        r["title"] = r.get("title") or os.path.splitext(
            os.path.basename(r["file_path"]))[0]
    entries, warnings = sl.generate(
        rows,
        start_id=(data.get("start_id") or "").strip() or None,
        minutes=float(data.get("minutes") or 60),
    )
    out = [{
        "id": e["track"]["id"],
        "title": e["track"].get("title"),
        "bpm": e["track"].get("bpm"),
        "camelot": e["track"].get("camelot"),
        "energy": e["track"].get("energy"),
        "stage": e["stage"],
        "hint": e["hint"],
    } for e in entries]
    return jsonify({"entries": out, "warnings": warnings})


def main():
    global DB_PATH
    ap = argparse.ArgumentParser(description="DJ 排歌工作流 · Web 界面")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--db", default=DB_PATH)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()
    DB_PATH = args.db

    url = "http://localhost:{}".format(args.port)
    print("DJ 排歌工作流已启动：" + url)
    print("（关闭本窗口即退出）")
    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    app.run(host="127.0.0.1", port=args.port, threaded=True)


if __name__ == "__main__":
    main()
