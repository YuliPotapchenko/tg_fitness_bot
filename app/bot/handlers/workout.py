"""Тренировка: выдача дня, кнопка «Я выполнил», обратная связь.

Защита от «перепрыгивания» дней:
  * выдаётся только progress.current_day (выбрать день вручную нельзя — такой кнопки нет);
  * после «Я выполнил» дата фиксируется в user.last_activity_date, и до завтра экран тренировки закрыт;
  * двойной клик обрабатывается блокировкой строки пользователя (см. services.progress.complete_workout).
"""
from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards, texts
from app.bot.screens import show_catalog, show_main_menu
from app.bot.utils import show
from app.db.models import Marathon, User
from app.services import progress as svc

router = Router(name="workout")


@router.callback_query(F.data == "workout:start")
async def workout_start(cb: CallbackQuery, session: AsyncSession, user: User) -> None:
    if user.current_marathon_id is None:
        await show_catalog(cb, session, user)
        return
    if svc.done_today(user):
        await show(cb, texts.workout_done_today(), keyboards.only_menu(), user)
        return

    marathon = await session.get(Marathon, user.current_marathon_id)
    if marathon is None:
        await show_catalog(cb, session, user)
        return
    progress = await svc.get_progress(session, user.id, marathon.id)
    if progress.is_finished:
        await show(cb, texts.marathon_finished_screen(marathon), keyboards.menu_and_catalog(), user)
        return

    workout = await svc.get_workout(session, marathon.id, progress.current_day)
    if workout is None:
        await show(cb, texts.workout_missing(marathon, progress.current_day), keyboards.only_menu(), user)
        return
    # Редактируем то же сообщение: меню превращается в экран тренировки
    await show(cb, texts.workout(marathon, workout), keyboards.workout(workout.video_url), user)


@router.callback_query(F.data == "workout:done")
async def workout_done(cb: CallbackQuery, session: AsyncSession, user: User) -> None:
    result = await svc.complete_workout(session, user)

    if result.status == "already_done":
        await show(cb, texts.workout_done_today(), keyboards.only_menu(), user)
    elif result.status == "no_marathon":
        await show_catalog(cb, session, user)
    elif result.status == "finished":
        marathon = await session.get(Marathon, user.current_marathon_id)
        await show(cb, texts.marathon_finished_screen(marathon), keyboards.menu_and_catalog(), user)
    else:
        # Экран завершения: сбор обратной связи
        await show(
            cb,
            texts.completed(result.day, result.marathon_finished, result.new_achievements),
            keyboards.feedback(),
            user,
        )


@router.callback_query(F.data.startswith("fb:"))
async def workout_feedback(cb: CallbackQuery, session: AsyncSession, user: User) -> None:
    value = (cb.data or "").split(":", 1)[1]
    if value not in svc.FEEDBACK_LABELS or not svc.done_today(user):
        await show_main_menu(cb, session, user)  # устаревшая кнопка
        return

    await svc.set_feedback(session, user, value)
    finished = False
    if user.current_marathon_id:
        finished = (await svc.get_progress(session, user.id, user.current_marathon_id)).is_finished
    kb = keyboards.menu_and_catalog() if finished else keyboards.only_menu()
    await show(cb, texts.feedback_thanks(0, finished, svc.FEEDBACK_LABELS[value]), kb, user)
