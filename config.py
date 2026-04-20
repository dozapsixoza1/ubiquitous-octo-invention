# config.py
import os
from pathlib import Path
from dotenv import load_dotenv

# Загружаем .env файл
load_dotenv()

class Config:
    # ───────────── ТОКЕН БОТА ─────────────
    BOT_TOKEN: str = os.getenv('BOT_TOKEN', '')

    # ───────────── АДМИНИСТРАТОРЫ ─────────────
    # В .env пишите: ADMIN_IDS=123456789,987654321
    ADMIN_IDS: list[int] = [
        int(i) for i in os.getenv('ADMIN_IDS', '').split(',') if i.strip().isdigit()
    ]

    # ───────────── БАЗА ДАННЫХ ─────────────
    # Пример: DATABASE_URL=sqlite:///flybase.db
    DATABASE_URL: str = os.getenv('DATABASE_URL', 'sqlite:///flybase.db')

    # ───────────── НАЗВАНИЕ И ВЕРСИЯ ─────────────
    BOT_NAME: str    = "FLY BASE"
    BOT_VERSION: str = "2.0.0"

    # ───────────── КАНАЛ/ЧАТ (опционально) ─────────────
    # Если указан — бот будет требовать подписку перед использованием
    # Оставьте пустым чтобы отключить
    REQUIRED_CHANNEL: str = os.getenv('REQUIRED_CHANNEL', '')  # пример: @mychannel

    # ───────────── ЛИМИТЫ ─────────────
    MAX_PENDING_PER_USER: int = 3          # максимум активных заявок от одного юзера
    MAILING_SLEEP_SEC: float = 0.05        # пауза между сообщениями рассылки

    # ───────────── ПУТИ ─────────────
    BASE_DIR:  Path = Path(__file__).parent
    MEDIA_DIR: Path = BASE_DIR / 'media'
    LOGS_DIR:  Path = BASE_DIR / 'logs'

    # ───────────── ВАЛИДАЦИЯ ─────────────
    @classmethod
    def validate(cls) -> None:
        errors = []
        if not cls.BOT_TOKEN:
            errors.append("BOT_TOKEN не задан в .env")
        if not cls.ADMIN_IDS:
            errors.append("ADMIN_IDS не заданы в .env")
        if errors:
            raise ValueError("Ошибки конфига:\n" + "\n".join(f"  • {e}" for e in errors))


# Создаём нужные директории
Config.MEDIA_DIR.mkdir(exist_ok=True)
Config.LOGS_DIR.mkdir(exist_ok=True)
