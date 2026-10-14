# 动画词卡 MVP 技术设计文档（v1）

| 项目 | 内容 |
| --- | --- |
| 对应 PRD | [`docs/prd/cartoon-vocab-mvp-prd.md`](../prd/cartoon-vocab-mvp-prd.md)（v0.2） |
| 文档版本 | v1.0（第一版） |
| 更新日期 | 2026-10-12 |
| 范围 | MVP：家长端内容准备 + 孩子端预习/复习 + 间隔复习 + 简版报告；首发 *Peppa Pig* S1E1 *Muddy Puddles* |

---

## 1. 设计目标与约束

| 目标 / 约束 | 来源 | 技术含义 |
| --- | --- | --- |
| 网页应用，平板浏览器横屏优先 | PRD 决策 #5 | 前端 SPA + PWA（Service Worker 离线缓存、可添加到主屏幕） |
| 孩子端零文字、全英文语音 | PRD 决策 #1 | 所有提示语音提前生成好，存成静态资源；点按到出声 ≤ 200ms，音频必须预加载 |
| 单集准备 ≤ 3 分钟，素材生成 ≤ 60s | PRD 2.1 / F4 | 提取和生成走异步任务队列，并发调用 TTS 和生图；前端轮询进度 |
| 每集默认 10 个条目 | PRD 决策 #3 | 一集约需生成 10 张图 + 30 段音频（单词正常/慢速 + 原句） |
| 生成成本暂不设上限 | PRD 决策 #6 | 不做限额，但**每次外部调用都记账**（`cost_ledger`） |
| 儿童隐私 | PRD 第 8 节 | 不采集孩子的个人信息；第三方密钥只放在服务端 |
| 首发单家庭单孩子 | PRD 2.2 | 数据模型保留 `child_id`，但不做多孩子切换界面 |

---

## 2. 总体架构

```
┌──────────────────────── 浏览器（iPad Safari / Chrome）────────────────────────┐
│  React SPA (PWA)                                                             │
│   ├─ 孩子端：首页 / 预习 / 复习 / 小复习 / 贴纸册                             │
│   ├─ 家长端：剧集 / 台词输入 / 词表审核 / 报告（家长锁）                      │
│   ├─ Lesson Player（题目状态机 + 音频引擎）                                   │
│   └─ Service Worker：缓存应用外壳 + 课程包（JSON / mp3 / webp）               │
└───────────────▲──────────────────────────────────────────────▲──────────────┘
                │ HTTPS JSON API                                │ CDN 拉取素材
┌───────────────┴───────────────┐                    ┌──────────┴───────────┐
│  API 服务 (FastAPI)            │                    │ 对象存储 + CDN        │
│  鉴权 / 剧集 / 审核 / 课程 /   │                    │ audio/*.mp3          │
│  作答记录 / 报告 / 调度         │                    │ image/*.webp         │
└───────┬───────────────┬───────┘                    └──────────▲───────────┘
        │ SQL           │ 入队                                   │ 上传
┌───────▼──────┐  ┌─────▼──────┐   ┌──────────────────────────┐  │
│ PostgreSQL   │  │ Redis      │◄──┤ Worker (arq)             ├──┘
│              │  │ (队列/锁)  │   │ 清洗 → NLP → LLM 提取     │
└──────────────┘  └────────────┘   │ → 生图 / TTS → 后处理     │
                                   │ → 课程编排                │
                                   └──┬──────────┬─────────┬──┘
                                      │          │         │
                              Claude API   字节 TTS    生图服务（待定）
                             （词表提取）  seed-audio
```

### 2.1 技术选型

| 层 | 选型 | 理由 |
| --- | --- | --- |
| 前端框架 | React 18 + TypeScript + Vite | 生态成熟；Vite 打包快 |
| PWA | `vite-plugin-pwa`（Workbox） | 生成 Service Worker，支持预缓存和运行时缓存 |
| 动效 | Framer Motion + Lottie（`lottie-web`） | 弹跳、晃动、庆祝动画 |
| 音频 | Howler.js（底层用 Web Audio） | 解决 iOS 自动播放解锁、预加载、多音轨并发 |
| 前端状态 | Zustand + TanStack Query | 轻量；接口缓存和轮询 |
| 后端 | Python 3.12 + FastAPI + Pydantic v2 | 异步 IO 适合大量外部调用；Pydantic 同时用于接口校验和 LLM 结构化输出 |
| ORM / 迁移 | SQLAlchemy 2.0（async）+ Alembic | — |
| 数据库 | PostgreSQL 16（本地开发可用 SQLite） | — |
| 任务队列 | arq（Redis） | 原生 asyncio，与 FastAPI 同栈 |
| 对象存储 | S3 兼容（本地 MinIO；线上任选 S3 兼容服务）+ CDN | 素材静态化，前端直接拉取 |
| NLP | spaCy `en_core_web_sm` + `wordfreq` | 分词、词性、词形还原、词频 |
| 音频后处理 | ffmpeg（`silenceremove`、`loudnorm`） | 去首尾静音、统一响度 |
| LLM | Anthropic Claude API，模型 `claude-opus-5-5`，Python SDK `anthropic` | 结构化输出（Pydantic）稳定，可直接得到校验后的对象 |
| TTS | 字节跳动 `seed-audio-1.0`（`/api/v3/tts/create`） | 已指定；支持用自然语言描述音色和语气 |
| 生图 | **待定**，通过 `ImageProvider` 接口抽象 | 见 6.4 |
| 部署 | Docker Compose（api / worker / postgres / redis / minio） | MVP 单机即可 |

---

## 3. 模块划分

| 模块 | 职责 | 对应 PRD |
| --- | --- | --- |
| `auth` | 家长账号注册/登录（邮箱 + 密码），JWT 放 httpOnly Cookie；孩子档案只存昵称和头像 | 第 3 节 |
| `episodes` | 剧集增删改查、状态机 | F1 |
| `transcript` | 台词清洗、分句、说话人识别、校验 | F2 |
| `extraction` | 候选词打分 + LLM 精选 + 家长审核 | F3 |
| `assets` | 生图、TTS、后处理、上传、全局词条复用 | F4 |
| `lessons` | 课程编排：题目序列、干扰项、选项位置随机 | F7 / F8 / F10 |
| `progress` | 作答记录、掌握状态、间隔复习调度 | F9 |
| `reports` | 家长报告聚合 | F5 |
| `billing` | 外部调用成本记账（不设上限，只记录） | PRD 决策 #6 |

---

## 4. 数据模型

> 在 PRD 第 7 节基础上细化。主键统一用 UUID，时间统一存 UTC。

```sql
-- 账号
parent(id, email UNIQUE, password_hash, created_at)
child(id, parent_id FK, nickname, avatar, accent_pref DEFAULT 'en-GB', created_at)

-- 剧集
episode(
  id, child_id FK, show_name, season, episode_no, title,
  transcript_raw TEXT, transcript_clean JSONB,      -- [{idx, speaker, text}]
  status TEXT,                                      -- 见 4.1
  planned_date DATE, target_item_count INT DEFAULT 10,
  error TEXT NULL, created_at, updated_at
)

-- 全局词条（跨剧集复用图片/音频）
vocab_item(
  id, text, lemma, type,                            -- noun/verb/adj/phrase/other
  accent,                                           -- en-GB / en-US
  default_image_id FK NULL,
  audio_normal_id FK NULL, audio_slow_id FK NULL,
  UNIQUE(lemma, type, accent)
)

-- 候选词（审核前后都在这张表，用 selected 区分）
episode_item(
  id, episode_id FK, vocab_item_id FK,
  source_sentence TEXT, sentence_audio_id FK NULL,
  meaning_zh TEXT, image_prompt TEXT, image_id FK NULL,
  visualizability SMALLINT, reason TEXT, score REAL,
  selected BOOL, is_backup BOOL, sort_order INT
)

-- 素材
asset(
  id, kind,                                         -- audio / image
  storage_key, mime, bytes, duration_ms NULL,
  provider, provider_request_id NULL,
  prompt TEXT, params JSONB, content_hash,          -- content_hash 用于去重
  status,                                           -- pending / ready / failed / rejected
  created_at
)

-- 学习
session(id, child_id, episode_id NULL, mode, started_at, finished_at NULL)  -- mode: preview/review/spaced
attempt(
  id, session_id FK, vocab_item_id FK, question_type,   -- Q1..Q5
  option_ids JSONB, chosen_id, is_correct, is_first_try,
  latency_ms, created_at
)
mastery(
  child_id, vocab_item_id, status,                  -- new/learning/mastered
  correct_streak, wrong_count, last_seen_at, next_due_at,
  PRIMARY KEY(child_id, vocab_item_id)
)
sticker_award(id, child_id, session_id, sticker_key, created_at)

-- 任务与成本
job(id, episode_id, type, status, progress JSONB, attempts, error, created_at, updated_at)
cost_ledger(id, episode_id NULL, provider, operation, units, unit, est_cost NULL, request_id, created_at)
```

### 4.1 剧集状态机

```
draft ──提交台词──► extracting ──成功──► reviewing ──家长确认──► generating ──成功──► ready
  ▲                    │                    │                       │
  └──────────── failed ◄┴────────────────────┴──── 失败（可重试） ────┘
ready ──孩子开始学习──► in_use（仅用于展示：已预习 / 已复习按 session 统计）
```

---

## 5. 后端接口（REST，前缀 `/api/v1`）

### 5.1 家长端

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/auth/register`、`/auth/login`、`/auth/logout` | 账号 |
| GET/PUT | `/child` | 孩子档案（昵称、头像、口音） |
| GET | `/episodes?status=` | 剧集列表 |
| POST | `/episodes` | 新建剧集 `{show_name, season?, episode_no?, title?, planned_date?}` |
| PUT | `/episodes/{id}/transcript` | 提交台词 `{text}` 或上传 `multipart(file)`（P1：srt/vtt）→ 清洗 + 校验，然后入队 `extract` |
| GET | `/episodes/{id}` | 详情 + 状态 + 任务进度 |
| GET | `/episodes/{id}/items` | 候选与备选条目 |
| PATCH | `/episodes/{id}/items/{item_id}` | 勾选/取消、改原句/释义/配图描述 |
| POST | `/episodes/{id}/items` | 手动新增 `{text}`（后端调 LLM 补全其余字段） |
| POST | `/episodes/{id}/confirm` | 确认词表 → 入队 `generate_assets` |
| POST | `/episodes/{id}/items/{item_id}/regenerate-image` | 换一张图（每条最多 3 次） |
| POST | `/episodes/{id}/items/{item_id}/image` | 上传自定义图片 |
| GET | `/reports/summary`、`/reports/episodes/{id}` | 报告 |

### 5.2 孩子端

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/home` | 今日剧集、两个按钮的完成状态、是否有到期的小复习 |
| GET | `/lessons/{episode_id}?mode=preview\|review` | 返回**课程包**（见 5.3）；mode=review 时自动混入到期旧词，并按是否做过预习决定是否加入认识卡 |
| GET | `/lessons/spaced` | 小复习课程包（只有 Q3） |
| POST | `/sessions` | 开始一节 `{episode_id?, mode}` |
| POST | `/sessions/{id}/attempts` | 批量上报作答（离线时先缓存，联网后补传；用 `client_attempt_id` 保证幂等） |
| POST | `/sessions/{id}/finish` | 结束一节 → 发贴纸、更新掌握状态 |

### 5.3 课程包格式

整节课一次性下发，前端拿到后可以完全离线播放，题目顺序也由服务端事先定好。

```json
{
  "lesson_id": "les_...",
  "episode_id": "ep_...",
  "mode": "preview",
  "accent": "en-GB",
  "theme": { "color": "#F7A1C4", "sticker_key": "pig_boots" },
  "assets": {
    "img_puddle": { "url": "https://cdn/.../puddle.webp" },
    "aud_puddle_n": { "url": "https://cdn/.../puddle_normal.mp3", "duration_ms": 820 },
    "aud_puddle_s": { "url": "https://cdn/.../puddle_slow.mp3",   "duration_ms": 1300 },
    "sys_where_is": { "url": "https://cdn/static/voice/where_is.mp3" }
  },
  "steps": [
    { "type": "intro",  "voice": ["sys_today_we_watch"] },
    { "type": "Q1", "item": "puddle", "image": "img_puddle", "audio": ["aud_puddle_n", "aud_puddle_s"] },
    { "type": "Q2", "item": "puddle", "prompt": ["sys_where_is", "aud_puddle_n"],
      "options": ["img_puddle", "img_boots"], "answer": "img_puddle" },
    { "type": "Q3", "item": "jump", "prompt": ["aud_jump_n"],
      "options": ["img_boots", "img_jump", "img_rain", "img_puddle"], "answer": "img_jump" },
    { "type": "outro", "voice": ["sys_now_lets_watch"], "sticker": true }
  ]
}
```

---

## 6. 内容生成流水线

```
PUT transcript
   │
   ▼  [同步] 清洗 / 分句 / 校验（< 1s）
job: extract  ─────────────────────────────────────────── 目标 ≤ 20s
   1. spaCy 分词、词性、词形还原
   2. 候选：名词/动词/形容词的 lemma + 2~4 词的 n-gram 语块
   3. 规则打分：频次 × 可视化先验 × 难度适配 − 已掌握惩罚（见 6.1）
   4. 取前 40 个候选 + 清洗后台词交给 Claude，输出 10 个正选 + 5~10 个备选（见 6.2）
   5. 写入 episode_item → 状态改为 reviewing
   │
家长审核 → POST confirm
   │
   ▼
job: generate_assets ──────────────────────────────────── 目标 ≤ 60s
   对每个选中条目（并发）：
     a. 全局词条命中且素材齐全 → 直接复用
     b. 否则：生图 ×1、TTS 单词正常 ×1、慢速 ×1
     c. TTS 原句 ×1（每集独有，不复用）
     d. 后处理：去静音、响度统一、转 webp / mp3 → 上传对象存储
     e. 质检（时长、格式）失败 → 重试 ≤ 2 次 → 仍失败则把该条标为 failed，家长端提示
   全部完成 → 状态改为 ready
```

### 6.1 候选打分（规则层）

```
score = w1·log(1+freq_in_transcript)
      + w2·visual_prior(pos, wordnet_concreteness)
      + w3·difficulty_fit(zipf_freq)          # wordfreq 的 Zipf 值落在 4.0~6.0 加分
      + w4·plot_weight                        # 出现在标题/首尾段落的加权
      − w5·mastered(child, lemma)
排除：停用词、专有名词（PROPN，可配置保留角色名）、长度 ≤ 2 的词
```

规则层只负责缩小范围、给出排序依据，最终选哪些词由 LLM 决定，便于后续调权重。

### 6.2 LLM 提取（Claude API）

- 模型：`claude-opus-5-5`；`output_config.effort = "medium"`（结构化提取任务，先从 medium 开始，用首发剧集测试后再调）。
- 输出：用 SDK 的 `client.messages.parse(..., output_format=ExtractionResult)` 直接得到校验好的 Pydantic 对象，不需要自己解析 JSON。
- 拒答兜底：开启服务端自动回退（`betas=["server-side-fallback-2026-07-01"]`，`fallbacks="default"`）；每次都先检查 `stop_reason`，是 `refusal` 时把任务标为失败，提示家长重试。
- 提示词：沿用 PRD 6.2 的要点，系统提示保持固定不变（利于缓存），把台词放在用户消息里。

```python
# backend/app/extraction/llm.py（示意）
from typing import Literal
from pydantic import BaseModel, Field
import anthropic

class Item(BaseModel):
    text: str
    type: Literal["noun", "verb", "adj", "phrase", "other"]
    meaning_zh: str
    source_sentence: str
    image_prompt: str
    visualizability: int = Field(ge=1, le=5)
    reason: str

class ExtractionResult(BaseModel):
    selected: list[Item]
    backups: list[Item]

client = anthropic.AsyncAnthropic()  # 从环境变量 ANTHROPIC_API_KEY 读取密钥

async def extract(transcript: str, candidates: list[str], mastered: list[str], n: int = 10) -> ExtractionResult:
    resp = await client.messages.parse(
        model="claude-opus-5-5",
        max_tokens=16000,
        output_config={"effort": "medium"},
        system=SYSTEM_PROMPT,  # 固定文本：儿童英语老师角色 + 选词规则
        messages=[{"role": "user", "content": build_user_prompt(transcript, candidates, mastered, n)}],
        output_format=ExtractionResult,
    )
    if resp.stop_reason == "refusal":
        raise ExtractionRefused()
    return resp.parsed_output
```

> 上面开启的服务端回退参数要求改用 `client.beta.messages.*` 调用，具体写法在实现时以 SDK 文档为准。

**校验（LLM 输出之后）**：
- `source_sentence` 必须能在清洗后的台词里找到（忽略大小写和标点后匹配），找不到就换成包含该词的最短原句；
- `text` 的词形还原结果必须在台词中出现过（家长手动添加的除外）；
- 去重；`visualizability < 3` 的条目自动挪到备选。

### 6.3 TTS：字节跳动 seed-audio

#### 6.3.1 接口

```
POST https://openspeech.bytedance.com/api/v3/tts/create
Headers:
  Content-Type: application/json
  X-Api-Key: ${VOLC_TTS_API_KEY}        # 只放服务端环境变量，禁止写进代码仓库和前端
Body:
{
  "model": "seed-audio-1.0",
  "text_prompt": "<用自然语言描述音色、语气、环境，再用引号写出要说的台词>",
  "audio_config": {
    "format": "mp3",
    "sample_rate": 48000,
    "pitch_rate": 0,
    "speech_rate": 0,
    "loudness_rate": 0
  },
  "watermark": {}
}
超时：客户端 300s（与示例 curl 的 --max-time 一致）
```

> ⚠️ **响应格式待确认**：示例只给了请求，没有给响应；从当前开发环境也访问不到这个域名（代理返回 403），无法实测。客户端按以下几种可能做兼容，第一次联调时确认后删掉多余分支：
> 1. 直接返回音频二进制（`Content-Type: audio/mpeg`）；
> 2. 返回 JSON，音频是 base64 字段（如 `data` / `audio`）；
> 3. 返回 JSON，里面是音频下载 URL；
> 4. 异步任务：返回任务 ID，需要轮询查询接口。
>
> 另外还需要确认：`speech_rate` / `pitch_rate` / `loudness_rate` 的取值范围和含义、并发 / QPS 限制、错误码、计费单位、`watermark` 的作用（是否会往音频里加可听见的水印）。

#### 6.3.2 用法设计

seed-audio 是“提示词驱动”的生成式音频模型（示例里还包含音效和配乐），所以要**严格约束提示词**，保证输出的是干净的人声：

| 用途 | `text_prompt` 模板 | `speech_rate` |
| --- | --- | --- |
| 单词·正常速 | `A warm, cheerful young {accent_desc} female voice, speaking clearly to a six-year-old child. Studio quality, no background music, no sound effects, no other speakers. She says: "{word}."` | 0 |
| 单词·慢速 | 同上，并把 `speaking clearly` 换成 `speaking slowly and very clearly, stretching each syllable gently` | 待确认取值后设为负值（约 0.75 倍速） |
| 短语 | 同单词模板，引号里换成短语，例如 `"jump up and down."` | 0 / 慢速同上 |
| 原句 | `... She reads the sentence naturally, slightly emphasizing the word "{word}". She says: "{sentence}"` | 0 |
| 系统提示语音（一次性） | 同一音色，句子来自固定清单（见 6.3.4） | 0 |

- `accent_desc`：`en-GB` → `British`（首发 *Peppa Pig* 默认），`en-US` → `American`。
- **音色一致性**：整个产品固定用同一段音色描述（存在配置 `VOICE_PROFILE` 里），保证孩子听到的始终是“同一位老师”。如果接口后续支持指定音色 ID（voice id）或参考音频，优先改用这种方式。
- **缓存键**：`sha256(model + text_prompt + audio_config)` → `asset.content_hash`；命中就直接复用，不重复生成。

#### 6.3.3 后处理与质检

生成式模型可能多说、漏说、混进背景音，所以每段音频都要过一遍：

1. `ffmpeg -af silenceremove=start_periods=1:start_threshold=-45dB,areverse,silenceremove=start_periods=1:start_threshold=-45dB,areverse,loudnorm=I=-16:TP=-1.5:LRA=11`
2. 时长检查：单词 0.3～2.5s，短语 0.6～4s，原句 ≤ 12s；超出范围就重新生成（最多 2 次）。
3. 统一输出 mp3、44.1/48kHz、单声道、64kbps（兼顾体积和音质）。
4. （P1）用语音识别（ASR）回听，核对转写结果是否包含目标词；不包含就重新生成。
5. 家长审核页提供试听按钮，可以单条“重新生成发音”。

#### 6.3.4 系统提示语音清单（预生成，存为静态资源）

`Listen!`、`Where is ...?`、`Tap the picture!`、`Great!`、`Well done!`、`You got it!`、`Try again!`、`Let's learn some words!`、`Today we will watch Peppa Pig!`、`Now let's watch! Listen for these words!`、`Let's review!`、`You did it! Here's a sticker!`、`Ask Mommy or Daddy for a new show!`

这些由脚本 `scripts/gen_system_voice.py` 一次性生成，人工试听确认后放进 `frontend/public/voice/`，跟随前端包发布，不在运行时调用 TTS。

#### 6.3.5 客户端实现要点

```python
# backend/app/assets/tts_seed.py（示意）
import base64, httpx

TTS_URL = "https://openspeech.bytedance.com/api/v3/tts/create"

class SeedTTS:
    def __init__(self, api_key: str, client: httpx.AsyncClient):
        self._key, self._http = api_key, client

    async def synthesize(self, text_prompt: str, speech_rate: int = 0) -> bytes:
        body = {
            "model": "seed-audio-1.0",
            "text_prompt": text_prompt,
            "audio_config": {"format": "mp3", "sample_rate": 48000,
                             "pitch_rate": 0, "speech_rate": speech_rate, "loudness_rate": 0},
            "watermark": {},
        }
        r = await self._http.post(TTS_URL, json=body, timeout=300,
                                  headers={"X-Api-Key": self._key})
        r.raise_for_status()
        if r.headers.get("content-type", "").startswith("audio/"):
            return r.content
        data = r.json()
        # TODO 联调后只保留实际使用的分支
        if b64 := (data.get("data") or data.get("audio")):
            return base64.b64decode(b64)
        if url := data.get("url") or data.get("audio_url"):
            return (await self._http.get(url, timeout=60)).content
        raise TTSUnexpectedResponse(data)
```

- 并发：用 `asyncio.Semaphore(TTS_CONCURRENCY)` 限制并发，默认 8，拿到 QPS 限制后再调整。
- 重试：网络错误、429、5xx 按指数退避重试（1s / 2s / 4s，最多 3 次）；4xx 不重试，直接记错误。
- 每次调用写一条 `cost_ledger`（provider=`bytedance_seed_audio`，units=字符数或秒数，具体以计费方式为准）。
- 日志里**不打印**请求头和密钥。

### 6.4 生图

- **接口抽象**：`ImageProvider.generate(prompt, size=1024) -> bytes`，具体服务商通过配置切换。
- **提示词模板**（统一风格）：`{image_prompt}. Children's picture-book flat illustration, bold clean outlines, bright saturated colors, single centered subject, plain pastel background, no text, no letters, no watermark.`
- 不使用任何版权角色形象（Peppa 等）：提示词里禁止出现角色名，LLM 生成 `image_prompt` 时替换成 `a cute cartoon pig` 这样的通用描述。
- **内置图库优先**：首发剧集的高频词（rain、puddle、boots、jump、mud 等）由人工精修后放进图库，作为 `vocab_item.default_image_id`，命中时不调用生图。
- 后处理：缩放到 768×768，转 webp（质量 80），单张控制在 100KB 以内。
- 内容安全：使用服务商自带的安全过滤，加上家长审核兜底；被家长“换一张”的图片标为 `rejected`，以后不再复用。

> 生图服务商还没有指定，需要单独确认。可选方向：与 TTS 同属字节的火山引擎生图服务，或其他文生图 API。

### 6.5 课程编排（`lessons/builder.py`）

| 步骤 | 规则 |
| --- | --- |
| 条目顺序 | 预习：名词 → 动词 → 形容词 → 短语（由易到难）；复习：随机打乱 |
| 干扰项 | 优先取本集其他条目；不够时从同类别的全局词条补；预习阶段排除发音相近的组合（编辑距离 ≤ 1，或同一组最小对立词，如 cat / cap） |
| 选项位置 | 随机排列，并保证正确答案不会连续 3 题出现在同一个位置 |
| 混入旧词 | 复习时混入 `mastery.next_due_at <= today` 的旧词，最多 3 个，薄弱词优先 |
| 未预习直接复习 | 在热身环节前插入每个条目的 Q1 认识卡（图 + 读音 1 遍） |
| 时长估算 | 每步预估秒数求和，超过 8 分钟时减少 Q2，不减少 Q3 |

题目序列在生成时由服务端随机决定，写进课程包，前端只负责按顺序播放，便于复现问题。

### 6.6 间隔复习调度（`progress/scheduler.py`）

```
首次作答（每题只看第一次选择）：
  答对：correct_streak += 1
  答错：correct_streak = 0；wrong_count += 1
状态：
  correct_streak >= 3 且三次分布在不同的天 → mastered
  否则                                   → learning
next_due_at：首次学习后第 1、3、7 天依次排期；答错时重置为明天
```

---

## 7. 前端设计

### 7.1 目录与路由

```
frontend/src/
  app/            路由、全局布局、家长锁
  child/          Home、LessonPlayer、StickerBook
  parent/         Episodes、TranscriptInput、ReviewItems、Reports、Settings
  player/         lessonMachine.ts（状态机）、audioEngine.ts、steps/Q1..Q5.tsx
  offline/        lessonCache.ts、attemptQueue.ts（IndexedDB）
  api/            自动生成的 TS 客户端（openapi-typescript）
```

| 路由 | 页面 |
| --- | --- |
| `/` | 孩子首页（看前 / 看后 / 小复习 / 贴纸册） |
| `/play/:episodeId/:mode` | 课程播放器 |
| `/stickers` | 贴纸册 |
| `/parent/*` | 家长端（先通过家长锁：算术题或长按 3 秒） |

### 7.2 课程播放器状态机

```
loading（预加载本节全部素材）
  → step.enter → playingPrompt → awaitingTap
       ├─ 点中正确 → feedbackCorrect（弹跳 + 鼓励语音 + 再读一遍） → next
       ├─ 点中错误（第 1 次） → feedbackWrong（晃动 + 重播题目） → awaitingTap
       ├─ 点中错误（第 2 次） → revealAnswer（正确图发光 + 读 2 遍） → next（该条进入错题回炉）
       ├─ 10s 无操作 → 重播题目；30s 无操作 → 正确选项轻微闪动
       └─ 长按“回家” 2s → 保存进度并退出
  → 全部完成 → 错题回炉（Q2） → outro（贴纸） → POST finish
```

### 7.3 音频与 iOS 兼容

- iOS Safari 必须在用户手势里才能开始播放：首页第一次点击时解锁 AudioContext（播放一段静音）。
- 进入课程前用 Howler 把本节全部 mp3 预加载完（10 个条目约 30 段，按每段 20KB 算约 600KB）；预加载完成前显示 loading 动画。
- 同一时间只播放一段语音：新语音开始时停止上一段，避免叠音。

### 7.4 离线

- 应用外壳和系统提示语音：构建时预缓存。
- 课程包：家长点“生成”完成后，或孩子首页加载时，后台预取今日课程包和其中的所有素材，存进 Cache Storage（`lesson-{id}`）。
- 作答记录：先写入 IndexedDB 队列，联网后批量上传，靠 `client_attempt_id` 保证不重复。
- iOS 上网页应用的存储有容量和清理限制：只保留最近 7 天的课程缓存，并用 `navigator.storage.persist()` 申请持久化存储（是否足够需要按 PRD 12.2 做技术验证）。

### 7.5 界面规范（落实 PRD 交互原则）

- 横屏；选项卡片 ≥ 120×120pt，四选一用 2×2 网格；
- 孩子端组件库里**禁止出现文本组件**（ESLint 自定义规则：`child/`、`player/` 目录下禁止 JSX 中的字面量文本）；
- 颜色不作为唯一的对错信号，同时配合动效区分。

---

## 8. 安全与隐私

| 项 | 措施 |
| --- | --- |
| 第三方密钥 | `VOLC_TTS_API_KEY`、`ANTHROPIC_API_KEY`、生图密钥只放在服务端环境变量 / 密钥管理里；**不提交到仓库**、不下发前端、不写进日志；仓库只放 `.env.example` |
| 密钥泄露处理 | 一旦密钥出现在聊天记录、截图或提交历史中，视为已泄露，立即在控制台轮换 |
| 儿童数据 | 不采集孩子的真实姓名、照片、录音；只存昵称和学习记录；家长可一键导出 / 删除全部数据 |
| 鉴权 | 家长 JWT（httpOnly + SameSite=Lax + Secure）；孩子端沿用家长的会话，通过家长锁区分界面 |
| 台词版权 | 台词只用于本家庭的学习，不公开、不跨账号共享；对象存储里只放生成的素材，不存视频 |
| 外部调用 | 所有对外请求只由 worker 发出；限制可访问的域名白名单 |

---

## 9. 可观测性与成本

- 结构化日志（JSON），带 `episode_id` / `job_id`。
- 指标：每集提取耗时、生成耗时、TTS / 生图失败率、重新生成率、家长“换一张”比例、课程包加载耗时。
- `cost_ledger` 按天、按剧集汇总，在家长端（或内部管理页）展示每集实际成本，为以后定价和限额积累数据（PRD 决策 #6）。

---

## 10. 配置项（`.env.example`）

```dotenv
DATABASE_URL=postgresql+asyncpg://app:app@postgres:5432/app
REDIS_URL=redis://redis:6379/0
S3_ENDPOINT=http://minio:9000
S3_BUCKET=cartoon-vocab
CDN_BASE_URL=http://localhost:9000/cartoon-vocab

ANTHROPIC_API_KEY=            # Claude API
LLM_MODEL=claude-opus-5-5

VOLC_TTS_API_KEY=             # 字节 seed-audio（不要把真实值提交到仓库）
TTS_MODEL=seed-audio-1.0
TTS_CONCURRENCY=8
VOICE_PROFILE="A warm, cheerful young British female voice"

IMAGE_PROVIDER=               # 待定
IMAGE_API_KEY=
```

---

## 11. 代码仓库结构（建议）

```
cartoon-vocab/
  backend/
    app/
      api/ (routers)  auth/  episodes/  transcript/  extraction/
      assets/ (tts_seed.py, image_provider.py, postprocess.py)
      lessons/  progress/  reports/  billing/
      worker.py  config.py  db.py
    alembic/
    tests/
  frontend/  (见 7.1)
  scripts/
    gen_system_voice.py      # 预生成系统提示语音
    seed_peppa_s1e1.py       # 导入首发剧集与精修图库
  docker-compose.yml
  .env.example
```

---

## 12. 测试策略

| 层 | 内容 |
| --- | --- |
| 单元 | 台词清洗（时间轴 / 说话人 / 音效标注）、打分函数、干扰项与选项位置规则、间隔复习调度 |
| 契约 | 用录好的响应样本测试 TTS 客户端（联调拿到真实响应后补齐）；LLM 输出的 Pydantic 校验 |
| 集成 | 用 *Peppa Pig* S1E1 台词跑完整流水线（外部服务用桩替代），检查条目数、原句可回溯、课程包结构 |
| 评测 | 首发剧集的“黄金词表”（人工标注 10～12 个），衡量 LLM 选词的重合率（PRD 目标：家长保留率 ≥ 70%） |
| 端到端 | Playwright：家长准备一集 → 孩子完成预习 / 复习 → 报告正确；离线模式下能完成一节课 |
| 真机 | iPad Safari（主屏幕模式）：音频解锁、预加载、离线、横屏 |

---

## 13. 开发计划（对应 PRD 里程碑）

| 周 | 后端 | 前端 | 内容 |
| --- | --- | --- | --- |
| 1 | 项目骨架、数据库、鉴权；**TTS 联调（确认响应格式）** | 骨架、PWA、音频引擎原型 | 首发剧集台词整理、黄金词表 |
| 2 | 清洗 + NLP + LLM 提取 | 播放器状态机 + Q1～Q3 | 系统提示语音生成并试听 |
| 3 | 素材生成流水线（TTS + 生图 + 后处理） | Q4 / Q5、反馈动效 | 精修图库（首发高频词） |
| 4 | 课程编排、作答、间隔复习 | 家长端：台词 / 审核 / 换图 | — |
| 5 | 报告、成本记账 | 首页、贴纸册、离线 | 首发剧集端到端走查 |
| 6 | 稳定性、监控 | iPad 真机打磨 | 5～10 个家庭小范围测试 |

---

## 14. 待确认事项

| # | 事项 | 影响 |
| --- | --- | --- |
| 1 | seed-audio 接口的**响应格式**、错误码、QPS / 并发限制、计费单位 | TTS 客户端实现、并发配置、成本记账 |
| 2 | `speech_rate` / `pitch_rate` / `loudness_rate` 的取值范围；能否指定固定音色 ID | 慢速音频、音色一致性 |
| 3 | `watermark` 字段的作用（是否会加可听见的水印） | 儿童体验 |
| 4 | 生图服务商选型 | 6.4 实现 |
| 5 | 部署环境与域名（国内 / 海外），以及从服务器访问 `openspeech.bytedance.com` 和 Claude API 的网络连通性 | 部署架构 |
| 6 | iPad Safari 网页应用的离线存储容量是否够用（PRD 12.2） | 离线策略 |
