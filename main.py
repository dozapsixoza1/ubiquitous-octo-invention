# main.py
import logging
import asyncio
import math

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)

from config import Config, RANKS, PERM_GLOBAN, PERM_RAZBAN, PERM_STATS, PERM_MAILING, PERM_ASSIGN
from database import Database
from panels import get_panel, get_rank_keyboard, kb_back

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
        f"<b>Добавлено:</b> {str(s.get('created_at', ''))[:10]}\n"
        f"<b>Запись №:</b> #{s['id']}\n\n"
        f"⚠️ <i>Будьте осторожны!</i>"
    )


def build_base_page(scammers: list, page: int) -> tuple[str, int]:
    total       = len(scammers)
    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    page        = max(0, min(page, total_pages - 1))
    chunk       = scammers[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]

    lines = [
        f"🗂 <b>БАЗА {Config.BOT_NAME}</b>\n"
        f"Записей: <b>{total}</b> | Стр. {page + 1}/{total_pages}\n"
    ]
    for i, s in enumerate(chunk, page * PAGE_SIZE + 1):
        un = f"@{s['scammer_username']}" if s.get('scammer_username') else s['scammer_id']
        r  = str(s.get('reason', ''))
        lines.append(
            f"<b>{i}.</b> <code>{s['scammer_id']}</code> {un}\n"
            f"    └ {r[:55]}{'…' if len(r) > 55 else ''}"
        )
    lines.append("\n💡 Подробнее: <code>чек @username</code>")
    return "\n".join(lines), total_pages


def kb_pages(page: int, total: int) -> InlineKeyboardMarkup:
    btns = []
    if page > 0:
        btns.append(InlineKeyboardButton("◀️", callback_data=f"base_page_{page - 1}"))
    btns.append(InlineKeyboardButton(f"{page + 1}/{total}", callback_data="noop"))
    if page < total - 1:
        btns.append(InlineKeyboardButton("▶️", callback_data=f"base_page_{page + 1}"))
    rows = [btns, [InlineKeyboardButton("🔙 Назад в панель", callback_data="p_back")]]
    return InlineKeyboardMarkup(rows)


async def send_panel(send_func, user_id: int):
    """Отправляет панель нужного уровня."""
    level     = db.get_rank_level(user_id)
    rank_name = db.get_rank_name(user_id)
    text, markup = get_panel(level, rank_name)
    await send_func(text, parse_mode='HTML', reply_markup=markup)


def find_user_by_query(query: str) -> dict | None:
    """Ищет юзера по ID или username."""
    q = query.lstrip('@')
    try:
        return db.get_user(int(q))
    except ValueError:
        with db.get_connection() as conn:
            row = conn.execute(
                'SELECT * FROM users WHERE LOWER(username)=LOWER(?)', (q,)
            ).fetchone()
            return dict(row) if row else None


# ══════════════════════════════════════════
#               /start  /panel
# ══════════════════════════════════════════

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.add_user(user.id, user.username, user.first_name, user.last_name)

    if db.is_banned(user.id):
        await update.message.reply_text("🚫 Вы заблокированы.")
        return

    # Обычное приветствие для всех — панель только через /panel
    await update.message.reply_text(
        f"👋 <b>Добро пожаловать в {Config.BOT_NAME}!</b>\n\n"
        "Проверяй людей перед сделкой.\n\n"
        "<b>Команды:</b>\n"
        "• <code>чек @username</code> — проверить человека\n"
        "• <code>база</code> — список мошенников\n\n"
        "<i>Если вы сотрудник — используйте /panel</i>",
        parse_mode='HTML'
    )
    db.add_stat('start', user.id)


async def cmd_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Открывает личную панель в личке бота."""
    user = update.effective_user
    db.add_user(user.id, user.username, user.first_name, user.last_name)

    if db.is_banned(user.id):
        await update.message.reply_text("🚫 Вы заблокированы.")
        return

    level = db.get_rank_level(user.id)
    if level > 16:
        await update.message.reply_text(
            "❌ У вас нет доступа к панели.\n"
            "Обратитесь к администрации для получения должности."
        )
        return

    # Сбрасываем состояние при открытии панели
    context.user_data.clear()
    await send_panel(update.message.reply_text, user.id)


# ══════════════════════════════════════════
#           ОБРАБОТЧИК КНОПОК ПАНЕЛИ
# ══════════════════════════════════════════

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user  = query.from_user
    data  = query.data
    level = db.get_rank_level(user.id)

    async def edit(text: str, markup=None):
        """Редактирует сообщение, всегда с текстом."""
        if not text:
            text = "..."
        try:
            await query.edit_message_text(
                text, parse_mode='HTML',
                reply_markup=markup or kb_back()
            )
        except TelegramError as e:
            logger.warning(f"edit_message_text error: {e}")

    async def back():
        rank_name    = db.get_rank_name(user.id)
        text, markup = get_panel(level, rank_name)
        await edit(text, markup)

    # ── Назад ──
    if data == 'p_back':
        context.user_data.pop('state', None)
        await back()
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
        await edit(text, kb_pages(page, total_pages))
        return

    # ════════════════════════════════
    #         КНОПКИ ПАНЕЛИ
    # ════════════════════════════════

    # ── Статистика ──
    if data == 'p_stats':
        if level > PERM_STATS:
            await query.answer("❌ Нет доступа.", show_alert=True)
            return
        s = db.get_stats()
        text = (
            f"📊 <b>СТАТИСТИКА {Config.BOT_NAME}</b>\n\n"
            f"👥 Пользователей: <b>{s['total_users']}</b>\n"
            f"🚫 Заблокировано: <b>{s['banned_users']}</b>\n"
            f"👔 Сотрудников: <b>{s['staff_count']}</b>\n"
            f"🕐 Активность сегодня: <b>{s['today_activity']}</b>\n\n"
            f"🚨 Записей в базе: <b>{s['approved_scammers']}</b>\n"
            f"🔍 Всего проверок: <b>{s['total_searches']}</b>\n"
            f"🔍 Проверок сегодня: <b>{s['today_searches']}</b>"
        )
        await edit(text, kb_back())
        return

    # ── Состав ──
    if data == 'p_staff_list':
        staff = db.get_staff()
        if not staff:
            await edit("👥 <b>Состав пуст.</b>\n\nНикто не назначен.", kb_back())
            return

        lines = [f"👥 <b>СОСТАВ {Config.BOT_NAME}</b>\n"]
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

    # ── База мошенников ──
    if data == 'p_base_info':
        scammers = db.get_approved_scammers()
        if not scammers:
            await edit("📭 <b>База пуста.</b>\n\nМошенников пока нет.", kb_back())
            return
        text, total_pages = build_base_page(scammers, 0)
        await edit(text, kb_pages(0, total_pages))
        return

    # ── Помощь по глобану ──
    if data == 'p_globan_help':
        await edit(
            "ℹ️ <b>Как добавить мошенника в базу:</b>\n\n"
            "Пишете <b>в чате</b>:\n"
            "<code>глобан @username причина | доказательства</code>\n\n"
            "<b>Пример:</b>\n"
            "<code>глобан @scammer кинул на деньги | скрины выше в теме</code>\n\n"
            "Чтобы удалить из базы:\n"
            "<code>разбан @username</code>",
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
            "📨 <b>Рассылка</b>\n\n"
            "Введите текст рассылки (поддерживается HTML).\n"
            "Для отмены напишите <code>отмена</code>",
            kb_back()
        )
        return

    # ── История рассылок ──
    if data == 'p_mailing_history':
        if level > 4:
            await query.answer("❌ Нет доступа.", show_alert=True)
            return
        mailings = db.get_mailings(5)
        if not mailings:
            await edit("📬 <b>Рассылок ещё не было.</b>", kb_back())
            return
        lines = ["📬 <b>Последние рассылки:</b>\n"]
        for m in mailings:
            short = str(m['message'])[:60]
            lines.append(
                f"• {str(m['sent_at'])[:16]} — {m['recipients_count']} получателей\n"
                f"  <i>{short}{'…' if len(str(m['message'])) > 60 else ''}</i>"
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
            "Введите ID пользователя.\n\n"
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
            await edit("📋 <b>Список блокировок пуст.</b>", kb_back())
            return
        lines = ["🔨 <b>Заблокированные:</b>\n"]
        for r in rows:
            r   = dict(r)
            un  = f"@{r['username']}" if r.get('username') else f"id:{r['user_id']}"
            rsn = str(r.get('reason', '—'))[:50]
            lines.append(f"• {un} — {rsn}")
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
            "Введите ID или @username.\n\n"
            "Для отмены: <code>отмена</code>",
            kb_back()
        )
        return

    # ════════════════════════════════
    #       ВЫДАЧА / СНЯТИЕ ДОЛЖНОСТИ
    # ════════════════════════════════

    if data == 'p_assign_rank':
        if level > PERM_ASSIGN:
            await query.answer("❌ Нет доступа.", show_alert=True)
            return
        context.user_data['state'] = 'assign_who'
        await edit(
            "👑 <b>Выдача должности</b>\n\n"
            "Введите ID или @username пользователя.\n\n"
            "Для отмены: <code>отмена</code>",
            kb_back()
        )
        return

    if data == 'p_remove_rank':
        if level > PERM_ASSIGN:
            await query.answer("❌ Нет доступа.", show_alert=True)
            return
        context.user_data['state'] = 'remove_who'
        await edit(
            "🗑 <b>Снятие должности</b>\n\n"
            "Введите ID или @username сотрудника.\n\n"
            "Для отмены: <code>отмена</code>",
            kb_back()
        )
        return

    # ── Нажатие на должность при выдаче: do_assign_{target_id}_{rank_key} ──
    if data.startswith('do_assign_'):
        parts = data[len('do_assign_'):].split('_', 1)
        if len(parts) < 2:
            await back()
            return

        target_id = int(parts[0])
        rank_key  = parts[1]
        new_level = RANKS.get(rank_key, {}).get('level', 999)

        if new_level <= level:
            await query.answer("❌ Нельзя выдать должность выше своей.", show_alert=True)
            return

        db.set_rank(target_id, rank_key, user.id)
        rank_name   = RANKS[rank_key]['name']
        target_user = db.get_user(target_id)
        target_un   = (f"@{target_user['username']}"
                       if target_user and target_user.get('username')
                       else f"id:{target_id}")

        try:
            await context.bot.send_message(
                target_id,
                f"🎉 <b>Поздравляем!</b>\n\n"
                f"Вам выдана должность: <b>{rank_name}</b>\n"
                f"Откройте панель командой /panel",
                parse_mode='HTML'
            )
        except TelegramError:
            pass

        context.user_data.pop('state', None)
        await edit(
            f"✅ <b>Должность выдана!</b>\n\n"
            f"Пользователь: {target_un}\n"
            f"Должность: {rank_name}",
            kb_back()
        )
        return

    # ── Подтверждение снятия: do_remove_{target_id} ──
    if data.startswith('do_remove_'):
        target_id = int(data[len('do_remove_'):])
        target_user = db.get_user(target_id)
        old_rank = db.get_rank_name(target_id)
        target_un = (f"@{target_user['username']}"
                     if target_user and target_user.get('username')
                     else f"id:{target_id}")

        db.set_rank(target_id, None, user.id)

        try:
            await context.bot.send_message(
                target_id,
                "❌ <b>Уведомление</b>\n\nВаша должность была снята.",
                parse_mode='HTML'
            )
        except TelegramError:
            pass

        context.user_data.pop('state', None)
        await edit(
            f"✅ <b>Должность снята</b>\n\n"
            f"Пользователь: {target_un}\n"
            f"Снята должность: {old_rank}",
            kb_back()
        )
        return

    # ── Подтверждение рассылки ──
    if data == 'mailing_yes':
        if level > PERM_MAILING:
            return
        text_to_send = context.user_data.get('mailing_text', '')
        users         = db.get_all_users_not_banned()
        sent          = 0
        for u in users:
            try:
                await context.bot.send_message(
                    u['user_id'],
                    f"📨 <b>РАССЫЛКА | {Config.BOT_NAME}</b>\n\n{text_to_send}",
                    parse_mode='HTML'
                )
                sent += 1
                await asyncio.sleep(Config.MAILING_SLEEP_SEC)
            except TelegramError:
                continue
        db.add_mailing(text_to_send, user.id, sent)
        context.user_data.pop('mailing_text', None)
        context.user_data.pop('state', None)
        await edit(
            f"✅ <b>Рассылка завершена</b>\n\nОтправлено: <b>{sent}</b> из {len(users)}",
            kb_back()
        )
        return

    if data == 'mailing_no':
        context.user_data.pop('mailing_text', None)
        context.user_data.pop('state', None)
        await back()
        return


# ══════════════════════════════════════════
#       РОУТЕР ТЕКСТОВЫХ СООБЩЕНИЙ
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

    level = db.get_rank_level(user.id)

    # ── Отмена любого состояния ──
    if lower == 'отмена' and state:
        context.user_data.clear()
        await update.message.reply_text("❌ Отменено.")
        await send_panel(update.message.reply_text, user.id)
        return

    # ════ СОСТОЯНИЯ ПАНЕЛИ ════

    if state == 'mailing_input':
        if level > PERM_MAILING:
            context.user_data.clear()
            return
        context.user_data['mailing_text'] = text
        context.user_data['state'] = 'mailing_confirm'
        await update.message.reply_text(
            f"📨 <b>Текст рассылки:</b>\n\n{text}\n\nОтправить всем?",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Отправить", callback_data="mailing_yes"),
                InlineKeyboardButton("❌ Отмена",   callback_data="mailing_no"),
            ]])
        )
        return

    if state == 'ban_input':
        if level > 8:
            context.user_data.clear()
            return
        parts = text.split(None, 1)
        try:
            ban_id = int(parts[0])
            reason = parts[1] if len(parts) > 1 else 'без причины'
            db.ban_user(ban_id, reason, user.id)
            context.user_data.clear()
            await update.message.reply_text(
                f"🔨 Пользователь <code>{ban_id}</code> заблокирован.\nПричина: {reason}",
                parse_mode='HTML'
            )
        except (ValueError, IndexError):
            await update.message.reply_text("❌ Формат: <code>ID причина</code>", parse_mode='HTML')
        return

    if state == 'unban_input':
        if level > 8:
            context.user_data.clear()
            return
        try:
            uid = int(text)
            db.unban_user(uid)
            context.user_data.clear()
            await update.message.reply_text(
                f"🔓 Пользователь <code>{uid}</code> разблокирован.", parse_mode='HTML'
            )
        except ValueError:
            await update.message.reply_text("❌ Введите числовой ID.")
        return

    if state == 'find_user':
        if level > 4:
            context.user_data.clear()
            return
        found = find_user_by_query(text)
        context.user_data.clear()
        if found:
            rank_name = db.get_rank_name(found['user_id'])
            un        = f"@{found['username']}" if found.get('username') else '—'
            await update.message.reply_text(
                f"👤 <b>Пользователь найден</b>\n\n"
                f"<b>ID:</b> <code>{found['user_id']}</code>\n"
                f"<b>Username:</b> {un}\n"
                f"<b>Имя:</b> {found.get('first_name', '—')}\n"
                f"<b>Должность:</b> {rank_name}\n"
                f"<b>Забанен:</b> {'да ❌' if found.get('is_banned') else 'нет ✅'}\n"
                f"<b>Регистрация:</b> {str(found.get('registered_date', ''))[:10]}",
                parse_mode='HTML'
            )
        else:
            await update.message.reply_text(
                f"❌ Пользователь <code>{text}</code> не найден.", parse_mode='HTML'
            )
        return

    # Ввод кому выдаём должность
    if state == 'assign_who':
        if level > PERM_ASSIGN:
            context.user_data.clear()
            return
        target = find_user_by_query(text)
        if not target:
            await update.message.reply_text(
                f"❌ Пользователь <code>{text}</code> не найден.\nПопробуйте ещё раз.",
                parse_mode='HTML'
            )
            return

        target_level = db.get_rank_level(target['user_id'])
        if target_level <= level:
            await update.message.reply_text(
                "❌ Нельзя изменить должность пользователя с равным или более высоким уровнем."
            )
            context.user_data.clear()
            return

        un = f"@{target['username']}" if target.get('username') else f"id:{target['user_id']}"
        context.user_data['state'] = 'assign_select'

        await update.message.reply_text(
            f"👤 Пользователь: <b>{un}</b>\n\nВыберите должность для выдачи:",
            parse_mode='HTML',
            # target_id встроен в callback — не теряется при смене сообщений
            reply_markup=get_rank_keyboard(level, 'assign', target['user_id'])
        )
        return

    # Ввод у кого снимаем должность
    if state == 'remove_who':
        if level > PERM_ASSIGN:
            context.user_data.clear()
            return
        target = find_user_by_query(text)
        if not target:
            await update.message.reply_text(
                f"❌ Пользователь <code>{text}</code> не найден.", parse_mode='HTML'
            )
            return

        target_level = db.get_rank_level(target['user_id'])
        if target_level <= level:
            await update.message.reply_text(
                "❌ Нельзя снять должность с пользователя выше или равного по уровню."
            )
            context.user_data.clear()
            return

        if not target.get('rank'):
            await update.message.reply_text("❌ У пользователя нет должности.")
            context.user_data.clear()
            return

        un       = f"@{target['username']}" if target.get('username') else f"id:{target['user_id']}"
        cur_rank = db.get_rank_name(target['user_id'])
        context.user_data['state'] = 'remove_confirm'

        await update.message.reply_text(
            f"👤 Пользователь: <b>{un}</b>\n"
            f"Текущая должность: <b>{cur_rank}</b>\n\n"
            f"Подтвердить снятие?",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                # target_id встроен в callback
                InlineKeyboardButton("✅ Снять",   callback_data=f"do_remove_{target['user_id']}"),
                InlineKeyboardButton("❌ Отмена",  callback_data="p_back"),
            ]])
        )
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
#       ЧЕК / ГЛОБАН / РАЗБАН / БАЗА / СТАТА
# ══════════════════════════════════════════

async def handle_chek(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user  = update.effective_user
    parts = update.message.text.strip().split(None, 1)
    query = parts[1].strip() if len(parts) > 1 else (context.args[0] if context.args else '')

    if not query:
        await update.message.reply_text(
            "❌ Пример: <code>чек @username</code>", parse_mode='HTML'
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
            lines.append(f"{i}. {un} — {str(s.get('reason', ''))[:50]}…")
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
            f"⚠️ <b>{target}</b> уже в базе (#{existing['id']}).", parse_mode='HTML'
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
        f"<b>Добавил:</b> {mod} | Запись #{sid}",
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
        await update.message.reply_text(
            "❌ Пример: <code>разбан @username</code>", parse_mode='HTML'
        )
        return

    scammer = db.get_scammer(target)
    if not scammer:
        await update.message.reply_text(
            f"❌ <code>{target}</code> не найден в базе.", parse_mode='HTML'
        )
        return

    db.delete_scammer(scammer['id'])
    mod = f"@{user.username}" if user.username else user.first_name
    await update.message.reply_text(
        f"🗑 <b>{target} удалён из базы</b>\nЗапись #{scammer['id']} | Удалил: {mod}",
        parse_mode='HTML'
    )


async def handle_baza(update: Update, context: ContextTypes.DEFAULT_TYPE):
    scammers = db.get_approved_scammers()
    if not scammers:
        await update.message.reply_text(
            f"📭 <b>База {Config.BOT_NAME} пуста</b>", parse_mode='HTML'
        )
        return
    text, total_pages = build_base_page(scammers, 0)
    await update.message.reply_text(
        text, parse_mode='HTML',
        reply_markup=kb_pages(0, total_pages) if total_pages > 1 else None
    )
    db.add_stat('baza', update.effective_user.id)


async def handle_stata(update: Update, context: ContextTypes.DEFAULT_TYPE):
    level = db.get_rank_level(update.effective_user.id)
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
