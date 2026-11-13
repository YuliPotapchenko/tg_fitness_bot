"""Фоновая рассылка пуш-уведомлений («пора на тренировку»).

Важно для бесплатного Neon: база засыпает после нескольких минут простоя, а бесплатные часы
вычислений ограничены. Поэтому планировщик НЕ опрашивает БД каждую минуту. Он держит в памяти
множество «минут суток», на которые у кого-то назначен пуш, и обращается к БД только в эти минуты.
Множество загружается при старте и пополняется, когда пользователь меняет время (register_push_minute).
"""
import asyncio
import datetime as dt
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError
from sqlalchemy import or_, select

from app.bot import keyboards
from app.config import settings
from app.db.models import DEFAULT_PUSH_TIME, User
from app.db.session import session_maker
from app.services import progress as svc

log = logging.getLogger(__name__)

_push_minutes: set[int] = {DEFAULT_PUSH_TIME.hour * 60 + DEFAULT_PUSH_TIME.minute}


def register_push_minute(t: dt.time) -> None:
    """Вызывается при смене времени уведомления пользователем."""
    _push_minutes.add(t.hour * 60 + t.minute)


async def _load_push_minutes() -> None:
    async with session_maker() as session:
        rows = (await session.execute(select(User.push_time).where(User.push_enabled.is_(True)).distinct())).scalars()
        for t in rows:
            register_push_minute(t)


async def _send_pushes(bot: Bot, day: dt.date, minutes: list[int]) -> None:
    times = [dt.time(m // 60, m % 60) for m in minutes]
    async with session_maker() as session:
        q = select(User).where(
            User.telegram_id.is_not(None),
            User.push_enabled.is_(True),
            User.push_time.in_(times),
            User.subscription_end >= day,
            User.current_marathon_id.is_not(None),
            or_(User.last_push_date.is_(None), User.last_push_date != day),
            or_(User.last_activity_date.is_(None), User.last_activity_date != day),
        )
        users = list((await session.execute(q)).scalars())
        for user in users:
            try:
                progress = await svc.get_progress(session, user.id, user.current_marathon_id)
                if progress.is_finished:
                    continue
                await bot.send_message(
                    user.telegram_id,
                    f"⏰ <b>Пора на тренировку!</b>\nСегодня тебя ждёт день {progress.current_day}. Всего 1 тренировка — и серия продолжается 🔥",
                    reply_markup=keyboards.push_start(),
                )
                user.last_push_date = day
            except TelegramForbiddenError:
                user.push_enabled = False  # пользователь заблокировал бота — больше не беспокоим
            except TelegramAPIError as exc:
                log.warning("Не удалось отправить пуш %s: %s", user.telegram_id, exc)
            await asyncio.sleep(0.05)  # лимиты Telegram: ~30 сообщений/сек
        await session.commit()


async def push_loop(bot: Bot) -> None:
    """Бесконечный цикл. Запускается как фоновая задача в lifespan FastAPI."""
    await _load_push_minutes()
    now = dt.datetime.now(settings.tz)
    last_day, last_min = now.date(), now.hour * 60 + now.minute
    while True:
        await asyncio.sleep(20)
        try:
            now = dt.datetime.now(settings.tz)
            day, cur = now.date(), now.hour * 60 + now.minute
            if day != last_day:
                minutes = [cur]
            else:
                # догоняем пропущенные минуты (если цикл задержался), но не больше 15
                minutes = list(range(max(last_min + 1, cur - 14), cur + 1))
            due = [m for m in minutes if m in _push_minutes]
            if due:
                await _send_pushes(bot, day, due)
            last_day, last_min = day, cur
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.exception("Ошибка в цикле пушей")
