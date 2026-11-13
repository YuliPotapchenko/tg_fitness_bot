"""Работа с подписками: создание/продление пользователя по данным из Tilda и генерация deep-link."""
import datetime as dt
import logging
import re
import secrets

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import User
from app.services.progress import today

log = logging.getLogger(__name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
DATE_FORMATS = ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y")


def normalize_email(value: str) -> str:
    return value.strip().lower()


def normalize_phone(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = re.sub(r"[^\d+]", "", value)
    return cleaned[:32] or None


def parse_date(value: str) -> dt.date:
    """Принимает 2026-12-31, 31.12.2026, 31/12/2026 и ISO-datetime."""
    value = value.strip()
    for fmt in DATE_FORMATS:
        try:
            return dt.datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError as exc:
        raise ValueError(f"Неверный формат даты: {value!r}") from exc


def make_deeplink(token: str) -> str:
    return f"https://t.me/{settings.BOT_USERNAME}?start={token}"


def _new_token() -> str:
    # 16 байт => ~22 символа [A-Za-z0-9_-]; Telegram разрешает payload до 64 символов
    return secrets.token_urlsafe(16)


async def upsert_subscription(
    session: AsyncSession,
    *,
    email: str,
    phone: str | None,
    subscription_end: dt.date,
    tariff: str | None,
) -> tuple[User, bool]:
    """Создаёт пользователя или продлевает существующего. Возвращает (user, created)."""
    email = normalize_email(email)

    async def _find() -> User | None:
        return (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()

    user = await _find()
    created = False
    if user is None:
        try:
            async with session.begin_nested():  # savepoint на случай гонки двух одинаковых вебхуков
                user = User(
                    email=email,
                    phone=phone,
                    start_token=_new_token(),
                    subscription_end=subscription_end,
                    tariff=tariff or "Стандарт",
                )
                session.add(user)
            created = True
        except IntegrityError:
            user = await _find()
            if user is None:
                raise

    if not created:
        user.subscription_end = subscription_end
        if phone:
            user.phone = phone
        if tariff:
            user.tariff = tariff

    await session.flush()
    log.info("Подписка %s: %s до %s", "создана" if created else "обновлена", email, subscription_end)
    return user, created


def default_end_from_days(days: int) -> dt.date:
    return today() + dt.timedelta(days=days)
