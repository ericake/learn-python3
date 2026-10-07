"""首次运行时准备 .env：从 .env.example 复制，并提示填写 TikHub Token 和 DeepSeek Key。

Key 只写进本机的 .env（已被 .gitignore 忽略），不会提交到仓库。由 start.bat / start.sh 调用。
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV = ROOT / ".env"
EXAMPLE = ROOT / ".env.example"

PROMPTS = [
    ("TIKHUB_API_KEY", "TikHub Token（抓取小红书真实数据必填）"),
    ("LLM_API_KEY", "DeepSeek API Key（情感判断，留空则用本地规则）"),
]


def read_value(text: str, key: str) -> str:
    m = re.search(rf"^{key}=([^\n#]*)", text, re.M)
    return m.group(1).strip() if m else ""


def set_value(text: str, key: str, value: str) -> str:
    line = f"{key}={value}"
    if re.search(rf"^{key}=", text, re.M):
        return re.sub(rf"^{key}=.*$", lambda _: line, text, flags=re.M)
    return text.rstrip("\n") + "\n" + line + "\n"


def main() -> None:
    if not ENV.exists():
        ENV.write_text(EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
        print("已生成 .env")
    text = ENV.read_text(encoding="utf-8")
    changed = False
    if sys.stdin.isatty():
        for key, label in PROMPTS:
            if read_value(text, key):
                continue
            value = input(f"请粘贴 {label}，直接回车跳过：").strip().strip('"').strip("'")
            if value:
                text = set_value(text, key, value)
                changed = True
    if changed:
        ENV.write_text(text, encoding="utf-8")
        print("已保存到 .env")
    if not read_value(text, "TIKHUB_API_KEY"):
        print("提示：没有 TikHub Token，系统不会抓取数据。之后可以编辑 .env 填写 TIKHUB_API_KEY 再重启。")


if __name__ == "__main__":
    main()
