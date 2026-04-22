# config.py
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ══════════════════════════════════════════
#           ИЕРАРХИЯ ДОЛЖНОСТЕЙ
# Чем меньше число — тем выше должность
# ══════════════════════════════════════════
RANKS = {
    'owner':        {'level': 1,  'name': '👑 Владелец'},
    'co_owner':     {'level': 2,  'name': '🔱 Заместитель Владельца'},
    'helper_owner': {'level': 3,  'name': '💎 Помощник Владельца'},
    'helper_co':    {'level': 4,  'name': '🌟 Помощник Заместителя'},
    'curator_admin':{'level': 5,  'name': '⚜️ Куратор Администрации'},
    'sr_admin':     {'level': 6,  'name': '🔥 Старший Администратор'},
    'admin':        {'level': 7,  'name': '⚡ Администратор'},
    'jr_admin':     {'level': 8,  'name': '🌙 Младший Администратор'},
    'curator_moder':{'level': 9,  'name': '🛡 Куратор Модерации'},
    'sr_moder':     {'level': 10, 'name': '🔵 Старший Модератор'},
    'moder':        {'level': 11, 'name': '🟢 Модератор'},
    'jr_moder':     {'level': 12, 'name': '🟡 Младший Модератор'},
    'curator_supp': {'level': 13, 'name': '🎯 Куратор Саппортов'},
    'sr_supp':      {'level': 14, 'name': '🔷 Старший Саппорт'},
    'supp':         {'level': 15, 'name': '🔹 Саппорт'},
    'jr_supp':      {'level': 16, 'name': '⬜ Младший Саппорт'},
}

# Минимальный уровень для каждого действия
# (чем меньше число — тем выше должность)
PERM_GLOBAN   = 12   # до Мл. Модератора включительно
PERM_RAZBAN   = 12
PERM_STATS    = 12
PERM_MAILING  = 5    # от Куратора Администрации и выше
PERM_ASSIGN   = 4    # назначать должности — от Помощника Зама и выше
PERM_PANEL    = 16   # панель есть у всех сотрудников


class Config:
    BOT_TOKEN:  str       = os.getenv('BOT_TOKEN', '')
    ADMIN_IDS:  list[int] = [
        int(i) for i in os.getenv('ADMIN_IDS', '').split(',') if i.strip().isdigit()
    ]
    DATABASE_URL: str = os.getenv('DATABASE_URL', 'sqlite:///data/flybase.db')
    BOT_NAME:     str = "FLY BASE"
    BOT_VERSION:  str = "3.0.0"
    REQUIRED_CHANNEL: str = os.getenv('REQUIRED_CHANNEL', '')
    MAILING_SLEEP_SEC: float = 0.05

    BASE_DIR:  Path = Path(__file__).parent
    MEDIA_DIR: Path = BASE_DIR / 'media'
    LOGS_DIR:  Path = BASE_DIR / 'logs'

    @classmethod
    def validate(cls):
        errors = []
        if not cls.BOT_TOKEN:
            errors.append("BOT_TOKEN не задан в .env")
        if not cls.ADMIN_IDS:
            errors.append("ADMIN_IDS не заданы в .env")
        if errors:
            raise ValueError("Ошибки конфига:\n" + "\n".join(f"  • {e}" for e in errors))


Config.MEDIA_DIR.mkdir(exist_ok=True)
Config.LOGS_DIR.mkdir(exist_ok=True)
