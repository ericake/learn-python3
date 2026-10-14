"""用 Claude 从候选中精选重点词和短语（技术文档 6.2）。"""

import json

import anthropic

from ..config import settings
from .candidates import Candidate
from .schemas import ExtractedItem, ExtractionResult

# 固定不变的系统提示，便于缓存
SYSTEM_PROMPT = """You are an early-childhood English teacher preparing a "listen and pick the picture" lesson
(Rosetta Stone style) for a 6-year-old Chinese child who cannot read. The child watches one English cartoon
episode per day; before and after watching, they hear a word and tap the matching picture.

Choose the key words and phrases from the episode transcript. Rules:
1. Every item must be clearly drawable as ONE simple picture: concrete nouns, visible actions,
   perceivable adjectives (colours, sizes, wet/dirty, feelings), or a simple scene for phrases.
2. Prefer items that appear in the transcript several times or matter for understanding the plot.
3. Exclude function words, abstract words, character names, and words the child has already mastered.
4. Use the base form for words (jumping -> jump). Phrases are 2-4 words of everyday spoken English.
5. source_sentence MUST be copied verbatim from the transcript: the shortest clear sentence containing the item.
6. image_prompt: English, describe a single centered subject on a plain background, children's flat
   illustration style, no text or letters. Never name copyrighted characters; say "a cute cartoon pig" instead.
7. meaning_zh and reason are written in Simplified Chinese; reason is short (e.g. "出现 6 次，剧情核心").
8. emoji: the single emoji that best represents the item.
Return exactly the requested number of selected items (fewer only if the transcript truly lacks drawable
items), plus 5-8 backup items ranked by quality."""


def _user_prompt(show: str, sentences: list[str], words: list[Candidate], phrases: list[Candidate],
                 mastered: list[str], n: int) -> str:
    cand = {
        "word_candidates": [{"text": c.text, "count": c.freq} for c in words[:30]],
        "phrase_candidates": [{"text": c.text, "count": c.freq} for c in phrases[:10]],
    }
    return (
        f"Cartoon: {show}\n"
        f"Select {n} items in total: about {n - min(3, max(2, n // 4))} words and "
        f"{min(3, max(2, n // 4))} phrases.\n"
        f"Already mastered (exclude): {', '.join(mastered) or 'none'}\n"
        f"Rule-based candidates (hints, you may pick others from the transcript):\n"
        f"{json.dumps(cand, ensure_ascii=False)}\n\n"
        "<transcript>\n" + "\n".join(sentences) + "\n</transcript>"
    )


class ExtractionRefused(RuntimeError):
    pass


async def llm_extract(show: str, sentences: list[str], words: list[Candidate], phrases: list[Candidate],
                      mastered: list[str], n: int) -> ExtractionResult:
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    resp = await client.messages.parse(
        model=settings.llm_model,
        max_tokens=16000,
        output_config={"effort": "medium"},
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _user_prompt(show, sentences, words, phrases, mastered, n)}],
        output_format=ExtractionResult,
    )
    if resp.stop_reason == "refusal" or resp.parsed_output is None:
        raise ExtractionRefused(str(resp.stop_reason))
    return resp.parsed_output


async def llm_complete_item(show: str, sentences: list[str], text: str) -> ExtractedItem:
    """家长手动新增条目时，补全其余字段。"""
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    resp = await client.messages.parse(
        model=settings.llm_model,
        max_tokens=4000,
        output_config={"effort": "low"},
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": f"Cartoon: {show}\nThe parent added the item \"{text}\". Fill in all fields for exactly "
                       f"this item (keep text as given).\n<transcript>\n" + "\n".join(sentences) + "\n</transcript>",
        }],
        output_format=ExtractedItem,
    )
    if resp.stop_reason == "refusal" or resp.parsed_output is None:
        raise ExtractionRefused(str(resp.stop_reason))
    return resp.parsed_output
