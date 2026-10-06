"""本地启动：python run.py，然后浏览器打开 http://localhost:8000

系统不需要登录，所以默认只监听本机。改 HOST 让局域网访问前，请确认网络里没有不该看到数据的人。
"""
import os

import uvicorn

if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    if host not in ("127.0.0.1", "localhost"):
        print(f"注意：系统没有登录，监听 {host} 后同一网络里的任何人都能访问和修改数据。")
    uvicorn.run("app.main:app", host=host, port=int(os.getenv("PORT", "8000")))
