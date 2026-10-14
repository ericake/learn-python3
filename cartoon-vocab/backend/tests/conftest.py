import os
import sys
import tempfile
from pathlib import Path

# 必须在导入 app 之前设置：测试用独立的临时数据库和素材目录，并关闭外部服务
_tmp = tempfile.mkdtemp(prefix="cvocab-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["MEDIA_DIR"] = f"{_tmp}/media"
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["VOLC_TTS_API_KEY"] = ""
os.environ["IMAGE_PROVIDER"] = "placeholder"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

SAMPLE = Path(__file__).resolve().parent.parent / "scripts" / "samples" / "muddy_puddles_sample.txt"
