"""Подключение к PostgreSQL (Neon) через SQLAlchemy 2.0 + asyncpg.

Особенности Neon:
  * нужен SSL (в строке подключения sslmode=require, asyncpg такой параметр не понимает,
    поэтому мы вырезаем его и передаём ssl через connect_args);
  * «пулер» Neon работает на базе pgbouncer, поэтому отключаем кэш prepared statements;
  * вычислительный узел засыпает после простоя, соединения при этом рвутся —
    включаем pool_pre_ping и короткий pool_recycle.
"""
import asyncio
import logging
import uuid

from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.db.base import Base

log = logging.getLogger(__name__)

LOCAL_HOSTS = {"localhost", "127.0.0.1", "db", "postgres"}


def _prepare_url(raw: str) -> tuple[URL, dict]:
    url = make_url(raw)
    # postgres:// и postgresql:// -> драйвер asyncpg
    url = url.set(drivername="postgresql+asyncpg")

    query = dict(url.query)
    sslmode = query.pop("sslmode", None)
    query.pop("channel_binding", None)  # Neon может добавлять этот параметр, asyncpg его не знает
    query.pop("ssl", None)
    url = url.set(query=query)

    connect_args: dict = {
        "statement_cache_size": 0,
        "prepared_statement_cache_size": 0,
        "prepared_statement_name_func": lambda: f"__asyncpg_{uuid.uuid4()}__",
    }
    if sslmode != "disable" and (url.host or "") not in LOCAL_HOSTS:
        connect_args["ssl"] = "require"
    return url, connect_args


def _build_engine() -> AsyncEngine:
    url, connect_args = _prepare_url(settings.DATABASE_URL)
    return create_async_engine(
        url,
        pool_size=5,
        max_overflow=2,
        pool_pre_ping=True,   # проверка соединения перед использованием (Neon мог его закрыть)
        pool_recycle=300,     # пересоздавать соединения каждые 5 минут
        connect_args=connect_args,
    )


engine: AsyncEngine = _build_engine()
session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db(retries: int = 5) -> None:
    """Создаёт таблицы. Повторяет попытки: Neon после простоя просыпается 1–3 секунды."""
    # импорт моделей нужен, чтобы они зарегистрировались в Base.metadata
    from app.db import models  # noqa: F401

    for attempt in range(1, retries + 1):
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            log.info("Таблицы БД готовы")
            return
        except Exception as exc:  # noqa: BLE001
            log.warning("Не удалось подключиться к БД (попытка %s/%s): %s", attempt, retries, exc)
            if attempt == retries:
                raise
            await asyncio.sleep(2 * attempt)
