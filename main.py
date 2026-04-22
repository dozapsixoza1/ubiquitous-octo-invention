# main.py
import logging
import asyncio
import math
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)

from config import Config, RANKS, PERM_GLOBAN, PERM_RAZBAN, PERM_STATS, PERM_MAILING, PERM_ASSIGN
from database import Database
from panels import get_panel, get_rank_select_keyboard, kb_back

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
PAGE_SIZE = 10

# ══════════════════════════════════════════
#               ХЕЛПЕРЫ
# ══════════════════════════════════════════

def fmt_scammer(s: dict) -> str:
    un = f"@{s['scammer_username']}" if s.get('scammer_username') else "—"
    return (
        f"🚨 <b>НАЙДЕН В БАЗЕ {Config.BOT_NAME}</b>\n\n"
        f"<b>ID:</b> <code>{s['scammer_id']}</code>\n"
        f"<b>Username:</b> {un}\n"
        f"<b>Имя:</b> {s.get('scammer_name') or '—'}\n\n"
        f"<b>Причина:</b>\n{s['reason']}\n\n"
        f"<b>Доказательства:</b>\n{s['proofs']}\n\n"
        f"<b>Добавлено:</b> {str(s.get('created_at',''))[:10]}\n"
        f"<b>Запись №:</b> #{s['id']}\n\n"
        f"⚠️ <i>Будьте осторожны!</i>"
    )


def build_base_page(scammers: list, page: int) -> tuple[str, int]:
    total = len(scammers)
    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    page = max(0, min(page, total_pages - 1))
    chunk = scammers[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]

    lines = [
        f"🗂 <b>БАЗА {Config.BOT_NAME}</b>\n"
        f"Записей: <b>{total}</b> | Стр. {page+1}/{total_pages}\n"
    ]
    for i, s in enumerate(chunk, page * PAGE_SIZE + 1):
        un = f"@{s['scammer_username']}" if s.get('scammer_username') else s['scammer_id']
        r  = str(s.get('reason', ''))
        lines.append(f"<b>{i}.</b> <code>{s['scammer_id']}</code> {un}\n    └ {r[:55]}{'…' if len(r)>55 else ''}")

    lines.append("\n💡 Подробнее: <code>чек @username</code>")
    return "\n".join(lines), total_pages


def kb_pages(page: int, total: int) -> InlineKeyboardMarkup:
    btns = []
    if page > 0:
        btns.append(InlineKeyboardButton("◀️", callback_data=f"base_page_{page-1}"))
    btns.append(InlineKeyboardButton(f"{page+1}/{total}", callback_data="noop"))
    if page < total - 1:
        btns.append(InlineKeyboardButton("▶️", callback_data=f"base_page_{page+1}"))
    return InlineKeyboardMarkup([btns])


async def open_panel(send_func, user_id: int):
    """Открывает панель нужного уровня."""
    level     = db.get_rank_level(user_id)
    rank_name = db.get_rank_name(user_id)
    text, markup = get_panel(level, rank_name)
    await send_func(text, parse_mode='HTML', reply_markup=markup)


# ══════════════════════════════════════════
#               /start  /panel
# ══════════════════════════════════════════

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.add_user(user.id, user.username, user.first_name, user.last_name)

    if db.is_banned(user.id):
        await update.message.reply_text("🚫 Вы заблокированы.")
        return

    rank_name = db.get_rank_name(user.id)
    level     = db.get_rank_level(user.id)

    # Если сотрудник — сразу открываем панель
    if level <= 16:
        await open_panel(update.message.reply_text, user.id)
        return

    await update.message.reply_text(
        f"👋 <b>Добро пожаловать в {Config.BOT_NAME}!</b>\n\n"
        "Проверяй людей перед сделкой.\n\n"
        "<b>Команды:</b>\n"
        "• <code>чек @username</code> — проверить\n"
        "• <code>база</code> — список мошенников\n\n"
        "<i>🛡 Будьте осторожны в сети!</i>",
        parse_mode='HTML'
    )
    db.add_stat('start', user.id)


async def cmd_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /panel — открывает панель в личке."""
    user = update.effective_user
    db.add_user(user.id, user.username, user.first_name, user.last_name)

    if db.is_banned(user.id):
        await update.message.reply_text("🚫 Вы заблокированы.")
        return

    if db.get_rank_level(user.id) > 16:
        await update.message.reply_text("❌ У вас нет доступа к панели.")
        return

    await open_panel(update.message.reply_text, user.id)


# ══════════════════════════════════════════
#           ОБРАБОТЧИК КНОПОК ПАНЕЛИ
# ══════════════════════════════════════════

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user  = query.from_user
    data  = query.data
    level = db.get_rank_level(user.id)

    async def edit(text, markup=None):
        await query.edit_message_text(text, parse_mode='HTML', reply_markup=markup)

    async def back_to_panel():
        rank_name    = db.get_rank_name(user.id)
        text, markup = get_panel(level, rank_name)
        await edit(text, markup)

    # ── Назад ──
    if data == 'p_back':
        await back_to_panel()
        return

    if data == 'noop':
        return

    # ── Пагинация базы ──
    if data.startswith('base_page_'):
        page     = int(data.split('_')[-1])
        scammers = db.get_approved_scammers()
        if not scammers:
            await edit("📭 База пуста.")
            return
        text, total_pages = build_base_page(scammers, page)
        await edit(text, kb_pages(page, total_pages) if total_pages > 1 else None)
        return

    # ── Статистика ──
    if data == 'p_stats':
        if level > PERM_STATS:
            await query.answer("❌ Нет доступа.", show_alert=True)
            return
        s = db.get_stats()
        await edit(
            f"📊 <b>СТАТИСТИКА {Config.BOT_NAME}</b>\n\n"
            f"👥 Пользователей: <b>{s['total_users']}</b>\n"
            f"🚫 Заблокировано: <b>{s['banned_users']}</b>\n"
            f"👔 Сотрудников: <b>{s['staff_count']}</b>\n"
            f"🕐 Активность сегодня: <b>{s['today_activity']}</b>\n\n"
            f"🚨 Записей в базе: <b>{s['approved_scammers']}</b>\n"
            f"🔍 Всего проверок: <b>{s['total_searches']}</b>\n"
            f"🔍 Проверок сегодня: <b>{s['today_searches']}</b>",
            kb_back()
        )
        return

    # ── Состав ──
    if data == 'p_staff_list':
        staff = db.get_staff()
        if not staff:
            await edit("👥 Состав пуст.", kb_back())
            return

        lines = [f"👥 <b>СОСТАВ {Config.BOT_NAME}</b>\n"]
        # Группируем по должности
        by_rank: dict = {}
        for m in staff:
            r = m.get('rank') or 'none'
            by_rank.setdefault(r, []).append(m)

        for rank_key, info in RANKS.items():
            members = by_rank.get(rank_key, [])
            if members:
                lines.append(f"\n{info['name']}:")
                for m in members:
                    un = f"@{m['username']}" if m.get('username') else f"id:{m['user_id']}"
                    lines.append(f"  • {un}")

        await edit("\n".join(lines), kb_back())
        return

    # ── Инфо о базе ──
    if data == 'p_base_info':
        scammers = db.get_approved_scammers()
        total    = len(scammers)
        if total == 0:
            await edit("📭 <b>База пуста</b>", kb_back())
            return
        text, total_pages = build_base_page(scammers, 0)
        markup = kb_pages(0, total_pages) if total_pages > 1 else kb_back()
        # Добавляем кнопку назад если есть пагинация
        if total_pages > 1:
            rows = markup.inline_keyboard + [[InlineKeyboardButton("🔙 Назад", callback_data="p_back")]]
            markup = InlineKeyboardMarkup(rows)
        await edit(text, markup)
        return

    # ── Помощь по глобану ──
    if data == 'p_globan_help':
        await edit(
            "ℹ️ <b>Как добавить мошенника в базу:</b>\n\n"
            "Пишете в чате:\n"
            "<code>глобан @username причина | доказательства</code>\n\n"
            "Пример:\n"
            "<code>глобан @scammer кинул на деньги | скрины выше</code>\n\n"
            "Чтобы удалить:\n"
            "<code>разбан @username</code>",
            kb_back()
        )
        return

    # ── Справка ──
    if data == 'p_help':
        await edit(
            "ℹ️ <b>Команды бота:</b>\n\n"
            "<code>чек @username</code> — проверить человека\n"
            "<code>база</code> — список мошенников\n"
            "<code>/panel</code> — открыть панель",
            kb_back()
        )
        return

    # ── Рассылка ──
    if data == 'p_mailing':
        if level > PERM_MAILING:
            await query.answer("❌ Нет доступа.", show_alert=True)
            return
        context.user_data['state'] = 'mailing_input'
        await edit(
            "📨 <b>Рассылка</b>\n\nВведите текст (поддерживается HTML):\n\n"
            "Для отмены напишите <code>отмена</code>",
            kb_back()
        )
        return

    # ── История рассылок ──
    if data == 'p_mailing_history':
        if level > 2:
            await query.answer("❌ Нет доступа.", show_alert=True)
            return
        mailings = db.get_mailings(5)
        if not mailings:
            await edit("📬 Рассылок ещё не было.", kb_back())
            return
        lines = ["📬 <b>Последние рассылки:</b>\n"]
        for m in mailings:
            lines.append(
                f"• {str(m['sent_at'])[:16]} — {m['recipients_count']} получателей\n"
                f"  <i>{str(m['message'])[:60]}…</i>"
            )
        await edit("\n\n".join(lines), kb_back())
        return

    # ── Блокировка ──
    if data == 'p_ban':
        if level > 8:
            await query.answer("❌ Нет доступа.", show_alert=True)
            return
        context.user_data['state'] = 'ban_input'
        await edit(
            "🔨 <b>Блокировка пользователя</b>\n\n"
            "Введите ID и причину:\n"
            "<code>123456789 причина</code>\n\n"
            "Для отмены: <code>отмена</code>",
            kb_back()
        )
        return

    # ── Разблокировка ──
    if data == 'p_unban':
        if level > 8:
            await query.answer("❌ Нет доступа.", show_alert=True)
            return
        context.user_data['state'] = 'unban_input'
        await edit(
            "🔓 <b>Разблокировка пользователя</b>\n\n"
            "Введите ID пользователя:\n\n"
            "Для отмены: <code>отмена</code>",
            kb_back()
        )
        return

    # ── Список заблокированных ──
    if data == 'p_ban_list':
        if level > 4:
            await query.answer("❌ Нет доступа.", show_alert=True)
            return
        with db.get_connection() as conn:
            rows = conn.execute(
                'SELECT b.*, u.username FROM ban_list b '
                'LEFT JOIN users u ON b.user_id = u.user_id '
                'ORDER BY b.banned_at DESC LIMIT 20'
            ).fetchall()
        if not rows:
            await edit("📋 Список блокировок пуст.", kb_back())
            return
        lines = ["🔨 <b>Заблокированные пользователи:</b>\n"]
        for r in rows:
            r = dict(r)
            un = f"@{r['username']}" if r.get('username') else f"id:{r['user_id']}"
            lines.append(f"• {un} — {r.get('reason','—')[:50]}")
        await edit("\n".join(lines), kb_back())
        return

    # ── Найти юзера ──
    if data == 'p_find_user':
        if level > 4:
            await query.answer("❌ Нет доступа.", show_alert=True)
            return
        context.user_data['state'] = 'find_user'
        await edit(
            "🔍 <b>Поиск пользователя</b>\n\n"
            "Введите ID или @username:\n\n"
            "Для отмены: <code>отмена</code>",
            kb_back()
        )
        return

    # ══ ВЫДАЧА ДОЛЖНОСТИ ══

    if data == 'p_assign_rank':
        if level > PERM_ASSIGN:
            await query.answer("❌ Нет доступа.", show_alert=True)
            return
        context.user_data['state'] = 'assign_who'
        await edit(
            "👑 <b>Выдача должности</b>\n\n"
            "Введите ID или @username пользователя:\n\n"
            "Для отмены: <code>отмена</code>",
            kb_back()
        )
        return

    if data.startswith('do_assign_'):
        rank_key = data[len('do_assign_'):]
        target_id = context.user_data.get('assign_target_id')
        if not target_id:
            await back_to_panel()
            return

        # Проверяем что нельзя выдать должность выше своей
        new_level = RANKS.get(rank_key, {}).get('level', 999)
        if new_level <= level:
            await query.answer("❌ Нельзя выдать должность выше или равную своей.", show_alert=True)
            return

        db.set_rank(target_id, rank_key, user.id)
        rank_name = RANKS[rank_key]['name']
        target_user = db.get_user(target_id)
        target_un = f"@{target_user['username']}" if target_user and target_user.get('username') else f"id:{target_id}"

        # Уведомляем получателя
        try:
            await context.bot.send_message(
                target_id,
                f"🎉 <b>Поздравляем!</b>\n\n"
                f"Вам выдана должность: <b>{rank_name}</b>\n"
                f"Выдал: @{user.username or user.id}\n\n"
                f"Откройте панель командой /panel",
                parse_mode='HTML'
            )
        except TelegramError:
            pass

        await edit(
            f"✅ <b>Должность выдана</b>\n\n"
            f"Пользователь: {target_un}\n"
            f"Должность: {rank_name}",
            kb_back()
        )
        context.user_data.pop('assign_target_id', None)
        context.user_data.pop('state', None)
        return

    # ══ СНЯТИЕ ДОЛЖНОСТИ ══

    if data == 'p_remove_rank':
        if level > PERM_ASSIGN:
            await query.answer("❌ Нет доступа.", show_alert=True)
            return
        context.user_data['state'] = 'remove_who'
        await edit(
            "🗑 <b>Снятие должности</b>\n\n"
            "Введите ID или @username сотрудника:\n\n"
            "Для отмены: <code>отмена</code>",
            kb_back()
        )
        return

    if data.startswith('do_remove_'):
        rank_key  = data[len('do_remove_'):]
        target_id = context.user_data.get('remove_target_id')
        if not target_id:
            await back_to_panel()
            return

        db.set_rank(target_id, None, user.id)
        target_user = db.get_user(target_id)
        target_un = f"@{target_user['username']}" if target_user and target_user.get('username') else f"id:{target_id}"

        try:
            await context.bot.send_message(
                target_id,
                f"❌ <b>Уведомление</b>\n\nВаша должность была снята.\nОбратитесь к администрации.",
                parse_mode='HTML'
            )
        except TelegramError:
            pass

        await edit(
            f"✅ Должность снята у пользователя {target_un}",
            kb_back()
        )
        context.user_data.pop('remove_target_id', None)
        context.user_data.pop('state', None)
        return

    # ── Подтверждение рассылки ──
    if data == 'mailing_confirm_yes':
        if level > PERM_MAILING:
            return
        text = context.user_data.get('mailing_text', '')
        users = db.get_all_users_not_banned()
        sent  = 0
        for u in users:
            try:
                await context.bot.send_message(
                    u['user_id'],
                    f"📨 <b>РАССЫЛКА | {Config.BOT_NAME}</b>\n\n{text}",
                    parse_mode='HTML'
                )
                sent += 1
                await asyncio.sleep(Config.MAILING_SLEEP_SEC)
            except TelegramError:
                continue
        db.add_mailing(text, user.id, sent)
        context.user_data.pop('mailing_text', None)
        context.user_data.pop('state', None)
        await edit(
            f"✅ Рассылка завершена.\nОтправлено: <b>{sent}</b> из {len(users)}",
            kb_back()
        )
        return

    if data == 'mailing_confirm_no':
        context.user_data.pop('mailing_text', None)
        context.user_data.pop('state', None)
        await back_to_panel()
        return


# ══════════════════════════════════════════
#       ОБРАБОТЧИК ТЕКСТОВЫХ СООБЩЕНИЙ
# ══════════════════════════════════════════

async def route_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user  = update.effective_user
    text  = update.message.text.strip()
    lower = text.lower()
    state = context.user_data.get('state', '')

    db.add_user(user.id, user.username, user.first_name, user.last_name)

    if db.is_banned(user.id):
        return

    # ── Отмена любого состояния ──
    if lower == 'отмена' and state:
        context.user_data.pop('state', None)
        await update.message.reply_text("❌ Отменено.")
        await open_panel(update.message.reply_text, user.id)
        return

    level = db.get_rank_level(user.id)

    # ════ СОСТОЯНИЯ ПАНЕЛИ ════

    # Ввод текста рассылки
    if state == 'mailing_input':
        if level > PERM_MAILING:
            context.user_data.pop('state', None)
            return
        context.user_data['mailing_text'] = text
        context.user_data['state'] = 'mailing_confirm'
        await update.message.reply_text(
            f"📨 <b>Текст рассылки:</b>\n\n{text}\n\nОтправить?",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Отправить", callback_data="mailing_confirm_yes"),
                InlineKeyboardButton("❌ Отмена",   callback_data="mailing_confirm_no"),
            ]])
        )
        return

    # Бан: ввод ID + причина
    if state == 'ban_input':
        if level > 8:
            context.user_data.pop('state', None)
            return
        parts = text.split(None, 1)
        try:
            ban_id = int(parts[0])
            reason = parts[1] if len(parts) > 1 else 'без причины'
            db.ban_user(ban_id, reason, user.id)
            context.user_data.pop('state', None)
            await update.message.reply_text(
                f"🔨 Пользователь <code>{ban_id}</code> заблокирован.\nПричина: {reason}",
                parse_mode='HTML'
            )
        except (ValueError, IndexError):
            await update.message.reply_text("❌ Формат: <code>ID причина</code>", parse_mode='HTML')
        return

    # Разбан: ввод ID
    if state == 'unban_input':
        if level > 8:
            context.user_data.pop('state', None)
            return
        try:
            uid = int(text)
            db.unban_user(uid)
            context.user_data.pop('state', None)
            await update.message.reply_text(f"🔓 Пользователь <code>{uid}</code> разблокирован.", parse_mode='HTML')
        except ValueError:
            await update.message.reply_text("❌ Введите числовой ID.")
        return

    # Поиск юзера
    if state == 'find_user':
        if level > 4:
            context.user_data.pop('state', None)
            return
        query_str = text.lstrip('@')
        found = None
        try:
            found = db.get_user(int(query_str))
        except ValueError:
            with db.get_connection() as conn:
                row = conn.execute(
                    'SELECT * FROM users WHERE LOWER(username)=LOWER(?)', (query_str,)
                ).fetchone()
                found = dict(row) if row else None

        context.user_data.pop('state', None)
        if found:
            rank_name = db.get_rank_name(found['user_id'])
            un = f"@{found['username']}" if found.get('username') else '—'
            await update.message.reply_text(
                f"👤 <b>Пользователь найден</b>\n\n"
                f"<b>ID:</b> <code>{found['user_id']}</code>\n"
                f"<b>Username:</b> {un}\n"
                f"<b>Имя:</b> {found.get('first_name','—')}\n"
                f"<b>Должность:</b> {rank_name}\n"
                f"<b>Заблокирован:</b> {'да' if found.get('is_banned') else 'нет'}\n"
                f"<b>Регистрация:</b> {str(found.get('registered_date',''))[:10]}",
                parse_mode='HTML'
            )
        else:
            await update.message.reply_text(f"❌ Пользователь <code>{text}</code> не найден.", parse_mode='HTML')
        return

    # Выдача должности: шаг 1 — кто получает
    if state == 'assign_who':
        if level > PERM_ASSIGN:
            context.user_data.pop('state', None)
            return
        query_str = text.lstrip('@')
        target = None
        try:
            target = db.get_user(int(query_str))
        except ValueError:
            with db.get_connection() as conn:
                row = conn.execute(
                    'SELECT * FROM users WHERE LOWER(username)=LOWER(?)', (query_str,)
                ).fetchone()
                target = dict(row) if row else None

        if not target:
            await update.message.reply_text(f"❌ Пользователь <code>{text}</code> не найден.\nПопробуйте ещё раз.", parse_mode='HTML')
            return

        # Проверяем что не пытаемся выдать должность тому кто выше
        target_level = db.get_rank_level(target['user_id'])
        if target_level <= level:
            await update.message.reply_text("❌ Нельзя изменить должность пользователя с равной или более высокой должностью.")
            context.user_data.pop('state', None)
            return

        context.user_data['assign_target_id'] = target['user_id']
        context.user_data['state'] = 'assign_rank_select'
        un = f"@{target['username']}" if target.get('username') else f"id:{target['user_id']}"
        await update.message.reply_text(
            f"👤 Пользователь: <b>{un}</b>\n\nВыберите должность:",
            parse_mode='HTML',
            reply_markup=get_rank_select_keyboard(level, 'assign')
        )
        return

    # Снятие должности: шаг 1 — у кого снимаем
    if state == 'remove_who':
        if level > PERM_ASSIGN:
            context.user_data.pop('state', None)
            return
        query_str = text.lstrip('@')
        target = None
        try:
            target = db.get_user(int(query_str))
        except ValueError:
            with db.get_connection() as conn:
                row = conn.execute(
                    'SELECT * FROM users WHERE LOWER(username)=LOWER(?)', (query_str,)
                ).fetchone()
                target = dict(row) if row else None

        if not target:
            await update.message.reply_text(f"❌ Пользователь не найден.", parse_mode='HTML')
            return

        target_level = db.get_rank_level(target['user_id'])
        if target_level <= level:
            await update.message.reply_text("❌ Нельзя снять должность с пользователя выше или равного по уровню.")
            context.user_data.pop('state', None)
            return

        if not target.get('rank'):
            await update.message.reply_text("❌ У пользователя нет должности.")
            context.user_data.pop('state', None)
            return

        context.user_data['remove_target_id'] = target['user_id']
        un = f"@{target['username']}" if target.get('username') else f"id:{target['user_id']}"
        cur_rank = db.get_rank_name(target['user_id'])

        await update.message.reply_text(
            f"👤 Пользователь: <b>{un}</b>\n"
            f"Текущая должность: <b>{cur_rank}</b>\n\n"
            f"Подтвердить снятие?",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Снять", callback_data=f"do_remove_{target.get('rank','none')}"),
                InlineKeyboardButton("❌ Отмена", callback_data="p_back"),
            ]])
        )
        context.user_data['state'] = 'remove_confirm'
        return

    # ════ КОМАНДЫ В ЧАТЕ ════

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


# ══════════════════════════════════════════
#       КОМАНДЫ ЧЕК / ГЛОБАН / РАЗБАН / БАЗА
# ══════════════════════════════════════════

async def handle_chek(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user  = update.effective_user
    text  = update.message.text.strip()
    parts = text.split(None, 1)
    query = (parts[1].strip() if len(parts) > 1 else
             (context.args[0] if context.args else ''))

    if not query:
        await update.message.reply_text(
            "❌ Укажите кого проверить.\nПример: <code>чек @username</code>",
            parse_mode='HTML'
        )
        return

    scammer = db.get_scammer(query)
    db.add_stat('search', user.id, query)

    if scammer:
        await update.message.reply_text(fmt_scammer(scammer), parse_mode='HTML')
        return

    results = db.search_scammers(query)
    if results:
        lines = [f"🔍 <b>Похожие результаты ({len(results)}):</b>\n"]
        for i, s in enumerate(results[:5], 1):
            un = f"@{s['scammer_username']}" if s.get('scammer_username') else s['scammer_id']
            lines.append(f"{i}. {un} — {str(s.get('reason',''))[:50]}…")
        await update.message.reply_text("\n".join(lines), parse_mode='HTML')
    else:
        await update.message.reply_text(
            f"✅ <b>Чисто</b>\n\n<code>{query}</code> — в базе не найден.",
            parse_mode='HTML'
        )


async def handle_globan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user  = update.effective_user
    level = db.get_rank_level(user.id)

    if level > PERM_GLOBAN:
        await update.message.reply_text("❌ Только модераторы могут добавлять в базу.")
        return

    body  = update.message.text.strip()[len('глобан'):].strip()
    parts = body.split(None, 1)

    if len(parts) < 2:
        await update.message.reply_text(
            "❌ Формат: <code>глобан @username причина | доказательства</code>",
            parse_mode='HTML'
        )
        return

    target = parts[0].strip()
    rest   = parts[1].strip()
    reason, proofs = ([x.strip() for x in rest.split('|', 1)]
                      if '|' in rest else [rest, 'Не указаны'])

    existing = db.get_scammer(target)
    if existing:
        await update.message.reply_text(
            f"⚠️ <b>{target}</b> уже в базе (#{existing['id']}).",
            parse_mode='HTML'
        )
        return

    sid = db.add_scammer(target, target.lstrip('@'), target, reason, proofs, user.id)
    db.update_scammer_status(sid, 'approved', user.id)
    db.add_stat('globan', user.id, target)

    mod = f"@{user.username}" if user.username else user.first_name
    await update.message.reply_text(
        f"✅ <b>{target} добавлен в базу</b>\n\n"
        f"<b>Причина:</b> {reason}\n"
        f"<b>Доказательства:</b> {proofs}\n"
        f"<b>Добавил:</b> {mod} | #{sid}",
        parse_mode='HTML'
    )


async def handle_razban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user  = update.effective_user
    level = db.get_rank_level(user.id)

    if level > PERM_RAZBAN:
        await update.message.reply_text("❌ Только модераторы могут удалять из базы.")
        return

    parts  = update.message.text.strip().split(None, 1)
    target = parts[1].strip() if len(parts) > 1 else ''

    if not target:
        await update.message.reply_text("❌ Укажите кого удалить. Пример: <code>разбан @username</code>", parse_mode='HTML')
        return

    scammer = db.get_scammer(target)
    if not scammer:
        await update.message.reply_text(f"❌ <code>{target}</code> не найден в базе.", parse_mode='HTML')
        return

    db.delete_scammer(scammer['id'])
    mod = f"@{user.username}" if user.username else user.first_name
    await update.message.reply_text(
        f"🗑 <b>{target} удалён из базы</b>\nЗапись #{scammer['id']} | Удалил: {mod}",
        parse_mode='HTML'
    )


async def handle_baza(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    scammers = db.get_approved_scammers()

    if not scammers:
        await update.message.reply_text(f"📭 <b>База {Config.BOT_NAME} пуста</b>", parse_mode='HTML')
        return

    text, total_pages = build_base_page(scammers, 0)
    await update.message.reply_text(
        text, parse_mode='HTML',
        reply_markup=kb_pages(0, total_pages) if total_pages > 1 else None
    )
    db.add_stat('baza', user.id)


async def handle_stata(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user  = update.effective_user
    level = db.get_rank_level(user.id)

    if level > PERM_STATS:
        await update.message.reply_text("❌ Только для модераторов.")
        return

    s = db.get_stats()
    await update.message.reply_text(
        f"📊 <b>СТАТИСТИКА {Config.BOT_NAME}</b>\n\n"
        f"👥 Пользователей: <b>{s['total_users']}</b>\n"
        f"🚫 Заблокировано: <b>{s['banned_users']}</b>\n"
        f"👔 Сотрудников: <b>{s['staff_count']}</b>\n"
        f"🚨 Записей в базе: <b>{s['approved_scammers']}</b>\n"
        f"🔍 Проверок сегодня: <b>{s['today_searches']}</b>",
        parse_mode='HTML'
    )


# ══════════════════════════════════════════
#               ЗАПУСК
# ══════════════════════════════════════════

def main():
    Config.validate()

    app = Application.builder().token(Config.BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("panel", cmd_panel))
    app.add_handler(CommandHandler("chek",  handle_chek))
    app.add_handler(CommandHandler("baza",  handle_baza))
    app.add_handler(CommandHandler("stata", handle_stata))

    app.add_handler(CallbackQueryHandler(button_handler))

    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        route_message
    ))

    logger.info(f"✅ {Config.BOT_NAME} v{Config.BOT_VERSION} запущен!")
    print(f"✅ {Config.BOT_NAME} v{Config.BOT_VERSION} — запущен.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
