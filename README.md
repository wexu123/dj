# DJ 排歌工作流

给 DJ 曲库自动打标（曲风 / 听感）→ 人工校正 → 生成演出 setlist 的本地 Web 工具。

解决「歌很多但没时间分类」的问题：把排歌前的准备工作自动化，你只需要确认标签和挑歌。

## 功能

- **属性提取**：BPM、调性（Camelot 编号）、能量、结构分段与混音切点
- **曲风打标**：23 类受控词表（12 个电子大类 + 11 个日常曲风），CLAP 零样本
- **听感打标**：7 类主观感受（热情/燃、emo/低沉、律动 groove…），映射到唤醒度 × 效价二维坐标
- **联网曲风纠正**：MusicBrainz / iTunes / AcoustID 指纹，用权威数据修正 AI 的判断
- **个性化补标**：人工校正几首后，kNN 分类器自动给其余歌归类，越用越准
- **找相似**：按听感、调性、BPM、能量找可替换的曲目
- **歌曲模块**：把常一起放的歌攒成模块，方便复用
- **生成 setlist**：按 Camelot 调性兼容、BPM ±6%、能量曲线（暖场 → 爬升 → peak → 收尾）排歌，每个过渡附情绪带动提示
- **导出**：标签 CSV（Excel 可编辑回写）/ setlist CSV / 模块 CSV

## 环境要求

- Python 3.10 或更高版本（安装时勾选 `Add to PATH`）
- Windows（`run.bat` 与 `tools/fpcalc.exe` 为 Windows 版；其他系统可手动启动）
- GPU 可选，有则打标快很多

## 快速开始

双击 `run.bat`。首次运行会自动装依赖，然后打开 http://localhost:8765 。

手动启动：

```bash
pip install -r requirements.txt
python webapp.py                 # 默认 8765 端口，自动开浏览器
python webapp.py --port 9000     # 换端口
python webapp.py --db D:\lib.db  # 指定数据库文件
python webapp.py --no-browser    # 不自动开浏览器
```

### 首次运行的两件慢事

1. **装依赖**：含 PyTorch，体积较大。`run.bat` 已配置清华镜像加速，失败会自动回退官方源。
2. **下载 AI 模型**：首次打标时自动下载约 1.8 GB 的 CLAP 模型，只需一次。走国内镜像 hf-mirror.com，可用环境变量 `DJ_CLAP_CKPT_URL` 换源。

## 使用流程

1. 填音乐目录（递归扫描 `.wav .flac .ogg .mp3 .aiff`）
2. 点「一键处理」：扫描 → 属性提取 → 曲风/听感打标 → 智能补标
3. 在表格里校正标签（留空表示采用自动结果）
4. 可选：点「联网曲风纠正」，用权威数据修正曲风
5. 设定时长与起始段落，点「生成 setlist」
6. 导出标签 CSV 或 setlist CSV

## 目录结构

```
webapp.py              Flask 入口，16 个 API 路由
run.bat                Windows 一键启动（含依赖安装）
requirements.txt       依赖清单
src/
  config.py            曲风/听感词表、Camelot 映射、排歌参数
  db.py                SQLite 读写
  audio_features.py    BPM / 调性 / 能量 / 结构切点
  genre_clap.py        曲风 CLAP 零样本
  mood_clap.py         听感 CLAP 零样本 + 模型下载
  online_genre.py      联网曲风查询与映射规则
  classifier.py        预测入口（训练模型优先，kNN 兜底）
  trainer.py           训练与 kNN 补标
  similarity.py        找相似
  setlist.py           排歌算法
  label_io.py          CSV 导入导出
  cli.py               命令行入口
static/index.html      前端单页（原生 JS，无构建）
tools/fpcalc.exe       AcoustID 指纹工具
tests/map_check.py     曲风映射单测（65 个用例）
```

## 可自定义的地方

- **曲风词表**：`src/config.py` 的 `GENRE_VOCAB`，加条目即可扩展识别范围（记得同步 `src/online_genre.py` 的 `MAP_RULES`）
- **排歌参数**：`src/config.py` 的 `ENERGY_BANDS`（能量区间）、`BPM_TOLERANCE`（默认 ±6%）
- **听感标签**：`src/config.py` 的 `MOOD_VOCAB`，含二维情绪坐标

改完映射规则记得跑单测：

```bash
python tests/map_check.py
```

## 隐私

数据不出本机。只有「联网曲风纠正」会把歌名/艺人发给 MusicBrainz 和 iTunes；音频文件本身不上传（AcoustID 可选，会上传音频指纹）。

`library.db`（曲库数据库，含本机文件路径）已加入 `.gitignore`，不会进仓库。

## 已知限制

- 曲风受控在 23 类，映射不进去的作者信息会被放弃，不会乱标
- 能量、切点都是算法估计，最终仍需人耳确认
- 联网查询依赖外网，国内可能需要代理
