"""进程内调度：每分钟检查到期的监测词；免打扰队列每分钟检查；每天 03:30 清理过期数据。"""
import logging

from apscheduler.schedulers.background import BackgroundScheduler

from ..config import get_settings
from . import pipeline

log = logging.getLogger(__name__)
_scheduler: BackgroundScheduler | None = None


def _safe(fn):
    def wrapper():
        try:
            fn()
        except Exception:  # 调度线程里的异常只记录，不能让调度器停掉
            log.exception("定时任务 %s 出错", fn.__name__)
    wrapper.__name__ = fn.__name__
    return wrapper


def start() -> None:
    global _scheduler
    if _scheduler:
        return
    s = get_settings()
    _scheduler = BackgroundScheduler(timezone=s.timezone)
    _scheduler.add_job(_safe(pipeline.run_due), "interval", seconds=60, id="run_due",
                       max_instances=1, coalesce=True, next_run_time=None)
    _scheduler.add_job(_safe(pipeline.cleanup), "cron", hour=3, minute=30, id="cleanup")
    _scheduler.start()
    # 启动后 5 秒先跑一轮，不用等一分钟
    from datetime import datetime, timedelta
    _scheduler.get_job("run_due").modify(next_run_time=datetime.now(_scheduler.timezone) + timedelta(seconds=5))
    log.info("调度器已启动：采集间隔 %s 分钟", s.crawl_interval_min)


def trigger_now() -> None:
    """新建关键词组后立即跑一轮（回溯）。"""
    if _scheduler and _scheduler.get_job("run_due"):
        from datetime import datetime
        _scheduler.get_job("run_due").modify(next_run_time=datetime.now(_scheduler.timezone))


def shutdown() -> None:
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
