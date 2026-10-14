"""固定的英文系统提示语音（技术文档 6.3.4）。

由 scripts/gen_system_voice.py 预生成到 media/voice/<key>.mp3；
文件不存在时前端用浏览器朗读 speak_text 兜底（仅开发用）。
"""

SYSTEM_VOICES: dict[str, str] = {
    "listen": "Listen!",
    "where_is": "Where is",
    "tap_picture": "Tap the picture!",
    "great": "Great!",
    "well_done": "Well done!",
    "you_got_it": "You got it!",
    "try_again": "Try again!",
    "lets_learn": "Let's learn some words!",
    "today_we_watch": "Today we will watch a cartoon!",
    "now_lets_watch": "Now let's watch! Listen for these words!",
    "lets_review": "Let's review!",
    "sticker": "You did it! Here's a sticker!",
    "ask_parent": "Ask Mommy or Daddy for a new show!",
}

PRAISE_KEYS = ["great", "well_done", "you_got_it"]
