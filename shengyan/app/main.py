"""应用入口：python run.py 或 uvicorn app.main:app，然后浏览器打开 http://localhost:8000"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select, text

from .api.routes import router
from .config import BASE_DIR, get_settings
from .db import SessionLocal, init_db
from .jobs import scheduler
from .models import CrawlState, User
from .settings_store import save_crawler_status

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("shengyan")
STATIC_DIR = BASE_DIR / "static"


def seed() -> None:
    s = get_settings()
    with SessionLocal() as db:
        if not db.scalar(select(func.count(User.id))):
            db.add(User(phone=s.admin_phone, name=s.admin_name, role="admin"))
            log.info("已创建管理员账号 %s", s.admin_phone)
        save_crawler_status(db, auth_failed=False, auth_error="", paused_until=None)  # 重启即重试
        db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    if s.app_env != "dev" and (s.app_secret_key == "change-me-in-production" or len(s.app_secret_key) < 32):
        raise RuntimeError("生产环境必须设置至少 32 位的 APP_SECRET_KEY")
    init_db()
    seed()
    log.info("数据源：%s；情感判断：%s", s.effective_crawler_mode, s.effective_sentiment_mode)
    if s.effective_crawler_mode == "mock":
        log.warning("未配置 TIKHUB_API_KEY，使用演示数据源（mock）")
    if s.effective_sentiment_mode == "rule":
        log.warning("未配置 LLM_API_KEY，情感判断使用本地规则（仅供演示）")
    if s.enable_scheduler:
        scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(title="声眼舆情监测 V1", lifespan=lifespan)
app.include_router(router)


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    return JSONResponse({"code": exc.status_code, "message": exc.detail}, status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    msgs = []
    for e in exc.errors():
        msg = str(e.get("msg", "")).removeprefix("Value error, ")
        msgs.append(msg)
    return JSONResponse({"code": 422, "message": "；".join(msgs) or "请求参数不正确"}, status_code=422)


@app.get("/healthz")
def healthz():
    with SessionLocal() as db:
        db.execute(text("SELECT 1"))
        last = db.scalar(select(func.max(CrawlState.last_success_at)))
    return {"ok": True, "db": "ok", "last_success_at": last.isoformat() + "Z" if last else None}


if (STATIC_DIR / "index.html").exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC_DIR / "index.html")
