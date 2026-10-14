from datetime import date

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Child, Episode


def current_child(db: Session = Depends(get_db)) -> Child:
    """MVP 单家庭单孩子：没有就自动创建一个。"""
    child = db.scalars(select(Child).order_by(Child.created_at).limit(1)).first()
    if child is None:
        child = Child()
        db.add(child)
        db.commit()
    return child


def get_episode(episode_id: str, db: Session = Depends(get_db), child: Child = Depends(current_child)) -> Episode:
    ep = db.get(Episode, episode_id)
    if ep is None or ep.child_id != child.id:
        raise HTTPException(404, "剧集不存在")
    return ep


def today() -> date:
    return date.today()
