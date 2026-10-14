"""本地文件存储（MVP）。接口与对象存储一致，后续可替换为 S3 兼容实现。"""

from pathlib import Path

from ..config import settings


class LocalStorage:
    def __init__(self, root: Path | None = None, base_url: str | None = None):
        self.root = Path(root or settings.media_dir)
        self.base_url = (base_url or settings.media_base_url).rstrip("/")

    def put(self, key: str, data: bytes) -> str:
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    def url(self, key: str) -> str:
        return f"{self.base_url}/{key}"


storage = LocalStorage()
