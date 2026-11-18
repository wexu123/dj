@echo off
chcp 65001 >nul
cd /d %~dp0
echo [DJ 排歌工作流] 检查运行环境...

where python >nul 2>nul
if errorlevel 1 (
  echo 未找到 Python，请先安装 Python 3.10 或更高版本：https://www.python.org/downloads/
  pause
  exit /b 1
)

python -c "import flask, librosa, laion_clap, torch" >nul 2>nul
if errorlevel 1 (
  echo 首次运行：安装依赖（含 PyTorch，需要几分钟，已走国内镜像加速）...
  python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn
  if errorlevel 1 (
    echo 国内镜像安装失败，改用官方源重试...
    python -m pip install -r requirements.txt
    if errorlevel 1 (
      echo 依赖安装失败，请检查网络后重试。
      pause
      exit /b 1
    )
  )
)

echo 启动中，浏览器将自动打开 http://localhost:8765
echo （提示：首次打标时会自动下载约 1.8GB 的 AI 模型，只需一次）
echo （关闭本窗口即退出程序）
python webapp.py
pause
