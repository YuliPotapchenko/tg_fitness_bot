"""Health-check для Render и UptimeRobot.

/health НЕ обращается к БД: иначе UptimeRobot каждые 5 минут будил бы Neon и съедал бесплатные часы.
UptimeRobot на бесплатном тарифе шлёт HEAD-запросы — поэтому принимаем и GET, и HEAD.
/health/db — ручная проверка БД (не вешайте её на мониторинг).
"""
from fastapi import APIRouter
from sqlalchemy import text

from app.db.session import engine

router = APIRouter()


@router.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
@router.api_route("/health", methods=["GET", "HEAD"])
async def health() -> dict:
    return {"status": "ok"}


@router.get("/health/db")
async def health_db() -> dict:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    return {"status": "ok", "db": True}
