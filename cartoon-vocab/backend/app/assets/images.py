"""生图抽象（技术文档 6.4）。正式服务商待定，默认用内置 emoji 卡片占位。"""

import hashlib
from typing import Protocol

STYLE_SUFFIX = (
    "Children's picture-book flat illustration, bold clean outlines, bright saturated colors, "
    "single centered subject, plain pastel background, no text, no letters, no watermark."
)

_PASTELS = ["#FDE2E4", "#E2ECE9", "#DFE7FD", "#FFF1C1", "#E8DFF5", "#D7F9F1", "#FCE1C8", "#E0F4FF"]


def full_prompt(image_prompt: str) -> str:
    return f"{image_prompt.rstrip('. ')}. {STYLE_SUFFIX}"


class ImageProvider(Protocol):
    name: str
    mime: str
    ext: str

    async def generate(self, prompt: str, *, emoji: str | None = None, variant: int = 0) -> bytes: ...


class PlaceholderImageProvider:
    """生成一张纯色背景 + 大 emoji 的 SVG 卡片（无文字），用于开发与兜底。"""

    name = "placeholder"
    mime = "image/svg+xml"
    ext = "svg"

    async def generate(self, prompt: str, *, emoji: str | None = None, variant: int = 0) -> bytes:
        h = int(hashlib.sha256(f"{prompt}:{variant}".encode()).hexdigest(), 16)
        bg = _PASTELS[(h + variant) % len(_PASTELS)]
        glyph = emoji or "⭐"
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">'
            f'<rect width="512" height="512" rx="64" fill="{bg}"/>'
            f'<text x="256" y="300" font-size="260" text-anchor="middle" dominant-baseline="middle">{glyph}</text>'
            "</svg>"
        )
        return svg.encode()


def get_image_provider(name: str) -> ImageProvider:
    if name == "placeholder":
        return PlaceholderImageProvider()
    raise ValueError(f"unknown IMAGE_PROVIDER {name!r}（正式生图服务商待定）")
