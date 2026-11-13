"""Модели SQLAlchemy.

Схема:
  users ──< user_progress >── marathons ──< workouts
    │            (прогресс по каждому марафону хранится отдельно и не теряется при смене)
    ├──< workout_logs        (журнал выполненных тренировок + обратная связь)
    └──< user_achievements >── achievements
"""
import datetime as dt

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

DEFAULT_PUSH_TIME = dt.time(9, 0)


class User(Base):
    """Подписчик. Создаётся вебхуком Tilda, к Telegram привязывается по deep-link токену."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, index=True)  # NULL до привязки
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(32))
    first_name: Mapped[str | None] = mapped_column(String(255))

    start_token: Mapped[str] = mapped_column(String(64), unique=True, index=True)  # payload для /start
    tariff: Mapped[str] = mapped_column(String(64), default="Стандарт")
    subscription_end: Mapped[dt.date] = mapped_column(Date)

    current_marathon_id: Mapped[int | None] = mapped_column(ForeignKey("marathons.id", ondelete="SET NULL"))

    # Геймификация
    streak: Mapped[int] = mapped_column(Integer, default=0)
    best_streak: Mapped[int] = mapped_column(Integer, default=0)
    last_activity_date: Mapped[dt.date | None] = mapped_column(Date)  # дата последней выполненной тренировки

    # Уведомления
    push_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    push_time: Mapped[dt.time] = mapped_column(Time, default=DEFAULT_PUSH_TIME)
    last_push_date: Mapped[dt.date | None] = mapped_column(Date)

    # id «единственного сообщения» бота — чтобы удалять старое при /start
    menu_message_id: Mapped[int | None] = mapped_column(BigInteger)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    activated_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    progress: Mapped[list["UserProgress"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    achievements: Mapped[list["UserAchievement"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Marathon(Base):
    """Программа тренировок (База 1.0, Стальные тиски ...)."""

    __tablename__ = "marathons"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    title: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text, default="")
    total_days: Mapped[int] = mapped_column(Integer, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    workouts: Mapped[list["Workout"]] = relationship(back_populates="marathon", order_by="Workout.day_number")


class Workout(Base):
    """Тренировка конкретного дня марафона: текст + ссылка на видео."""

    __tablename__ = "workouts"
    __table_args__ = (UniqueConstraint("marathon_id", "day_number", name="uq_workout_day"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    marathon_id: Mapped[int] = mapped_column(ForeignKey("marathons.id", ondelete="CASCADE"), index=True)
    day_number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200))
    text: Mapped[str] = mapped_column(Text, default="")
    video_url: Mapped[str | None] = mapped_column(String(500))

    marathon: Mapped[Marathon] = relationship(back_populates="workouts")


class UserProgress(Base):
    """Прогресс пользователя в одном марафоне. Строка живёт вечно => при смене марафона прогресс сохраняется."""

    __tablename__ = "user_progress"
    __table_args__ = (UniqueConstraint("user_id", "marathon_id", name="uq_progress_user_marathon"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    marathon_id: Mapped[int] = mapped_column(ForeignKey("marathons.id", ondelete="CASCADE"))
    current_day: Mapped[int] = mapped_column(Integer, default=1)       # день, который нужно выполнить следующим
    completed_days: Mapped[int] = mapped_column(Integer, default=0)
    is_finished: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[User] = relationship(back_populates="progress")
    marathon: Mapped[Marathon] = relationship()


class WorkoutLog(Base):
    """Журнал выполненных тренировок. Уникален по (пользователь, марафон, день) — повторный клик не дублирует."""

    __tablename__ = "workout_logs"
    __table_args__ = (UniqueConstraint("user_id", "marathon_id", "day_number", name="uq_log_user_day"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    marathon_id: Mapped[int] = mapped_column(ForeignKey("marathons.id", ondelete="CASCADE"))
    day_number: Mapped[int] = mapped_column(Integer)
    feedback: Mapped[str | None] = mapped_column(String(16))  # easy / normal / hard
    completed_on: Mapped[dt.date] = mapped_column(Date)
    completed_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Achievement(Base):
    """Справочник ачивок."""

    __tablename__ = "achievements"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    icon: Mapped[str] = mapped_column(String(8), default="🏆")
    title: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(String(255))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class UserAchievement(Base):
    """Полученные пользователем ачивки."""

    __tablename__ = "user_achievements"
    __table_args__ = (UniqueConstraint("user_id", "achievement_id", name="uq_user_achievement"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    achievement_id: Mapped[int] = mapped_column(ForeignKey("achievements.id", ondelete="CASCADE"))
    earned_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(back_populates="achievements")
    achievement: Mapped[Achievement] = relationship()
