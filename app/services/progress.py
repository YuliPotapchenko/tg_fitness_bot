"""Бизнес-логика тренировок: прогресс, серии (streak), обратная связь, ачивки.

Правила:
  * В день можно выполнить ровно ОДНУ тренировку (во всех марафонах суммарно) —
    следующий день открывается «завтра» (по часовому поясу TIMEZONE).
  * Нельзя перескочить день: выдаётся только progress.current_day.
  * Прогресс по каждому марафону хранится в отдельной строке user_progress и не удаляется при смене марафона.
"""
import datetime as dt
import logging
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import (
    Achievement,
    Marathon,
    User,
    UserAchievement,
    UserProgress,
    Workout,
    WorkoutLog,
)

log = logging.getLogger(__name__)

FEEDBACK_LABELS = {"easy": "Легко 😌", "normal": "Нормально 👌", "hard": "Тяжело 🥵"}


# ---------- даты и подписка ----------

def today() -> dt.date:
    """Сегодняшняя дата в часовом поясе проекта."""
    return dt.datetime.now(settings.tz).date()


def subscription_active(user: User) -> bool:
    return user.subscription_end >= today()


def days_left(user: User) -> int:
    return max((user.subscription_end - today()).days, 0)


def effective_streak(user: User) -> int:
    """Серия «сгорает», если вчера и сегодня тренировок не было."""
    if user.last_activity_date and user.last_activity_date >= today() - dt.timedelta(days=1):
        return user.streak
    return 0


def done_today(user: User) -> bool:
    return user.last_activity_date == today()


# ---------- выборки ----------

async def get_user_by_tg(session: AsyncSession, telegram_id: int) -> User | None:
    return (await session.execute(select(User).where(User.telegram_id == telegram_id))).scalar_one_or_none()


async def list_marathons(session: AsyncSession) -> list[Marathon]:
    q = select(Marathon).where(Marathon.is_active.is_(True)).order_by(Marathon.sort_order, Marathon.id)
    return list((await session.execute(q)).scalars())


async def get_progress(session: AsyncSession, user_id: int, marathon_id: int) -> UserProgress:
    """Возвращает прогресс по марафону, создавая его при первом обращении."""
    q = select(UserProgress).where(UserProgress.user_id == user_id, UserProgress.marathon_id == marathon_id)
    progress = (await session.execute(q)).scalar_one_or_none()
    if progress:
        return progress
    try:
        # savepoint: если параллельный запрос создал строку первым — не ломаем всю транзакцию
        async with session.begin_nested():
            progress = UserProgress(user_id=user_id, marathon_id=marathon_id, current_day=1, completed_days=0)
            session.add(progress)
        return progress
    except IntegrityError:
        return (await session.execute(q)).scalar_one()


async def progress_map(session: AsyncSession, user_id: int) -> dict[int, UserProgress]:
    rows = (await session.execute(select(UserProgress).where(UserProgress.user_id == user_id))).scalars()
    return {p.marathon_id: p for p in rows}


async def get_workout(session: AsyncSession, marathon_id: int, day: int) -> Workout | None:
    q = select(Workout).where(Workout.marathon_id == marathon_id, Workout.day_number == day)
    return (await session.execute(q)).scalar_one_or_none()


# ---------- выполнение тренировки ----------

@dataclass
class CompleteResult:
    status: str  # ok | already_done | finished | no_marathon
    day: int = 0
    marathon_finished: bool = False
    new_achievements: list[Achievement] = field(default_factory=list)


async def complete_workout(session: AsyncSession, user: User) -> CompleteResult:
    """Отмечает текущий день выполненным. Защищено от двойных нажатий блокировкой строки пользователя."""
    if user.current_marathon_id is None:
        return CompleteResult("no_marathon")

    # Блокируем строку пользователя и перечитываем актуальные данные:
    # второй параллельный клик «Я выполнил» дождётся первого и увидит last_activity_date == today.
    await session.refresh(user, with_for_update=True)
    t = today()
    if user.last_activity_date == t:
        return CompleteResult("already_done")

    marathon = await session.get(Marathon, user.current_marathon_id)
    if marathon is None:
        return CompleteResult("no_marathon")
    progress = await get_progress(session, user.id, marathon.id)
    if progress.is_finished:
        return CompleteResult("finished")

    day = progress.current_day
    session.add(WorkoutLog(user_id=user.id, marathon_id=marathon.id, day_number=day, completed_on=t))

    progress.completed_days += 1
    progress.current_day = day + 1
    finished = progress.current_day > marathon.total_days
    if finished:
        progress.is_finished = True

    # Ударный режим: вчера тренировался — серия растёт, иначе начинается заново
    if user.last_activity_date == t - dt.timedelta(days=1):
        user.streak += 1
    else:
        user.streak = 1
    user.best_streak = max(user.best_streak, user.streak)
    user.last_activity_date = t

    await session.flush()
    new_ach = await check_achievements(session, user, marathon_finished=finished)
    return CompleteResult("ok", day=day, marathon_finished=finished, new_achievements=new_ach)


async def set_feedback(session: AsyncSession, user: User, value: str) -> None:
    """Сохраняет оценку сложности для тренировки, выполненной сегодня."""
    if value not in FEEDBACK_LABELS:
        return
    q = (
        select(WorkoutLog)
        .where(WorkoutLog.user_id == user.id, WorkoutLog.completed_on == today())
        .order_by(WorkoutLog.id.desc())
        .limit(1)
    )
    entry = (await session.execute(q)).scalar_one_or_none()
    if entry:
        entry.feedback = value


# ---------- достижения ----------

async def check_achievements(session: AsyncSession, user: User, marathon_finished: bool = False) -> list[Achievement]:
    total = (
        await session.execute(select(func.count()).select_from(WorkoutLog).where(WorkoutLog.user_id == user.id))
    ).scalar_one()

    conditions = {
        "first_workout": total >= 1,
        "workouts_10": total >= 10,
        "workouts_30": total >= 30,
        "streak_3": user.streak >= 3,
        "streak_7": user.streak >= 7,
        "streak_14": user.streak >= 14,
        "marathon_finished": marathon_finished,
    }
    catalog = {a.code: a for a in (await session.execute(select(Achievement))).scalars()}
    owned = set(
        (await session.execute(select(UserAchievement.achievement_id).where(UserAchievement.user_id == user.id))).scalars()
    )

    new: list[Achievement] = []
    for code, ok in conditions.items():
        ach = catalog.get(code)
        if ok and ach and ach.id not in owned:
            session.add(UserAchievement(user_id=user.id, achievement_id=ach.id))
            new.append(ach)
    await session.flush()
    return new


@dataclass
class Stats:
    total_workouts: int
    finished_marathons: int
    streak: int
    best_streak: int
    achievements: list[tuple[Achievement, bool]]  # (ачивка, получена ли)


async def get_stats(session: AsyncSession, user: User) -> Stats:
    total = (
        await session.execute(select(func.count()).select_from(WorkoutLog).where(WorkoutLog.user_id == user.id))
    ).scalar_one()
    finished = (
        await session.execute(
            select(func.count()).select_from(UserProgress).where(UserProgress.user_id == user.id, UserProgress.is_finished)
        )
    ).scalar_one()
    all_ach = list((await session.execute(select(Achievement).order_by(Achievement.sort_order))).scalars())
    owned = set(
        (await session.execute(select(UserAchievement.achievement_id).where(UserAchievement.user_id == user.id))).scalars()
    )
    return Stats(
        total_workouts=total,
        finished_marathons=finished,
        streak=effective_streak(user),
        best_streak=user.best_streak,
        achievements=[(a, a.id in owned) for a in all_ach],
    )
