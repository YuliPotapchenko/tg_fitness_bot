"""Главное меню и «запасной» обработчик любых сообщений.

Подключается ПОСЛЕДНИМ: fallback ловит всё, что не обработали остальные роутеры.
Любой текст пользователя -> удаляем его и показываем главное меню (чат остаётся чистым).
"""
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.screens import show_main_menu
from app.db.models import User

router = Router(name="menu")


@router.callback_query(F.data == "menu")
async def cb_menu(cb: CallbackQuery, session: AsyncSession, user: User) -> None:
    await show_main_menu(cb, session, user)


@router.message(Command("menu"))
async def cmd_menu(message: Message, session: AsyncSession, user: User) -> None:
    await show_main_menu(message, session, user)


@router.message()
async def fallback(message: Message, session: AsyncSession, user: User) -> None:
    await show_main_menu(message, session, user)
