# 声眼舆情监测 V1

单租户、只监测小红书、无需登录的舆情系统：按关键词通过 TikHub 抓取小红书笔记，DeepSeek 判断情感，负面内容推送到企业微信 / 飞书 / 邮件。前端是工作台版界面，由后端直接提供，本地浏览器打开即可使用。

## 本地运行

代码在分支 `claude/keen-lovelace-3t1bm7`（还没合并到 master）：

```bash
git fetch origin
git checkout claude/keen-lovelace-3t1bm7
```

需要 Python 3.10 及以上。最简单的方式：Windows 双击 `shengyan/start.bat`，Mac / Linux 运行 `bash shengyan/start.sh`。第一次会自动安装依赖并生成 `.env`，之后把 Key 填进 `.env` 再重新启动。

也可以手动：

```bash
cd shengyan
python -m venv .venv
source .venv/bin/activate          # Windows：.venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # 填入 TIKHUB_API_KEY 和 LLM_API_KEY
python run.py
```

终端出现 `Application startup complete` 后，浏览器打开 http://127.0.0.1:8000 即可使用（运行期间不要关掉终端窗口），不需要登录。首次启动会自动创建关键词组“全嘻嘻”并开始回溯近 3 天的内容；想换默认词，在首次启动前修改 `.env` 里的 `DEFAULT_KEYWORDS`，之后在“关键词管理”页增删即可。

**只在本机访问**：系统没有登录，服务默认只监听 `127.0.0.1`。如果设置 `HOST=0.0.0.0` 让同一网络里的其他电脑访问，任何能连上的人都能查看和修改数据。

**不填 Key 也能跑**：没有 `TIKHUB_API_KEY` 时使用演示数据源，没有 `LLM_API_KEY` 时使用本地规则判断情感，页面右上角会标出当前是演示模式。想更快看到增量数据和预警，可以设置 `CRAWL_INTERVAL_MIN=1`。

## 打不开页面时

| 现象 | 原因与处理 |
| --- | --- |
| 浏览器提示“无法访问此网站 / 拒绝连接” | 服务没在运行。先执行 `python run.py`（或 start 脚本），窗口保持打开 |
| 找不到 `shengyan` 目录 | 还在 master 分支，按上面切换到 `claude/keen-lovelace-3t1bm7` |
| 提示“需要 Python 3.10 或更高版本” | 升级 Python |
| 提示 `No module named ...` | 在 `shengyan` 目录执行 `pip install -r requirements.txt` |
| 提示“端口 8000 已被占用” | 已经有一个在运行，直接打开页面；或用 `PORT=8001` 换端口 |
| `localhost` 打不开但服务在运行 | 改用 http://127.0.0.1:8000 |

仍然不行时，把终端里的完整输出发给开发者。

## 密钥

TikHub Token 和 DeepSeek Key 只放在 `.env`（已被 `.gitignore` 忽略），不要写进代码或提交到仓库。在聊天、文档等地方明文出现过的 Key，上线前请到对应控制台重新生成。

## 运行测试

```bash
pytest -q
```

测试不访问外网：TikHub、DeepSeek 和机器人推送都用 `httpx.MockTransport` 模拟。

## 目录

| 路径 | 内容 |
| --- | --- |
| `app/crawlers/xiaohongshu.py` | TikHub 搜索笔记适配器：鉴权、限流、重试、字段映射 |
| `app/crawlers/mock.py` | 演示数据源 |
| `app/analysis/` | 关键词二次校验、相似内容归并、情感判断（DeepSeek / 规则） |
| `app/alerts/` | 预警判定、6 小时降噪、免打扰合并推送、三个推送渠道 |
| `app/jobs/` | 增量采集、新词回溯、调度器 |
| `app/api/routes.py` | `/api/v1` 接口 |
| `static/` | 前端（工作台版） |
| `tests/` | 单元与接口测试 |

## 与技术文档的差异

为了本地一条命令就能启动，V1 做了以下简化，后续可按文档替换：

- 数据库默认 SQLite，设置 `DATABASE_URL` 可切换到 PostgreSQL（需另装 `psycopg`）。
- 不用 Redis 队列，调度和采集在应用进程内运行（APScheduler），监测词按顺序采集。
- 单租户本地使用，去掉了登录和成员管理（技术文档第 7 节中的 /auth、/users 接口）。
- 机器人 Webhook 地址明文存库，只允许企业微信 / 飞书官方域名。

## 待联调确认

- **TikHub 返回结构**：字段映射是按候选路径查找的（`app/crawlers/xiaohongshu.py` 的 `map_note`），并在 `posts.raw` 保存原始 JSON。拿到真实响应后，核对笔记 ID、发布时间、互动数等字段，必要时调整映射。
- **TikHub 限流与单价**：默认每秒 1 次请求、每 10 分钟一轮，确认后调整 `TIKHUB_MIN_INTERVAL_MS`、`CRAWL_INTERVAL_MIN`。
