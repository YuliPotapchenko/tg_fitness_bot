"""Тексты экранов бота (HTML-разметка). Чистые функции без обращений к БД и Telegram."""
import datetime as dt
from html import escape

from app.db.models import Achievement, Marathon, User, UserProgress, Workout
from app.services import progress as svc


def progress_bar(done: int, total: int, width: int = 10) -> str:
    if total <= 0:
        return "░" * width
    filled = round(width * done / total)
    return "▓" * filled + "░" * (width - filled)


def percent(done: int, total: int) -> int:
    return round(100 * done / total) if total else 0


def _date(d: dt.date) -> str:
    return d.strftime("%d.%m.%Y")


def name_of(user: User) -> str:
    return escape(user.first_name or "атлет")


# ---------- доступ ----------

NO_ACCESS_UNKNOWN = (
    "🔒 <b>Доступ только по подписке</b>\n\n"
    "Оформите подписку на сайте — после оплаты вы получите персональную ссылку для входа в бота."
)


def no_access_expired(user: User) -> str:
    return (
        f"⏳ <b>{name_of(user)}, срок подписки истёк</b> ({_date(user.subscription_end)}).\n\n"
        "Ваш прогресс сохранён — продлите подписку, и вы продолжите с того же места."
    )


def link_invalid() -> str:
    return (
        "🤔 <b>Ссылка недействительна</b>\n\n"
        "Откройте ссылку из письма после оплаты ещё раз. Если не получается — напишите в поддержку."
    )


def link_used() -> str:
    return "🔐 Эта ссылка уже привязана к другому аккаунту Telegram. Если это ошибка — напишите в поддержку."


# ---------- онбординг ----------

def onboarding(user: User) -> str:
    return (
        f"🎉 <b>Добро пожаловать, {name_of(user)}!</b>\n\n"
        f"Подписка активна до <b>{_date(user.subscription_end)}</b>.\n\n"
        "Как всё устроено:\n"
        "1️⃣ Выберите марафон в каталоге\n"
        "2️⃣ Каждый день открывается одна тренировка\n"
        "3️⃣ Нажмите «Я выполнил» — и завтра откроется следующая\n"
        "4️⃣ Тренируйтесь без пропусков, копите серию 🔥 и получайте достижения 🏆\n\n"
        "Готовы начать?"
    )


# ---------- главное меню ----------

def main_menu(user: User, marathon: Marathon | None, progress: UserProgress | None) -> str:
    left = svc.days_left(user)
    lines = [
        f"<b>Привет, {name_of(user)}!</b> 👋",
        "",
        f"💳 Подписка: ✅ активна до <b>{_date(user.subscription_end)}</b> (осталось {left} дн.)",
    ]
    if marathon and progress:
        lines += [
            f"🏋️ Марафон: <b>{escape(marathon.title)}</b>",
            f"{progress_bar(progress.completed_days, marathon.total_days)} "
            f"<b>{percent(progress.completed_days, marathon.total_days)}%</b>",
        ]
        if progress.is_finished:
            lines.append("🏁 Марафон завершён — выберите следующий в каталоге!")
        else:
            lines.append(f"📅 День {progress.current_day} из {marathon.total_days}")
    else:
        lines.append("🏋️ Марафон: <i>не выбран</i> — загляните в каталог")
    lines.append(f"🔥 Серия: <b>{svc.effective_streak(user)}</b> дн. подряд")
    return "\n".join(lines)


# ---------- тренировка ----------

def workout(marathon: Marathon, workout_: Workout) -> str:
    return (
        f"🏋️ <b>{escape(marathon.title)} · День {workout_.day_number} из {marathon.total_days}</b>\n"
        f"<b>{escape(workout_.title)}</b>\n\n"
        f"{escape(workout_.text)}\n\n"
        "Посмотрите видео, выполните тренировку и нажмите «Я выполнил» 👇"
    )


def workout_missing(marathon: Marathon, day: int) -> str:
    return f"🛠 Тренировка дня {day} марафона «{escape(marathon.title)}» ещё готовится. Загляните чуть позже!"


def workout_done_today() -> str:
    return (
        "✅ <b>Сегодняшняя тренировка уже выполнена!</b>\n\n"
        "Следующая откроется <b>завтра</b>. Отдыхайте и восстанавливайтесь 💤"
    )


def marathon_finished_screen(marathon: Marathon) -> str:
    return (
        f"🏁 <b>Марафон «{escape(marathon.title)}» пройден!</b>\n\n"
        "Вы молодец! Выберите следующую программу в каталоге — прогресс этого марафона сохранён."
    )


# ---------- завершение ----------

def completed(day: int, marathon_finished: bool, new_ach: list[Achievement]) -> str:
    text = f"🎉 <b>День {day} выполнен!</b>\n\n"
    if new_ach:
        text += "🏆 <b>Новые достижения:</b>\n" + "\n".join(f"{a.icon} {escape(a.title)}" for a in new_ach) + "\n\n"
    if marathon_finished:
        text += "🏁 Вы прошли весь марафон!\n\n"
    text += "Как вам тренировка?"
    return text


def feedback_thanks(day: int, marathon_finished: bool, label: str) -> str:
    text = f"Спасибо за оценку: <b>{label}</b> 🙌\n\n"
    if marathon_finished:
        text += "🏁 Марафон завершён! Выберите следующую программу в каталоге."
    else:
        text += "🔓 <b>Следующая тренировка откроется завтра.</b> Не забудьте вернуться — серия не должна прерваться 🔥"
    return text


# ---------- каталог ----------

def catalog() -> str:
    return (
        "📚 <b>Каталог марафонов</b>\n\n"
        "Выберите программу. Прогресс каждого марафона сохраняется — "
        "можно переключаться и возвращаться с того же дня."
    )


def marathon_card(marathon: Marathon, progress: UserProgress | None, is_current: bool) -> str:
    done = progress.completed_days if progress else 0
    text = (
        f"<b>{escape(marathon.title)}</b>\n"
        f"📅 Длительность: {marathon.total_days} дн.\n\n"
        f"{escape(marathon.description)}\n\n"
        f"{progress_bar(done, marathon.total_days)} {percent(done, marathon.total_days)}%"
    )
    if progress and progress.is_finished:
        text += "\n🏁 Пройден"
    elif done:
        text += f"\nВаш прогресс: {done} из {marathon.total_days}"
    if is_current:
        text += "\n▶️ Сейчас активен"
    return text


# ---------- достижения ----------

def achievements(stats: svc.Stats) -> str:
    lines = [
        "🏆 <b>Мои достижения</b>",
        "",
        f"💪 Тренировок выполнено: <b>{stats.total_workouts}</b>",
        f"🏁 Марафонов пройдено: <b>{stats.finished_marathons}</b>",
        f"🔥 Текущая серия: <b>{stats.streak}</b> дн.",
        f"⭐ Рекордная серия: <b>{stats.best_streak}</b> дн.",
        "",
        "<b>Ачивки:</b>",
    ]
    for ach, got in stats.achievements:
        if got:
            lines.append(f"{ach.icon} <b>{escape(ach.title)}</b> — {escape(ach.description)}")
        else:
            lines.append(f"🔒 {escape(ach.title)} — {escape(ach.description)}")
    return "\n".join(lines)


# ---------- настройки ----------

def settings_screen(user: User) -> str:
    push = f"включены, в <b>{user.push_time.strftime('%H:%M')}</b>" if user.push_enabled else "выключены"
    return (
        "⚙️ <b>Настройки</b>\n\n"
        f"💳 Тариф: <b>{escape(user.tariff)}</b>\n"
        f"📆 Действует до: <b>{_date(user.subscription_end)}</b> (осталось {svc.days_left(user)} дн.)\n"
        f"🔔 Напоминания: {push}"
    )


def push_time_screen() -> str:
    return "⏰ <b>Во сколько присылать напоминание?</b>\n\nВремя указано по часовому поясу проекта (Москва)."


def account_conflict() -> str:
    return (
        "🔐 Этот Telegram-аккаунт уже привязан к другой подписке.\n"
        "Если вы покупали подписку повторно с другого email — напишите в поддержку, мы объединим доступы."
    )
