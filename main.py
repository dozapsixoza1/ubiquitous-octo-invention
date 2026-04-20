# main.py
import logging
import asyncio
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.error import TelegramError
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)

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

# ───────────── СОСТОЯНИЯ ─────────────
(
    MAIN_MENU,
    SEARCH_INPUT,
    ADD_SCAMMER_ID,
    ADD_SCAMMER_REASON,
    ADD_SCAMMER_PROOFS,
    ADD_SCAMMER_CONFIRM,
    ADMIN_MENU,
    MODER_MENU,
    MAILING_INPUT,
    MAILING_CONFIRM,
    ADMIN_ADD_MODER,
    ADMIN_REMOVE_MODER,
    ADMIN_BAN_INPUT,
    ADMIN_UNBAN_INPUT,
    PENDING_LIST,
) = range(15)

db = Database()

# ══════════════════════════════════════════
#               КЛАВИАТУРЫ
# ══════════════════════════════════════════

def kb_main(user_id: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("🔍 Поиск в базе", callback_data='search')],
        [InlineKeyboardButton("➕ Добавить мошенника", callback_data='add_scammer')],
        [InlineKeyboardButton("📖 О боте", callback_data='about')],
    ]
    if db.is_admin(user_id):
        rows.append([InlineKeyboardButton("👑 Админ панель", callback_data='admin_panel')])
    elif db.is_moder(user_id):
        rows.append([InlineKeyboardButton("🛡 Модер панель", callback_data='moder_panel')])
    return InlineKeyboardMarkup(rows)


def kb_admin() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Статистика", callback_data='admin_stats')],
        [InlineKeyboardButton("📨 Рассылка",   callback_data='admin_mailing')],
        [InlineKeyboardButton("📝 Заявки",     callback_data='admin_pending')],
        [InlineKeyboardButton("👥 Модераторы", callback_data='admin_moders_list')],
        [
            InlineKeyboardButton("➕ Добавить модера",  callback_data='admin_add_moder'),
            InlineKeyboardButton("➖ Убрать модера",    callback_data='admin_remove_moder'),
        ],
        [
            InlineKeyboardButton("🔨 Забанить юзера",  callback_data='admin_ban'),
            InlineKeyboardButton("🔓 Разбанить юзера", callback_data='admin_unban'),
        ],
        [InlineKeyboardButton("🗂 История рассылок",   callback_data='admin_mailing_history')],
        [InlineKeyboardButton("🔙 Назад",              callback_data='back_to_main')],
    ])


def kb_moder() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 Заявки на проверку", callback_data='moder_pending')],
        [InlineKeyboardButton("🔙 Назад",              callback_data='back_to_main')],
    ])


def kb_pending(scammer_db_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Одобрить", callback_data=f'approve_{scammer_db_id}'),
            InlineKeyboardButton("❌ Отклонить", callback_data=f'reject_{scammer_db_id}'),
        ],
    ])


def kb_confirm_mailing() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Отправить", callback_data='mailing_send'),
            InlineKeyboardButton("❌ Отмена",   callback_data='mailing_cancel'),
        ]
    ])


def kb_confirm_add() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Подтвердить", callback_data='confirm_add'),
            InlineKeyboardButton("❌ Отменить",    callback_data='cancel_add'),
        ]
    ])

# ══════════════════════════════════════════
#               ВСПОМОГАТЕЛИ
# ══════════════════════════════════════════

async def check_banned(update: Update) -> bool:
    """Возвращает True и отвечает, если юзер забанен."""
    uid = update.effective_user.id
    if db.is_banned(uid):
        text = "🚫 Вы заблокированы и не можете использовать бота."
        if update.message:
            await update.message.reply_text(text)
        elif update.callback_query:
            await update.callback_query.answer(text, show_alert=True)
        return True
    return False


async def check_subscription(bot: Bot, user_id: int) -> bool:
    """Проверка подписки на канал (если REQUIRED_CHANNEL задан)."""
    ch = Config.REQUIRED_CHANNEL
    if not ch:
        return True
    try:
        member = await bot.get_chat_member(ch, user_id)
        return member.status not in ('left', 'kicked')
    except TelegramError:
        return True   # если канал не найден — не блокируем


def format_scammer(s: dict) -> str:
    username = f"@{s['scammer_username']}" if s.get('scammer_username') else '—'
    return (
        f"🚨 <b>МОШЕННИК НАЙДЕН!</b>\n\n"
        f"<b>ID:</b> <code>{s['scammer_id']}</code>\n"
        f"<b>Username:</b> {username}\n"
        f"<b>Имя:</b> {s.get('scammer_name') or '—'}\n\n"
        f"<b>Причина:</b>\n{s['reason']}\n\n"
        f"<b>Доказательства:</b>\n{s['proofs']}\n\n"
        f"<b>Добавлено:</b> {s.get('created_at', '')[:10]}\n\n"
        f"⚠️ <i>Будьте осторожны!</i>"
    )

# ══════════════════════════════════════════
#               КОМАНДЫ
# ══════════════════════════════════════════

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.add_user(user.id, user.username, user.first_name, user.last_name)

    if await check_banned(update):
        return

    if not await check_subscription(context.bot, user.id):
        ch = Config.REQUIRED_CHANNEL
        await update.message.reply_text(
            f"⚠️ Для использования бота необходимо подписаться на канал {ch}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📢 Подписаться", url=f"https://t.me/{ch.lstrip('@')}")],
                [InlineKeyboardButton("✅ Проверить подписку", callback_data='check_sub')],
            ])
        )
        return

    context.user_data['state'] = MAIN_MENU
    db.add_stat('start', user.id)

    await update.message.reply_text(
        f"👋 <b>Добро пожаловать в {Config.BOT_NAME}!</b>\n\n"
        "Этот бот поможет вам проверить человека на причастность к мошенничеству.\n\n"
        "<b>Что умеет бот:</b>\n"
        "🔍 Поиск по ID, username или имени\n"
        "➕ Добавление мошенников (проходит модерацию)\n"
        "📊 Статистика базы\n\n"
        "<i>Будьте осторожны в сети! 🛡</i>",
        parse_mode='HTML',
        reply_markup=kb_main(user.id)
    )


async def cmd_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_banned(update):
        return
    if not context.args:
        await update.message.reply_text("❌ Использование: /info <id или @username>")
        return

    query = context.args[0]
    scammer = db.get_scammer(query)
    db.add_stat('info', update.effective_user.id, query)

    if scammer:
        await update.message.reply_text(format_scammer(scammer), parse_mode='HTML')
    else:
        await update.message.reply_text(
            f"✅ <b>Чисто</b>\n\nПо запросу <code>{query}</code> ничего не найдено в базе.",
            parse_mode='HTML'
        )


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Быстрая команда /stats — только для админов/модеров."""
    uid = update.effective_user.id
    if not db.is_admin(uid) and not db.is_moder(uid):
        return
    stats = db.get_stats()
    await update.message.reply_text(
        _stats_text(stats), parse_mode='HTML'
    )

# ══════════════════════════════════════════
#               ОБРАБОТКА СООБЩЕНИЙ
# ══════════════════════════════════════════

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_banned(update):
        return

    user  = update.effective_user
    text  = update.message.text.strip()
    state = context.user_data.get('state', MAIN_MENU)

    db.add_user(user.id, user.username, user.first_name, user.last_name)

    # ── поиск ──
    if state == SEARCH_INPUT:
        scammer = db.get_scammer(text)
        db.add_stat('search', user.id, text)

        if scammer:
            await update.message.reply_text(format_scammer(scammer), parse_mode='HTML')
        else:
            # Попробуем полнотекстовый поиск
            results = db.search_scammers(text)
            if results:
                lines = [f"🔍 <b>Найдено совпадений: {len(results)}</b>\n"]
                for s in results[:5]:
                    un = f"@{s['scammer_username']}" if s.get('scammer_username') else s['scammer_id']
                    lines.append(f"• {un} — {s['reason'][:60]}…")
                lines.append("\nИспользуйте точный ID или @username для полной карточки.")
                await update.message.reply_text("\n".join(lines), parse_mode='HTML')
            else:
                await update.message.reply_text(
                    f"✅ <b>Чисто</b>\n\nПо запросу <code>{text}</code> ничего не найдено.",
                    parse_mode='HTML'
                )
        context.user_data['state'] = MAIN_MENU
        await update.message.reply_text("🏠 Главное меню", reply_markup=kb_main(user.id))
        return

    # ── добавление: ID мошенника ──
    if state == ADD_SCAMMER_ID:
        context.user_data['scammer_id'] = text
        context.user_data['state'] = ADD_SCAMMER_REASON
        await update.message.reply_text(
            "📝 Укажите причину (что именно сделал мошенник):"
        )
        return

    # ── добавление: причина ──
    if state == ADD_SCAMMER_REASON:
        context.user_data['scammer_reason'] = text
        context.user_data['state'] = ADD_SCAMMER_PROOFS
        await update.message.reply_text(
            "📎 Отправьте доказательства (скриншоты-ссылки, описание, сумма ущерба и т.д.):"
        )
        return

    # ── добавление: доказательства ──
    if state == ADD_SCAMMER_PROOFS:
        context.user_data['scammer_proofs'] = text
        context.user_data['state'] = ADD_SCAMMER_CONFIRM
        sid    = context.user_data.get('scammer_id', '—')
        reason = context.user_data.get('scammer_reason', '—')
        await update.message.reply_text(
            f"📋 <b>Проверьте данные перед отправкой:</b>\n\n"
            f"<b>ID/Username:</b> {sid}\n"
            f"<b>Причина:</b> {reason}\n"
            f"<b>Доказательства:</b> {text}",
            parse_mode='HTML',
            reply_markup=kb_confirm_add()
        )
        return

    # ── рассылка ──
    if state == MAILING_INPUT:
        if not db.is_admin(user.id):
            await update.message.reply_text("❌ Нет прав.")
            context.user_data['state'] = ADMIN_MENU
            return
        context.user_data['mailing_text'] = text
        context.user_data['state'] = MAILING_CONFIRM
        await update.message.reply_text(
            f"📨 <b>Текст рассылки:</b>\n\n{text}\n\nОтправить всем пользователям?",
            parse_mode='HTML',
            reply_markup=kb_confirm_mailing()
        )
        return

    # ── добавление модера (ввод ID) ──
    if state == ADMIN_ADD_MODER:
        if not db.is_admin(user.id):
            context.user_data['state'] = MAIN_MENU
            return
        try:
            mod_id = int(text)
            db.set_moder(mod_id, True)
            await update.message.reply_text(
                f"✅ Пользователь <code>{mod_id}</code> теперь модератор.",
                parse_mode='HTML', reply_markup=kb_admin()
            )
        except ValueError:
            await update.message.reply_text("❌ Неверный ID — введите число.")
        context.user_data['state'] = ADMIN_MENU
        return

    # ── удаление модера ──
    if state == ADMIN_REMOVE_MODER:
        if not db.is_admin(user.id):
            context.user_data['state'] = MAIN_MENU
            return
        try:
            mod_id = int(text)
            db.set_moder(mod_id, False)
            await update.message.reply_text(
                f"✅ У пользователя <code>{mod_id}</code> убраны права модератора.",
                parse_mode='HTML', reply_markup=kb_admin()
            )
        except ValueError:
            await update.message.reply_text("❌ Неверный ID.")
        context.user_data['state'] = ADMIN_MENU
        return

    # ── бан ──
    if state == ADMIN_BAN_INPUT:
        if not db.is_admin(user.id):
            context.user_data['state'] = MAIN_MENU
            return
        parts = text.split(None, 1)
        try:
            ban_id = int(parts[0])
            reason = parts[1] if len(parts) > 1 else 'без причины'
            db.ban_user(ban_id, reason, user.id)
            await update.message.reply_text(
                f"🔨 Пользователь <code>{ban_id}</code> заблокирован.\nПричина: {reason}",
                parse_mode='HTML', reply_markup=kb_admin()
            )
        except (ValueError, IndexError):
            await update.message.reply_text("❌ Формат: <id> [причина]")
        context.user_data['state'] = ADMIN_MENU
        return

    # ── разбан ──
    if state == ADMIN_UNBAN_INPUT:
        if not db.is_admin(user.id):
            context.user_data['state'] = MAIN_MENU
            return
        try:
            unban_id = int(text)
            db.unban_user(unban_id)
            await update.message.reply_text(
                f"🔓 Пользователь <code>{unban_id}</code> разблокирован.",
                parse_mode='HTML', reply_markup=kb_admin()
            )
        except ValueError:
            await update.message.reply_text("❌ Неверный ID.")
        context.user_data['state'] = ADMIN_MENU
        return

    # ── иначе — главное меню ──
    await update.message.reply_text(
        "🏠 Главное меню", reply_markup=kb_main(user.id)
    )

# ══════════════════════════════════════════
#               ОБРАБОТЧИК КНОПОК
# ══════════════════════════════════════════

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user
    data = query.data

    if await check_banned(update):
        return

    # ─ проверка подписки ─
    if data == 'check_sub':
        if await check_subscription(context.bot, user.id):
            context.user_data['state'] = MAIN_MENU
            await query.edit_message_text(
                f"✅ Подписка подтверждена!\n\n"
                f"👋 Добро пожаловать в <b>{Config.BOT_NAME}</b>!",
                parse_mode='HTML',
                reply_markup=kb_main(user.id)
            )
        else:
            ch = Config.REQUIRED_CHANNEL
            await query.answer("❌ Вы ещё не подписались!", show_alert=True)
        return

    # ─ поиск ─
    if data == 'search':
        context.user_data['state'] = SEARCH_INPUT
        await query.edit_message_text(
            "🔍 Введите ID, @username или имя для поиска в базе:"
        )
        return

    # ─ добавление мошенника ─
    if data == 'add_scammer':
        uid = user.id
        # Лимит заявок
        cnt = db.count_pending_by_user(uid)
        if cnt >= Config.MAX_PENDING_PER_USER:
            await query.answer(
                f"❌ У вас уже {cnt} заявки на проверке. Дождитесь решения модераторов.",
                show_alert=True
            )
            return
        context.user_data['state'] = ADD_SCAMMER_ID
        await query.edit_message_text(
            "⚠️ Введите Telegram ID или @username мошенника:"
        )
        return

    # ─ о боте ─
    if data == 'about':
        stats = db.get_stats()
        await query.edit_message_text(
            f"ℹ️ <b>{Config.BOT_NAME} v{Config.BOT_VERSION}</b>\n\n"
            f"📊 В базе подтверждённых мошенников: <b>{stats['approved_scammers']}</b>\n"
            f"👥 Пользователей бота: <b>{stats['total_users']}</b>\n\n"
            f"Бот помогает проверить человека перед сделкой.",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад", callback_data='back_to_main')]
            ])
        )
        return

    # ─ главное меню ─
    if data == 'back_to_main':
        context.user_data['state'] = MAIN_MENU
        await query.edit_message_text(
            "🏠 <b>Главное меню</b>",
            parse_mode='HTML',
            reply_markup=kb_main(user.id)
        )
        return

    # ─ подтверждение добавления ─
    if data == 'confirm_add':
        sid    = context.user_data.get('scammer_id', '')
        reason = context.user_data.get('scammer_reason', '')
        proofs = context.user_data.get('scammer_proofs', '')

        db.add_scammer(
            scammer_id=sid,
            scammer_username=sid.lstrip('@'),
            scammer_name=sid,
            reason=reason,
            proofs=proofs,
            added_by=user.id
        )
        db.add_stat('add_scammer', user.id, sid)

        context.user_data['state'] = MAIN_MENU
        await query.edit_message_text(
            "✅ <b>Заявка отправлена!</b>\n\nМодераторы проверят её в ближайшее время.",
            parse_mode='HTML',
            reply_markup=kb_main(user.id)
        )

        # Уведомляем модеров
        await _notify_moders(context, sid, reason, user)
        return

    if data == 'cancel_add':
        context.user_data['state'] = MAIN_MENU
        await query.edit_message_text(
            "❌ Добавление отменено.",
            reply_markup=kb_main(user.id)
        )
        return

    # ═══════ АДМИН ПАНЕЛЬ ═══════

    if data == 'admin_panel':
        if not db.is_admin(user.id):
            await query.answer("❌ Нет доступа.", show_alert=True)
            return
        context.user_data['state'] = ADMIN_MENU
        await query.edit_message_text(
            f"👑 <b>Админ панель</b> — {Config.BOT_NAME}",
            parse_mode='HTML',
            reply_markup=kb_admin()
        )
        return

    if data == 'admin_stats':
        if not db.is_admin(user.id):
            return
        stats = db.get_stats()
        await query.edit_message_text(
            _stats_text(stats),
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад", callback_data='admin_panel')]
            ])
        )
        return

    if data == 'admin_moders_list':
        if not db.is_admin(user.id):
            return
        moders = db.get_moderators()
        if moders:
            lines = ["👥 <b>Список модераторов:</b>\n"]
            for m in moders:
                un = f"@{m['username']}" if m.get('username') else f"id:{m['user_id']}"
                lines.append(f"• {un} — <code>{m['user_id']}</code>")
            text = "\n".join(lines)
        else:
            text = "👥 Модераторов пока нет."
        await query.edit_message_text(
            text, parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад", callback_data='admin_panel')]
            ])
        )
        return

    if data == 'admin_mailing':
        if not db.is_admin(user.id):
            return
        context.user_data['state'] = MAILING_INPUT
        await query.edit_message_text(
            "📨 Введите текст рассылки (поддерживается HTML):"
        )
        return

    if data == 'admin_mailing_history':
        if not db.is_admin(user.id):
            return
        mailings = db.get_mailings(5)
        if mailings:
            lines = ["📬 <b>Последние рассылки:</b>\n"]
            for m in mailings:
                lines.append(
                    f"• {m['sent_at'][:16]} — {m['recipients_count']} получателей\n"
                    f"  <i>{str(m['message'])[:60]}…</i>"
                )
            text = "\n\n".join(lines)
        else:
            text = "📬 Рассылок ещё не было."
        await query.edit_message_text(
            text, parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад", callback_data='admin_panel')]
            ])
        )
        return

    if data == 'mailing_send':
        if not db.is_admin(user.id):
            return
        mailing_text = context.user_data.get('mailing_text', '')
        all_users = db.get_all_users_not_banned()
        sent = 0
        for u in all_users:
            try:
                await context.bot.send_message(
                    chat_id=u['user_id'],
                    text=f"📨 <b>РАССЫЛКА от {Config.BOT_NAME}</b>\n\n{mailing_text}",
                    parse_mode='HTML'
                )
                sent += 1
                await asyncio.sleep(Config.MAILING_SLEEP_SEC)
            except TelegramError:
                continue

        db.add_mailing(mailing_text, user.id, sent)
        context.user_data['state'] = ADMIN_MENU
        await query.edit_message_text(
            f"✅ Рассылка завершена.\nОтправлено: <b>{sent}</b> из {len(all_users)}",
            parse_mode='HTML',
            reply_markup=kb_admin()
        )
        return

    if data == 'mailing_cancel':
        context.user_data['state'] = ADMIN_MENU
        await query.edit_message_text(
            "❌ Рассылка отменена.", reply_markup=kb_admin()
        )
        return

    if data == 'admin_add_moder':
        if not db.is_admin(user.id):
            return
        context.user_data['state'] = ADMIN_ADD_MODER
        await query.edit_message_text(
            "➕ Введите Telegram ID пользователя, которого хотите назначить модератором:"
        )
        return

    if data == 'admin_remove_moder':
        if not db.is_admin(user.id):
            return
        context.user_data['state'] = ADMIN_REMOVE_MODER
        await query.edit_message_text(
            "➖ Введите Telegram ID модератора, которого хотите снять:"
        )
        return

    if data == 'admin_ban':
        if not db.is_admin(user.id):
            return
        context.user_data['state'] = ADMIN_BAN_INPUT
        await query.edit_message_text(
            "🔨 Введите ID пользователя и (опционально) причину:\n"
            "<code>123456789 спам</code>",
            parse_mode='HTML'
        )
        return

    if data == 'admin_unban':
        if not db.is_admin(user.id):
            return
        context.user_data['state'] = ADMIN_UNBAN_INPUT
        await query.edit_message_text(
            "🔓 Введите ID пользователя для разблокировки:"
        )
        return

    # ═══════ ЗАЯВКИ (ADMIN + MODER) ═══════

    if data in ('admin_pending', 'moder_pending'):
        is_adm = db.is_admin(user.id)
        is_mod = db.is_moder(user.id)
        if not is_adm and not is_mod:
            await query.answer("❌ Нет доступа.", show_alert=True)
            return

        pending = db.get_pending_scammers()
        if not pending:
            await query.edit_message_text(
                "📝 Активных заявок нет.",
                reply_markup=kb_admin() if is_adm else kb_moder()
            )
            return

        await query.edit_message_text(
            f"📝 <b>Заявок на проверке: {len(pending)}</b>\n\nПросматриваю первые 5…",
            parse_mode='HTML',
            reply_markup=kb_admin() if is_adm else kb_moder()
        )

        for s in pending[:5]:
            un = f"@{s['scammer_username']}" if s.get('scammer_username') else s['scammer_id']
            txt = (
                f"📋 <b>Заявка #{s['id']}</b>\n\n"
                f"<b>ID/Username:</b> {un}\n"
                f"<b>Причина:</b> {s['reason']}\n"
                f"<b>Доказательства:</b> {s['proofs']}\n"
                f"<b>От:</b> <code>{s['added_by']}</code>\n"
                f"<b>Дата:</b> {str(s['created_at'])[:16]}"
            )
            await query.message.reply_text(
                txt, parse_mode='HTML',
                reply_markup=kb_pending(s['id'])
            )
        return

    if data == 'moder_panel':
        if not db.is_moder(user.id):
            await query.answer("❌ Нет доступа.", show_alert=True)
            return
        context.user_data['state'] = MODER_MENU
        await query.edit_message_text(
            "🛡 <b>Панель модератора</b>",
            parse_mode='HTML',
            reply_markup=kb_moder()
        )
        return

    if data.startswith('approve_'):
        if not db.is_moder(user.id):
            await query.answer("❌ Нет доступа.", show_alert=True)
            return
        sid = int(data.split('_', 1)[1])
        db.update_scammer_status(sid, 'approved', user.id)
        await query.edit_message_text(f"✅ Заявка #{sid} одобрена.")
        return

    if data.startswith('reject_'):
        if not db.is_moder(user.id):
            await query.answer("❌ Нет доступа.", show_alert=True)
            return
        sid = int(data.split('_', 1)[1])
        db.update_scammer_status(sid, 'rejected', user.id)
        await query.edit_message_text(f"❌ Заявка #{sid} отклонена.")
        return

    # ─ fallback ─
    await query.answer("⚠️ Неизвестная команда.")

# ══════════════════════════════════════════
#               ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ══════════════════════════════════════════

def _stats_text(stats: dict) -> str:
    return (
        f"📊 <b>СТАТИСТИКА {Config.BOT_NAME}</b>\n\n"
        f"👥 <b>Пользователи:</b>\n"
        f"  • Всего: {stats['total_users']}\n"
        f"  • Заблокировано: {stats['banned_users']}\n"
        f"  • Активность сегодня: {stats['today_activity']}\n\n"
        f"🛡 <b>Команда:</b>\n"
        f"  • Модераторов: {stats['moderators']}\n\n"
        f"🚨 <b>База мошенников:</b>\n"
        f"  • Всего записей: {stats['total_scammers']}\n"
        f"  • Подтверждено: {stats['approved_scammers']}\n"
        f"  • Ожидают: {stats['pending_scammers']}\n"
        f"  • Отклонено: {stats['rejected_scammers']}\n\n"
        f"🔍 <b>Поиск:</b>\n"
        f"  • Всего запросов: {stats['total_searches']}\n"
        f"  • Сегодня: {stats['today_searches']}"
    )


async def _notify_moders(context: ContextTypes.DEFAULT_TYPE,
                         scammer_id: str, reason: str, from_user):
    """Уведомляем всех модеров о новой заявке."""
    moders = db.get_moderators()
    admins = [{'user_id': aid} for aid in Config.ADMIN_IDS]
    targets = {m['user_id'] for m in moders + admins}

    msg = (
        f"🔔 <b>Новая заявка!</b>\n\n"
        f"<b>ID/Username:</b> {scammer_id}\n"
        f"<b>Причина:</b> {reason[:100]}\n"
        f"<b>От:</b> @{from_user.username or from_user.id}\n\n"
        "Перейдите в панель модератора для проверки."
    )
    for uid in targets:
        try:
            await context.bot.send_message(uid, msg, parse_mode='HTML')
        except TelegramError:
            pass

# ══════════════════════════════════════════
#               ЗАПУСК
# ══════════════════════════════════════════

def main():
    Config.validate()   # Проверяем конфиг — упадём сразу если что-то не так

    app = Application.builder().token(Config.BOT_TOKEN).build()

    # Команды
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("info",  cmd_info))
    app.add_handler(CommandHandler("stats", cmd_stats))

    # Кнопки
    app.add_handler(CallbackQueryHandler(button_handler))

    # Текстовые сообщения
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info(f"✅ Бот {Config.BOT_NAME} v{Config.BOT_VERSION} запущен!")
    print(f"✅ {Config.BOT_NAME} v{Config.BOT_VERSION} — запущен. Ctrl+C для остановки.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
