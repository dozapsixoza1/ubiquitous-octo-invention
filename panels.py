# panels.py
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from config import RANKS


def btn(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text, callback_data=data)


def kb(rows: list) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(rows)


def kb_back() -> InlineKeyboardMarkup:
    return kb([[btn("🔙 Назад в панель", "p_back")]])


# ══════════════════════════════════════════
#           ГЛАВНАЯ ПАНЕЛЬ ПО УРОВНЮ
# ══════════════════════════════════════════

def get_panel(level: int, rank_name: str) -> tuple[str, InlineKeyboardMarkup]:
    header = f"🎛 <b>Панель | {rank_name}</b>\n\nВыберите действие:"

    # Базовые кнопки есть у всех сотрудников
    base = [
        [btn("📊 Статистика", "p_stats"),
         btn("👥 Состав",     "p_staff_list")],
        [btn("🗂 База мошенников", "p_base_info")],
    ]

    moder_btns = [
        [btn("ℹ️ Как добавить в базу", "p_globan_help")],
    ]

    assign_btns = [
        [btn("👑 Выдать должность", "p_assign_rank"),
         btn("🗑 Снять должность",  "p_remove_rank")],
    ]

    ban_btns = [
        [btn("🔨 Заблокировать",  "p_ban"),
         btn("🔓 Разблокировать", "p_unban")],
    ]

    mailing_btns = [
        [btn("📨 Рассылка",          "p_mailing"),
         btn("📜 История рассылок",  "p_mailing_history")],
    ]

    find_btn = [[btn("🔍 Найти юзера", "p_find_user"),
                 btn("📋 Список заблок.", "p_ban_list")]]

    rows = list(base)

    # Уровни 1-4: Владелец, Зам, Помощник Владельца, Помощник Зама
    if level <= 4:
        rows += mailing_btns + assign_btns + ban_btns + find_btn

    # Уровни 5-8: Кураторы Адм, Ст.Адм, Адм, Мл.Адм
    elif level <= 8:
        rows += assign_btns + ban_btns

    # Уровень 9: Куратор Модерации
    elif level == 9:
        rows += assign_btns

    # Уровни 10-12: Ст.Модер, Модер, Мл.Модер
    elif level <= 12:
        rows += moder_btns

    # Уровень 13: Куратор Саппортов
    elif level == 13:
        rows += assign_btns

    # Уровни 14-16: Саппорты — только базовые кнопки

    return header, kb(rows)


# ══════════════════════════════════════════
#       ВЫБОР ДОЛЖНОСТИ ДЛЯ ВЫДАЧИ
# ══════════════════════════════════════════

def get_rank_keyboard(assigner_level: int, action: str, target_id: int) -> InlineKeyboardMarkup:
    """
    action: 'assign' или 'remove'
    target_id встроен в callback_data чтобы не терять контекст
    """
    prefix = f"do_assign_{target_id}_" if action == 'assign' else f"do_remove_{target_id}_"
    rows = []
    for rank_key, info in RANKS.items():
        lvl = info['level']
        if lvl > assigner_level:  # можно выдавать только ниже себя
            rows.append([InlineKeyboardButton(
                info['name'],
                callback_data=f"{prefix}{rank_key}"
            )])
    rows.append([btn("🔙 Назад в панель", "p_back")])
    return kb(rows)
