# panels.py
# Панели и клавиатуры для каждой должности

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from config import RANKS, PERM_GLOBAN, PERM_RAZBAN, PERM_STATS, PERM_MAILING, PERM_ASSIGN


def kb(rows: list) -> InlineKeyboardMarkup:
    """Быстрое создание клавиатуры из списка списков кнопок."""
    return InlineKeyboardMarkup(rows)


def btn(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text, callback_data=data)


# ══════════════════════════════════════════
#           ГЛАВНАЯ ПАНЕЛЬ (по уровню)
# ══════════════════════════════════════════

def get_panel(level: int, rank_name: str) -> tuple[str, InlineKeyboardMarkup]:
    """
    Возвращает (текст_заголовка, клавиатура) в зависимости от уровня должности.
    level: числовой уровень из RANKS (1=Владелец, 16=Мл.Саппорт)
    """

    header = f"🎛 <b>Панель | {rank_name}</b>\n\nВыберите действие:"

    # ── ВЛАДЕЛЕЦ (1) ──
    if level == 1:
        rows = [
            [btn("📊 Статистика",        "p_stats"),
             btn("👥 Состав",             "p_staff_list")],
            [btn("📨 Рассылка",           "p_mailing"),
             btn("🗂 База мошенников",    "p_base_info")],
            [btn("👑 Выдать должность",   "p_assign_rank"),
             btn("🗑 Снять должность",    "p_remove_rank")],
            [btn("🔨 Заблокировать",      "p_ban"),
             btn("🔓 Разблокировать",     "p_unban")],
            [btn("📋 Список заблок.",     "p_ban_list"),
             btn("🔍 Найти юзера",        "p_find_user")],
            [btn("📜 История рассылок",   "p_mailing_history")],
        ]

    # ── ЗАМЕСТИТЕЛЬ ВЛАДЕЛЬЦА (2) ──
    elif level == 2:
        rows = [
            [btn("📊 Статистика",        "p_stats"),
             btn("👥 Состав",             "p_staff_list")],
            [btn("📨 Рассылка",           "p_mailing"),
             btn("🗂 База мошенников",    "p_base_info")],
            [btn("👑 Выдать должность",   "p_assign_rank"),
             btn("🗑 Снять должность",    "p_remove_rank")],
            [btn("🔨 Заблокировать",      "p_ban"),
             btn("🔓 Разблокировать",     "p_unban")],
            [btn("📋 Список заблок.",     "p_ban_list"),
             btn("🔍 Найти юзера",        "p_find_user")],
        ]

    # ── ПОМОЩНИК ВЛАДЕЛЬЦА (3) ──
    elif level == 3:
        rows = [
            [btn("📊 Статистика",        "p_stats"),
             btn("👥 Состав",             "p_staff_list")],
            [btn("📨 Рассылка",           "p_mailing"),
             btn("🗂 База мошенников",    "p_base_info")],
            [btn("👑 Выдать должность",   "p_assign_rank"),
             btn("🗑 Снять должность",    "p_remove_rank")],
            [btn("🔨 Заблокировать",      "p_ban"),
             btn("🔓 Разблокировать",     "p_unban")],
            [btn("🔍 Найти юзера",        "p_find_user")],
        ]

    # ── ПОМОЩНИК ЗАМЕСТИТЕЛЯ (4) ──
    elif level == 4:
        rows = [
            [btn("📊 Статистика",        "p_stats"),
             btn("👥 Состав",             "p_staff_list")],
            [btn("📨 Рассылка",           "p_mailing"),
             btn("🗂 База мошенников",    "p_base_info")],
            [btn("👑 Выдать должность",   "p_assign_rank"),
             btn("🗑 Снять должность",    "p_remove_rank")],
            [btn("🔨 Заблокировать",      "p_ban"),
             btn("🔓 Разблокировать",     "p_unban")],
        ]

    # ── КУРАТОР АДМИНИСТРАЦИИ (5) ──
    elif level == 5:
        rows = [
            [btn("📊 Статистика",        "p_stats"),
             btn("👥 Состав",             "p_staff_list")],
            [btn("📨 Рассылка",           "p_mailing"),
             btn("🗂 База мошенников",    "p_base_info")],
            [btn("👑 Выдать должность",   "p_assign_rank"),
             btn("🗑 Снять должность",    "p_remove_rank")],
            [btn("🔨 Заблокировать",      "p_ban"),
             btn("🔓 Разблокировать",     "p_unban")],
        ]

    # ── СТ. АДМИН / АДМИН / МЛ. АДМИН (6-8) ──
    elif level in (6, 7, 8):
        rows = [
            [btn("📊 Статистика",        "p_stats"),
             btn("👥 Состав",             "p_staff_list")],
            [btn("🗂 База мошенников",    "p_base_info")],
            [btn("👑 Выдать должность",   "p_assign_rank"),
             btn("🗑 Снять должность",    "p_remove_rank")],
            [btn("🔨 Заблокировать",      "p_ban"),
             btn("🔓 Разблокировать",     "p_unban")],
        ]

    # ── КУРАТОР МОДЕРАЦИИ (9) ──
    elif level == 9:
        rows = [
            [btn("📊 Статистика",        "p_stats"),
             btn("👥 Состав",             "p_staff_list")],
            [btn("🗂 База мошенников",    "p_base_info")],
            [btn("👑 Выдать должность",   "p_assign_rank"),
             btn("🗑 Снять должность",    "p_remove_rank")],
        ]

    # ── СТ. МОДЕР / МОДЕР / МЛ. МОДЕР (10-12) ──
    elif level in (10, 11, 12):
        rows = [
            [btn("📊 Статистика",        "p_stats"),
             btn("👥 Состав",             "p_staff_list")],
            [btn("🗂 База мошенников",    "p_base_info")],
            [btn("ℹ️ Как добавить в базу","p_globan_help")],
        ]

    # ── КУРАТОР САППОРТОВ (13) ──
    elif level == 13:
        rows = [
            [btn("📊 Статистика",        "p_stats"),
             btn("👥 Состав",             "p_staff_list")],
            [btn("🗂 База мошенников",    "p_base_info")],
            [btn("👑 Выдать должность",   "p_assign_rank"),
             btn("🗑 Снять должность",    "p_remove_rank")],
        ]

    # ── СТ. САППОРТ / САППОРТ / МЛ. САППОРТ (14-16) ──
    else:
        rows = [
            [btn("📊 Статистика",        "p_stats")],
            [btn("🗂 База мошенников",    "p_base_info")],
            [btn("ℹ️ Команды бота",       "p_help")],
        ]

    return header, kb(rows)


# ══════════════════════════════════════════
#       КЛАВИАТУРА ВЫБОРА ДОЛЖНОСТИ
# ══════════════════════════════════════════

def get_rank_select_keyboard(assigner_level: int, action: str = 'assign') -> InlineKeyboardMarkup:
    """
    Показывает только те должности, которые assigner может выдать/снять.
    Нельзя выдать должность равную или выше своей.
    action: 'assign' или 'remove'
    """
    prefix = 'do_assign_' if action == 'assign' else 'do_remove_'
    rows = []

    for rank_key, info in RANKS.items():
        lvl = info['level']
        # Можно выдавать только должности НИЖЕ своей
        if lvl > assigner_level:
            rows.append([InlineKeyboardButton(
                info['name'],
                callback_data=f"{prefix}{rank_key}"
            )])

    rows.append([btn("🔙 Назад", "p_back")])
    return kb(rows)


# ══════════════════════════════════════════
#       КНОПКА НАЗАД
# ══════════════════════════════════════════

def kb_back() -> InlineKeyboardMarkup:
    return kb([[btn("🔙 Назад", "p_back")]])
