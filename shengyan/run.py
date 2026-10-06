"""本地启动：python run.py，然后浏览器打开 http://127.0.0.1:8000

系统不需要登录，所以默认只监听本机。改 HOST 让局域网访问前，请确认网络里没有不该看到数据的人。
"""
import os
import socket
import sys
from pathlib import Path

if sys.version_info < (3, 10):
    sys.exit(f"需要 Python 3.10 或更高版本，当前是 {sys.version.split()[0]}。请安装新版 Python 后重试。")

# 无论从哪个目录运行，都以本文件所在目录为准（app/、static/、.env 都在这里）
ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

try:
    import uvicorn
except ImportError:
    sys.exit("缺少依赖，请先在 shengyan 目录执行：pip install -r requirements.txt")


def port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1" if host in ("0.0.0.0", "localhost") else host, port)) == 0


if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    if port_in_use(host, port):
        sys.exit(f"端口 {port} 已被占用。可能声眼已经在运行（直接打开 http://127.0.0.1:{port}），"
                 f"或换个端口：PORT=8001 python run.py（Windows：set PORT=8001 后再运行）")
    if host not in ("127.0.0.1", "localhost"):
        print(f"注意：系统没有登录，监听 {host} 后同一网络里的任何人都能访问和修改数据。")
    print(f"\n声眼正在启动，看到 “Application startup complete” 后在浏览器打开：http://127.0.0.1:{port}\n"
          "运行期间请不要关闭这个窗口；按 Ctrl+C 停止。\n")
    uvicorn.run("app.main:app", host=host, port=port)
