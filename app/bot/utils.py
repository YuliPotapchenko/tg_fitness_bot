"""Механика «Single Message»: один экран = одно сообщение, которое мы редактируем.

show(event, text, kb, user):
  * CallbackQuery  -> bot.edit_message_text(...) того сообщения, на кнопку которого нажали (чат не засоряется);
  * Message (/start, /menu, любой текст) -> отправляем новый экран, а предыдущее сообщение бота и
    сообщение пользователя удаляем — в чате всегда остаётся одно «живое» сообщение.
Если редактирование невозможно (сообщению > 48 ч, удалено и т.п.) — аккуратно отправляем новое.
"""
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from app.db.models import User

log = logging.getLogger(__name__)


async def _remember_and_cleanup(bot: Bot, user: User | None, chat_id: int, new_id: int) -> None:
    """Запоминает id актуального сообщения и удаляет предыдущее, если оно другое."""
    if user is None:
        return
    old_id = user.menu_message_id
    user.menu_message_id = new_id
    if old_id and old_id != new_id:
        try:
            await bot.delete_message(chat_id, old_id)
        except TelegramAPIError:
            pass  # уже удалено или слишком старое — не страшно


async def show(
    event: Message | CallbackQuery,
    text: str,
    kb: InlineKeyboardMarkup | None = None,
    user: User | None = None,
) -> None:
    bot = event.bot

    if isinstance(event, CallbackQuery):
        msg = event.message
        # InaccessibleMessage (сообщение слишком старое) редактировать нельзя
        if isinstance(msg, Message):
            try:
                # ВАЖНО: именно редактирование, а не отправка нового сообщения
                await bot.edit_message_text(
                    text=text,
                    chat_id=msg.chat.id,
                    message_id=msg.message_id,
                    reply_markup=kb,
                )
                if user is not None:
                    user.menu_message_id = msg.message_id
                return
            except TelegramBadRequest as exc:
                if "message is not modified" in str(exc):
                    return  # нажали кнопку, экран не изменился — игнорируем
                log.info("Не удалось отредактировать сообщение (%s) — отправляем новое", exc)
        sent = await bot.send_message(chat_id=event.from_user.id, text=text, reply_markup=kb)
        await _remember_and_cleanup(bot, user, event.from_user.id, sent.message_id)
        return

    # Message: /start, /menu, произвольный текст
    sent = await event.answer(text, reply_markup=kb)
    await _remember_and_cleanup(bot, user, event.chat.id, sent.message_id)
    try:
        await event.delete()  # убираем сообщение пользователя (в приватном чате бот может удалять его сообщения)
    except TelegramAPIError:
        pass
