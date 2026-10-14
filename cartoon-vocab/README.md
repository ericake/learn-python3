# 动画词卡（Cartoon Word Pal）MVP

6 岁孩子看英文动画前后，用“听音识图”预习 / 复习当集重点词和短语。
需求见 [`docs/prd/cartoon-vocab-mvp-prd.md`](../docs/prd/cartoon-vocab-mvp-prd.md)，技术设计见 [`docs/tech/cartoon-vocab-tech-design-v1.md`](../docs/tech/cartoon-vocab-tech-design-v1.md)。

## 目录

```
backend/    FastAPI + SQLAlchemy（SQLite），选词 / 素材生成 / 课程编排 / 学习记录
frontend/   React + Vite PWA：孩子端（零文字）+ 家长端
```

## 本地运行

需要 Python 3.11+、Node 20+；装了 ffmpeg 时会对 TTS 音频做去静音和响度统一。

```bash
# 后端
cd backend
pip install -r requirements-dev.txt
cp .env.example .env          # 按需填写密钥，不填也能跑（见下）
uvicorn app.main:app --reload --port 8000

# 前端（另开终端）
cd frontend
npm install
npm run dev                    # http://localhost:5173 ，/api 和 /media 代理到 8000
```

生产构建：`cd frontend && npm run build`，之后后端会直接托管 `frontend/dist`，只需启动 uvicorn，访问 http://localhost:8000 。

## 外部服务与兜底

| 能力 | 配置 | 未配置时 |
| --- | --- | --- |
| 选词（Claude） | `ANTHROPIC_API_KEY` | 离线规则选词（词频 + 儿童可视化词表） |
| 语音（字节 seed-audio） | `VOLC_TTS_API_KEY` | 浏览器朗读（Web Speech），仅开发用 |
| 生图 | `IMAGE_PROVIDER`（服务商待定） | emoji 占位卡片 |

系统提示语音（"Where is…?"、"Great!" 等）配置好语音密钥后运行一次：

```bash
cd backend && python -m scripts.gen_system_voice
```

> seed-audio 接口的响应格式还没有联调确认，`app/assets/tts_seed.py` 里兼容了几种常见形式，第一次接入时请确认后删掉多余分支。

## 使用流程

1. 孩子端首页右上角 ⚙️ **长按 3 秒** → 家长验证（两位数加法）→ 家长端。
2. 新建剧集（默认填好 *Peppa Pig* S1E1）→ 粘贴台词或上传 SRT/VTT → 自动选出 10 个条目。
   可以用 `backend/scripts/samples/muddy_puddles_sample.txt`（自编的示例台词）试用。
3. 审核：移除 / 从备选加入 / 手动添加、修改原句和释义 → “确认并生成课程”。
4. 孩子端首页：🔭 看前（预习），🎁 看后（复习），两者不强制顺序；有到期旧词时出现 🔁 小复习。
5. 课程中左上角 🏠 **长按 2 秒**退出；完成一节得到一张贴纸（📒 贴纸册）。
6. 家长端“学习报告”查看完成情况、首次正确率、薄弱词。

## 测试

```bash
cd backend && python -m pytest -q
cd frontend && npm run typecheck && npm test
```

## 与技术设计 v1 的差异（第一迭代的简化）

- 数据库用 SQLite，后台任务用进程内 asyncio 代替 arq + Redis，素材存本地目录代替对象存储；接口形状不变，后续可替换。
- 暂无家长账号体系（单家庭单孩子），家长端只靠家长锁保护；**部署到公网前需要补上登录**。
- 词形还原用轻量规则 + `wordfreq` 代替 spaCy。
- 剧集开场语音暂用通用句 "Today we will watch a cartoon!"。
