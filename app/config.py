"""Конфигурация приложения.

Все настройки читаются из переменных окружения (или из файла .env при локальной разработке).
Один экземпляр `settings` импортируется во всех модулях.
"""
from functools import lru_cache
from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Обязательные ---
    BOT_TOKEN: str = "9184671215:AAGLjq9jUSmbOo1vHf2HoRqUQyh38T9kKyM"
    BOT_USERNAME: str = "denisMarathonBot"
    DATABASE_URL: str = "postgresql://neondb_owner:npg_ZPulUBV4w7zy@ep-square-shadow-baace6yh-pooler.c-8.eu-central-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
    TELEGRAM_WEBHOOK_SECRET: str
    TILDA_SECRET: str

    # --- Необязательные ---
    PUBLIC_URL: str = ""            # свой домен, если не Render
    RENDER_EXTERNAL_URL: str = ""   # Render подставляет сам
    SITE_URL: str = "https://example.tilda.ws"
    TIMEZONE: str = "Europe/Moscow"
    LOG_LEVEL: str = "INFO"
    EMAIL_API_KEY: str = ""
    EMAIL_FROM: str = ""

    @property
    def base_url(self) -> str:
        """Публичный адрес сервиса без завершающего слеша. Пусто => режим polling."""
        return (self.PUBLIC_URL or self.RENDER_EXTERNAL_URL).rstrip("/")

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.TIMEZONE)


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
