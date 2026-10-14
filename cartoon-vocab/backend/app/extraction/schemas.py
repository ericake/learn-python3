from typing import Literal

from pydantic import BaseModel, Field

ItemType = Literal["noun", "verb", "adj", "phrase", "other"]


class ExtractedItem(BaseModel):
    text: str = Field(description="单词原形或短语")
    type: ItemType
    meaning_zh: str = Field(description="中文释义，仅家长端显示")
    source_sentence: str = Field(description="台词中的原句，选最短最清楚的一句")
    image_prompt: str = Field(description="英文配图描述：单一主体、无文字、不出现版权角色名")
    emoji: str = Field(description="最能代表该词的一个 emoji，用于占位图")
    visualizability: int = Field(ge=1, le=5)
    reason: str = Field(description="入选理由（中文，简短）")


class ExtractionResult(BaseModel):
    selected: list[ExtractedItem]
    backups: list[ExtractedItem]
