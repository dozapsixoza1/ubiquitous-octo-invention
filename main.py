# main.py
import logging
import asyncio
import math
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.error import TelegramError
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)
from telegram.constants import ChatMemberStatus

from config import Config
from database import Database

# ───────────── ЛОГИРОВАНИЕ ─────────────
logging.basicConfig(
    format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(Config.LOGS_DIR / 'bot.log', encoding='utf-8'),
    ]
)
logger = logging.getLogger(__name__)

db = Database()

PAGE_SIZE = 10  # записей на странице команды "база"

# ══════════════════════════════════════════
#               ПРОВЕРКА ПРАВ
# ══════════════════════════════════════════

async def is_moder_or_admin(bot: Bot, chat_id: int, user_id: int) -> bool:
    """Проверяет, является ли юзер модером/админом группы ИЛИ он в ADMIN_IDS."""
    if user_id in Config.ADMIN_IDS:
        return True
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in (
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER
        )
    except TelegramError:
        return False


# ══════════════════════════════════════════
#               ФОРМАТИРОВАНИЕ
# ══════════════════════════════════════════

def fmt_scammer_full(s: dict) -> str:
    """Полная карточка мошенника."""
    un = f"@{s['scammer_username']}" if s.get('scammer_username') else "—"
    added = str(s.get('created_at', ''))[:10]
    return (
        f"🚨 <b>НАЙДЕН В БАЗЕ FLY BASE</b>\n\n"
        f"<b>ID:</b> <code>{s['scammer_id']}</code>\n"
        f"<b>Username:</b> {un}\n"
        f"<b>Имя:</b> {s.get('scammer_name') or '—'}\n\n"
        f"<b>Причина:</b>\n{s['reason']}\n\n"
        f"<b>Доказательства:</b>\n{s['proofs']}\n\n"
        f"<b>Добавлено:</b> {added}\n"
        f"<b>Запись:</b> #{s['id']}\n\n"
        f"⚠️ <i>Будьте осторожны!</i>"
    )


def kb_base_pages(page: int, total_pages: int) -> InlineKeyboardMarkup:
    """Кнопки пагинации для команды база."""
    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton("◀️ Назад", callback_data=f"base_page_{page - 1}"))
    buttons.append(InlineKeyboardButton(f"{page + 1} / {total_pages}", callback_data="base_noop"))
    if page < total_pages - 1:
        buttons.append(InlineKeyboardButton("Вперёд ▶️", callback_data=f"base_page_{page + 1}"))
    return InlineKeyboardMarkup([buttons])


def build_base_text(scammers: list, page: int) -> tuple[str, int]:
    """Возвращает текст страницы и total_pages."""
    total = len(scammers)
    total_pages = math.ceil(total / PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))

    start = page * PAGE_SIZE
    chunk = scammers[start:start + PAGE_SIZE]

    lines = [
        f"🗂 <b>БАЗА {Config.BOT_NAME}</b>\n"
        f"Всего записей: <b>{total}</b> | Страница {page + 1}/{total_pages}\n"
    ]
    for i, s in enumerate(chunk, start + 1):
        un = f"@{s['scammer_username']}" if s.get('scammer_username') else s['scammer_id']
        reason = str(s.get('reason', ''))
        short = reason[:55] + "…" if len(reason) > 55 else reason
        lines.append(f"<b>{i}.</b> <code>{s['scammer_id']}</code> {un}\n    └ {short}")

    lines.append(f"\n💡 Подробнее: <code>чек @username</code>")
    return "\n".join(lines), total_pages


# ══════════════════════════════════════════
#           /start  /help
# ══════════════════════════════════════════

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.add_user(user.id, user.username, user.first_name, user.last_name)

    if db.is_banned(user.id):
        await update.message.reply_text("🚫 Вы заблокированы.")
        return

    await update.message.reply_text(
        f"👋 <b>Добро пожаловать в {Config.BOT_NAME}!</b>\n\n"
        "База мошенников — проверяй людей перед сделкой.\n\n"
        "<b>Команды:</b>\n"
        "• <code>чек @username</code> — проверить человека\n"
        "• <code>чек 123456789</code> — проверить по ID\n"
        "• <code>база</code> — полный список базы\n\n"
        "<b>Как добавить мошенника?</b>\n"
        "Напишите заявку в тему чата со скриншотами.\n"
        "Модератор добавит командой <code>глобан</code>.\n\n"
        "<i>🛡 Будьте осторожны в сети!</i>",
        parse_mode='HTML'
    )
    db.add_stat('start', user.id)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    is_mod = await is_moder_or_admin(context.bot, update.effective_chat.id, user.id)

    text = (
        "📖 <b>Команды для всех:</b>\n\n"
        "<code>чек @username</code> — проверить по username\n"
        "<code>чек 123456789</code> — проверить по ID\n"
        "<code>база</code> — список всех мошенников\n"
    )

    if is_mod:
        text += (
            "\n\n🛡 <b>Команды модераторов:</b>\n\n"
            "<code>глобан @user причина | доказательства</code>\n"
            "— добавить в базу\n\n"
            "<code>разбан @user</code>\n"
            "— удалить из базы\n\n"
            "<code>стата</code> — статистика базы"
        )

    await update.message.reply_text(text, parse_mode='HTML')


# ══════════════════════════════════════════
#           ЧЕК — ПРОВЕРКА ЧЕЛОВЕКА
# ══════════════════════════════════════════

async def handle_chek(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Текстовая команда: чек @username  или  чек 123456789
    Слеш-команда:     /chek @username или  /chek 123456789
    """
    user = update.effective_user
    db.add_user(user.id, user.username, user.first_name, user.last_name)

    if db.is_banned(user.id):
        return

    text = update.message.text.strip()
    # Убираем первое слово (чек / /chek) и берём остаток
    parts = text.split(None, 1)
    query = parts[1].strip() if len(parts) > 1 else ""

    # Для /chek с аргументами через context.args
    if not query and context.args:
        query = context.args[0].strip()

    if not query:
        await update.message.reply_text(
            "❌ Укажите кого проверить.\n"
            "Пример: <code>чек @username</code> или <code>чек 123456789</code>",
            parse_mode='HTML'
        )
        return

    scammer = db.get_scammer(query)
    db.add_stat('search', user.id, query)

    if scammer:
        await update.message.reply_text(fmt_scammer_full(scammer), parse_mode='HTML')
        return

    # Полнотекстовый поиск
    results = db.search_scammers(query)
    if results:
        lines = [f"🔍 <b>Точного совпадения нет, похожие ({len(results)}):</b>\n"]
        for i, s in enumerate(results[:5], 1):
            un = f"@{s['scammer_username']}" if s.get('scammer_username') else s['scammer_id']
            lines.append(f"{i}. {un} — {str(s.get('reason',''))[:50]}…")
        lines.append("\nУточните запрос для точного результата.")
        await update.message.reply_text("\n".join(lines), parse_mode='HTML')
    else:
        await update.message.reply_text(
            f"✅ <b>Чисто</b>\n\n"
            f"<code>{query}</code> — в базе не найден.\n\n"
            f"<i>Если знаете о мошенничестве — напишите заявку в тему чата.</i>",
            parse_mode='HTML'
        )


# ══════════════════════════════════════════
#           ГЛОБАН — ДОБАВЛЕНИЕ В БАЗУ
# ══════════════════════════════════════════

async def handle_globan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Только для модераторов/админов группы.
    Формат: глобан @username/ID причина | доказательства
    Пример: глобан @scam123 кинул на 5к | скрины: http://...
    """
    user = update.effective_user
    chat_id = update.effective_chat.id

    if not await is_moder_or_admin(context.bot, chat_id, user.id):
        await update.message.reply_text("❌ Только модераторы могут добавлять в базу.")
        return

    text = update.message.text.strip()
    body = text[len("глобан"):].strip()

    if not body:
        await update.message.reply_text(
            "❌ Неверный формат.\n\n"
            "Используйте:\n"
            "<code>глобан @username причина | доказательства</code>\n\n"
            "Пример:\n"
            "<code>глобан @scammer кинул на деньги | скрины: https://...</code>",
            parse_mode='HTML'
        )
        return

    parts = body.split(None, 1)
    if len(parts) < 2:
        await update.message.reply_text(
            "❌ Укажите причину.\n"
            "Формат: <code>глобан @username причина | доказательства</code>",
            parse_mode='HTML'
        )
        return

    target = parts[0].strip()
    rest   = parts[1].strip()

    # Разделяем причину и доказательства по "|"
    if '|' in rest:
        reason, proofs = [x.strip() for x in rest.split('|', 1)]
    else:
        reason = rest
        proofs = "Не указаны (см. скрины в заявке)"

    if not reason:
        await update.message.reply_text("❌ Причина не может быть пустой.")
        return

    # Уже в базе?
    existing = db.get_scammer(target)
    if existing:
        await update.message.reply_text(
            f"⚠️ <b>{target}</b> уже есть в базе (запись #{existing['id']}).\n\n"
            f"Причина: {existing['reason']}",
            parse_mode='HTML'
        )
        return

    username = target.lstrip('@')
    scammer_db_id = db.add_scammer(
        scammer_id=target,
        scammer_username=username,
        scammer_name=target,
        reason=reason,
        proofs=proofs,
        added_by=user.id
    )
    # Сразу одобряем — модер уже всё проверил
    db.update_scammer_status(scammer_db_id, 'approved', user.id)
    db.add_stat('globan', user.id, target)

    mod_name = f"@{user.username}" if user.username else user.first_name

    await update.message.reply_text(
        f"✅ <b>{target} добавлен в базу FLY BASE</b>\n\n"
        f"<b>Причина:</b> {reason}\n"
        f"<b>Доказательства:</b> {proofs}\n\n"
        f"<b>Добавил:</b> {mod_name}\n"
        f"<b>Запись №:</b> #{scammer_db_id}",
        parse_mode='HTML'
    )


# ══════════════════════════════════════════
#           РАЗБАН — УДАЛЕНИЕ ИЗ БАЗЫ
# ══════════════════════════════════════════

async def handle_razban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Формат: разбан @username или разбан 123456789"""
    user = update.effective_user
    chat_id = update.effective_chat.id

    if not await is_moder_or_admin(context.bot, chat_id, user.id):
        await update.message.reply_text("❌ Только модераторы могут удалять из базы.")
        return

    text = update.message.text.strip()
    parts = text.split(None, 1)

    if len(parts) < 2:
        await update.message.reply_text(
            "❌ Укажите кого удалить.\n"
            "Пример: <code>разбан @username</code>",
            parse_mode='HTML'
        )
        return

    target = parts[1].strip()
    scammer = db.get_scammer(target)

    if not scammer:
        await update.message.reply_text(
            f"❌ <code>{target}</code> не найден в базе.",
            parse_mode='HTML'
        )
        return

    db.delete_scammer(scammer['id'])
    mod_name = f"@{user.username}" if user.username else user.first_name

    await update.message.reply_text(
        f"🗑 <b>{target} удалён из базы</b>\n\n"
        f"Запись #{scammer['id']} удалена.\n"
        f"Удалил: {mod_name}",
        parse_mode='HTML'
    )


# ══════════════════════════════════════════
#           БАЗА — СПИСОК ВСЕХ
# ══════════════════════════════════════════

async def handle_baza(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.add_user(user.id, user.username, user.first_name, user.last_name)

    if db.is_banned(user.id):
        return

    scammers = db.get_approved_scammers()

    if not scammers:
        await update.message.reply_text(
            f"📭 <b>База {Config.BOT_NAME} пуста</b>\n\nПока никто не добавлен.",
            parse_mode='HTML'
        )
        return

    text, total_pages = build_base_text(scammers, page=0)
    await update.message.reply_text(
        text,
        parse_mode='HTML',
        reply_markup=kb_base_pages(0, total_pages) if total_pages > 1 else None
    )
    db.add_stat('baza', user.id)


# ══════════════════════════════════════════
#           СТАТА — СТАТИСТИКА
# ══════════════════════════════════════════

async def handle_stata(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id

    if not await is_moder_or_admin(context.bot, chat_id, user.id):
        await update.message.reply_text("❌ Только для модераторов.")
        return

    stats = db.get_stats()
    await update.message.reply_text(
        f"📊 <b>СТАТИСТИКА {Config.BOT_NAME}</b>\n\n"
        f"👥 Пользователей: <b>{stats['total_users']}</b>\n"
        f"🚫 Заблокировано: <b>{stats['banned_users']}</b>\n"
        f"🕐 Активность сегодня: <b>{stats['today_activity']}</b>\n\n"
        f"🚨 Записей в базе: <b>{stats['approved_scammers']}</b>\n"
        f"🔍 Всего проверок: <b>{stats['total_searches']}</b>\n"
        f"🔍 Проверок сегодня: <b>{stats['today_searches']}</b>",
        parse_mode='HTML'
    )


# ══════════════════════════════════════════
#           КНОПКИ ПАГИНАЦИИ
# ══════════════════════════════════════════

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == 'base_noop':
        return

    if query.data.startswith('base_page_'):
        page = int(query.data.split('_')[-1])
        scammers = db.get_approved_scammers()

        if not scammers:
            await query.edit_message_text("📭 База пуста.")
            return

        text, total_pages = build_base_text(scammers, page)
        await query.edit_message_text(
            text,
            parse_mode='HTML',
            reply_markup=kb_base_pages(page, total_pages) if total_pages > 1 else None
        )


# ══════════════════════════════════════════
#           РОУТЕР ТЕКСТОВЫХ СООБЩЕНИЙ
# ══════════════════════════════════════════

async def route_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Роутит сообщения без слеша на нужный обработчик."""
    if not update.message or not update.message.text:
        return

    user = update.effective_user
    db.add_user(user.id, user.username, user.first_name, user.last_name)

    if db.is_banned(user.id):
        return

    lower = update.message.text.strip().lower()

    if lower.startswith('чек'):
        await handle_chek(update, context)
    elif lower.startswith('глобан'):
        await handle_globan(update, context)
    elif lower.startswith('разбан'):
        await handle_razban(update, context)
    elif lower == 'база':
        await handle_baza(update, context)
    elif lower == 'стата':
        await handle_stata(update, context)
    elif lower in ('помощь', 'хелп', 'help'):
        await cmd_help(update, context)


# ══════════════════════════════════════════
#               ЗАПУСК
# ══════════════════════════════════════════

def main():
    Config.validate()

    app = Application.builder().token(Config.BOT_TOKEN).build()

    # Слеш-команды
    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("help",   cmd_help))
    app.add_handler(CommandHandler("chek",   handle_chek))
    app.add_handler(CommandHandler("baza",   handle_baza))
    app.add_handler(CommandHandler("stata",  handle_stata))

    # Кнопки
    app.add_handler(CallbackQueryHandler(button_handler))

    # Текстовые команды без слеша (чек / глобан / разбан / база / стата)
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        route_message
    ))

    logger.info(f"✅ {Config.BOT_NAME} v{Config.BOT_VERSION} запущен!")
    print(f"✅ {Config.BOT_NAME} v{Config.BOT_VERSION} — запущен. Ctrl+C для остановки.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
