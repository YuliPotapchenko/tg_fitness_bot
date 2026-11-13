"""Настройки: тариф, срок подписки, время пуш-уведомлений."""
import datetime as dt

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards, texts
from app.bot.utils import show
from app.db.models import User
from app.services.scheduler import register_push_minute

router = Router(name="settings")


async def _show_settings(cb: CallbackQuery, user: User) -> None:
    await show(cb, texts.settings_screen(user), keyboards.settings_kb(user.push_enabled), user)


@router.callback_query(F.data == "settings")
async def settings_open(cb: CallbackQuery, session: AsyncSession, user: User) -> None:
    await _show_settings(cb, user)


@router.callback_query(F.data == "push:toggle")
async def push_toggle(cb: CallbackQuery, session: AsyncSession, user: User) -> None:
    user.push_enabled = not user.push_enabled
    if user.push_enabled:
        register_push_minute(user.push_time)
    await _show_settings(cb, user)


@router.callback_query(F.data == "push:time")
async def push_time(cb: CallbackQuery, session: AsyncSession, user: User) -> None:
    await show(cb, texts.push_time_screen(), keyboards.push_times(), user)


@router.callback_query(F.data.startswith("push:set:"))
async def push_set(cb: CallbackQuery, session: AsyncSession, user: User) -> None:
    raw = (cb.data or "").rsplit(":", 1)[1]
    allowed = {t.replace(":", "") for t in keyboards.PUSH_TIMES}
    if raw not in allowed:  # защита от подделанного callback_data
        await _show_settings(cb, user)
        return
    new_time = dt.time(int(raw[:2]), int(raw[2:]))
    user.push_time = new_time
    user.push_enabled = True
    register_push_minute(new_time)  # планировщик должен «проснуться» в эту минуту
    await _show_settings(cb, user)
