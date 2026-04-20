# main.py
import logging
import asyncio
from datetime import datetime
from typing import Dict, Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, filters, ContextTypes
)

from config import Config
from database import Database

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния для разговоров
(
    MAIN_MENU, SEARCH_INPUT, ADD_SCAMMER_REASON, ADD_SCAMMER_PROOFS,
    ADD_SCAMMER_CONFIRM, ADMIN_MENU, MODER_MENU, MAILING_INPUT,
    ADMIN_ADD_MODER, ADMIN_REMOVE_MODER, PENDING_LIST
) = range(11)

# Инициализация БД
db = Database()

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========

def get_main_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Главное меню"""
    keyboard = [
        [InlineKeyboardButton("🔍 Поиск", callback_data='search')],
        [InlineKeyboardButton("➕ Добавить мошенника", callback_data='add_scammer')],
    ]
    
    user = db.get_user(user_id)
    if user:
        if user.get('is_admin'):
            keyboard.append([InlineKeyboardButton("👑 Админ панель", callback_data='admin_panel')])
        elif user.get('is_moder'):
            keyboard.append([InlineKeyboardButton("🛡 Модер панель", callback_data='moder_panel')])
    
    return InlineKeyboardMarkup(keyboard)

def get_admin_keyboard() -> InlineKeyboardMarkup:
    """Админ панель"""
    keyboard = [
        [InlineKeyboardButton("📊 Статистика", callback_data='admin_stats')],
        [InlineKeyboardButton("📨 Рассылка", callback_data='admin_mailing')],
        [InlineKeyboardButton("📝 Заявки", callback_data='admin_pending')],
        [InlineKeyboardButton("➕ Добавить модера", callback_data='admin_add_moder')],
        [InlineKeyboardButton("➖ Убрать модера", callback_data='admin_remove_moder')],
        [InlineKeyboardButton("🔙 Назад", callback_data='back_to_main')]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_moder_keyboard() -> InlineKeyboardMarkup:
    """Модер панель"""
    keyboard = [
        [InlineKeyboardButton("📝 Заявки", callback_data='moder_pending')],
        [InlineKeyboardButton("🔙 Назад", callback_data='back_to_main')]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_pending_keyboard(scammer_id: int, is_admin: bool = False) -> InlineKeyboardMarkup:
    """Клавиатура для заявок"""
    keyboard = [
        [
            InlineKeyboardButton("✅ Одобрить", callback_data=f'approve_{scammer_id}'),
            InlineKeyboardButton("❌ Отклонить", callback_data=f'reject_{scammer_id}')
        ],
        [InlineKeyboardButton("🔙 Назад", callback_data='back_to_pending')]
    ]
    return InlineKeyboardMarkup(keyboard)

# ========== ОБРАБОТЧИКИ КОМАНД ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user
    db.add_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )
    
    welcome_text = f"""
👋 <b>Добро пожаловать в ANT BASE!</b>

Этот бот поможет вам проверить человека на причастность к мошенничеству.

<b>Что я умею:</b>
🔍 Искать мошенников по ID или username
➕ Добавлять новых мошенников (после проверки модератором)
📊 Показывать статистику

<b>Как пользоваться:</b>
1. Нажми "Поиск" и введи ID или username
2. Если человека нет в базе - добавь его с доказательствами
3. Модераторы проверят и добавят в базу

<i>Будьте осторожны в сети! 🛡</i>
"""
    await update.message.reply_text(
        welcome_text,
        parse_mode='HTML',
        reply_markup=get_main_keyboard(user.id)
    )
    
    db.add_stat('start', user.id)

async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /info"""
    if not context.args:
        await update.message.reply_text("❌ Использование: /info <id или username>")
        return
    
    query = context.args[0]
    scammer = db.get_scammer(query)
    
    if scammer:
        text = f"""
🚨 <b>НАЙДЕН МОШЕННИК!</b>

<b>ID:</b> {scammer['scammer_id']}
<b>Username:</b> @{scammer['scammer_username']}
<b>Имя:</b> {scammer['scammer_name']}
<b>Причина:</b> {scammer['reason']}
<b>Доказательства:</b> {scammer['proofs']}
<b>Добавлен:</b> {scammer['created_at']}

⚠️ <b>Будьте осторожны!</b>
"""
    else:
        text = f"""
✅ <b>ЧЕЛОВЕК НЕ НАЙДЕН В БАЗЕ</b>

Запрос: {query}

Если вы стали жертвой мошенничества со стороны этого человека - добавьте его в базу через меню бота.
"""
    
    await update.message.reply_text(text, parse_mode='HTML')
    db.add_stat('info', update.effective_user.id, query)

# ========== ОБРАБОТЧИКИ СООБЩЕНИЙ ==========

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    user = update.effective_user
    text = update.message.text
    
    # Обновляем активность пользователя
    db.add_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )
    
    state = context.user_data.get('state', MAIN_MENU)
    
    if state == SEARCH_INPUT:
        # Поиск мошенника
        scammer = db.get_scammer(text)
        
        if scammer:
            response = f"""
🚨 <b>МОШЕННИК НАЙДЕН!</b>

<b>Данные:</b>
• ID: {scammer['scammer_id']}
• Username: @{scammer['scammer_username']}
• Имя: {scammer['scammer_name']}

<b>Причина:</b>
{scammer['reason']}

<b>Доказательства:</b>
{scammer['proofs']}

⚠️ <b>Будьте осторожны при общении с этим человеком!</b>
"""
        else:
            response = f"""
✅ <b>ЧИСТО</b>

По запросу <code>{text}</code> ничего не найдено.

Если у вас есть информация о мошенничестве - добавьте его в базу через меню.
"""
        
        await update.message.reply_text(response, parse_mode='HTML')
        context.user_data['state'] = MAIN_MENU
        db.add_stat('search', user.id, text)
        
    elif state == ADD_SCAMMER_REASON:
        # Сохраняем причину
        context.user_data['scammer_reason'] = text
        context.user_data['state'] = ADD_SCAMMER_PROOFS
        await update.message.reply_text(
            "📎 Отправьте доказательства (скриншоты, ссылки, описание):"
        )
        
    elif state == ADD_SCAMMER_PROOFS:
        # Сохраняем доказательства
        context.user_data['scammer_proofs'] = text
        context.user_data['state'] = ADD_SCAMMER_CONFIRM
        
        confirm_text = f"""
📝 <b>Проверьте данные:</b>

<b>ID/Username:</b> {context.user_data.get('scammer_id')}
<b>Причина:</b> {context.user_data.get('scammer_reason')}
<b>Доказательства:</b> {context.user_data.get('scammer_proofs')}

Всё верно?
"""
        keyboard = [
            [
                InlineKeyboardButton("✅ Да, отправить", callback_data='confirm_add'),
                InlineKeyboardButton("❌ Нет, заново", callback_data='cancel_add')
            ]
        ]
        await update.message.reply_text(
            confirm_text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    elif state == MAILING_INPUT:
        # Рассылка
        if not user.id in Config.ADMIN_IDS and not db.get_user(user.id).get('is_admin'):
            await update.message.reply_text("❌ У вас нет прав на рассылку")
            context.user_data['state'] = MAIN_MENU
            return
        
        context.user_data['mailing_text'] = text
        keyboard = [
            [
                InlineKeyboardButton("✅ Отправить", callback_data='mailing_send'),
                InlineKeyboardButton("❌ Отмена", callback_data='mailing_cancel')
            ]
        ]
        await update.message.reply_text(
            f"📨 Текст рассылки:\n\n{text}\n\nОтправить?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

# ========== ОБРАБОТЧИКИ КОЛЛБЭКОВ ==========

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на кнопки"""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    data = query.data
    
    if data == 'search':
        # Поиск
        context.user_data['state'] = SEARCH_INPUT
        await query.edit_message_text(
            "🔍 Введите ID или username для поиска:"
        )
        
    elif data == 'add_scammer':
        # Добавление мошенника
        context.user_data['state'] = ADD_SCAMMER_REASON
        await query.edit_message_text(
            "⚠️ Введите ID или username мошенника:"
        )
        
    elif data == 'admin_panel':
        # Админ панель
        context.user_data['state'] = ADMIN_MENU
        await query.edit_message_text(
            "👑 Админ панель\n\nВыберите действие:",
            reply_markup=get_admin_keyboard()
        )
        
    elif data == 'moder_panel':
        # Модер панель
        context.user_data['state'] = MODER_MENU
        await query.edit_message_text(
            "🛡 Модер панель\n\nВыберите действие:",
            reply_markup=get_moder_keyboard()
        )
        
    elif data == 'admin_stats':
        # Статистика
        stats = db.get_stats()
        text = f"""
📊 <b>СТАТИСТИКА БОТА</b>

👥 <b>Пользователи:</b>
• Всего: {stats['total_users']}
• Активность сегодня: {stats['today_activity']}

🚨 <b>Мошенники:</b>
• Всего: {stats['total_scammers']}
• Подтверждено: {stats['approved_scammers']}
• Ожидает: {stats['pending_scammers']}

🔍 <b>Поиски:</b>
• Всего запросов: {stats['total_searches']}
"""
        await query.edit_message_text(
            text,
            parse_mode='HTML',
            reply_markup=get_admin_keyboard()
        )
        
    elif data == 'admin_mailing':
        # Рассылка
        context.user_data['state'] = MAILING_INPUT
        await query.edit_message_text(
            "📨 Введите текст для рассылки:"
        )
        
    elif data == 'admin_pending' or data == 'moder_pending':
        # Список заявок
        pending = db.get_pending_scammers()
        context.user_data['state'] = PENDING_LIST
        
        if not pending:
            await query.edit_message_text(
                "📝 Нет активных заявок",
                reply_markup=get_admin_keyboard() if data == 'admin_pending' else get_moder_keyboard()
            )
            return
        
        for scammer in pending[:5]:  # Показываем по 5 заявок
            text = f"""
📝 <b>Заявка #{scammer['id']}</b>

<b>ID/Username:</b> {scammer['scammer_id']}
<b>Причина:</b> {scammer['reason']}
<b>Доказательства:</b> {scammer['proofs']}
<b>Добавил:</b> {scammer['added_by']}
<b>Дата:</b> {scammer['created_at']}
"""
            is_admin = db.get_user(user.id).get('is_admin', False)
            await query.message.reply_text(
                text,
                parse_mode='HTML',
                reply_markup=get_pending_keyboard(scammer['id'], is_admin)
            )
        
        await query.edit_message_text(
            "📝 Список заявок:",
            reply_markup=get_admin_keyboard() if data == 'admin_pending' else get_moder_keyboard()
        )
        
    elif data.startswith('approve_'):
        # Одобрение заявки
        scammer_id = int(data.split('_')[1])
        db.update_scammer_status(scammer_id, 'approved', user.id)
        await query.edit_message_text("✅ Заявка одобрена")
        
    elif data.startswith('reject_'):
        # Отклонение заявки
        scammer_id = int(data.split('_')[1])
        db.update_scammer_status(scammer_id, 'rejected', user.id)
        await query.edit_message_text("❌ Заявка отклонена")
        
    elif data == 'admin_add_moder':
        # Добавление модера
        context.user_data['state'] = ADMIN_ADD_MODER
        await query.edit_message_text(
            "➕ Введите ID пользователя, которого хотите сделать модератором:"
        )
        
    elif data == 'admin_remove_moder':
        # Удаление модера
        context.user_data['state'] = ADMIN_REMOVE_MODER
        await query.edit_message_text(
            "➖ Введите ID пользователя, у которого хотите убрать права модератора:"
        )
        
    elif data == 'back_to_main':
        # Назад в главное меню
        context.user_data['state'] = MAIN_MENU
        await query.edit_message_text(
            "🏠 Главное меню",
            reply_markup=get_main_keyboard(user.id)
        )
        
    elif data == 'back_to_pending':
        # Назад к списку заявок
        pending = db.get_pending_scammers()
        if pending:
            await query.edit_message_text("📝 Список заявок:")
        else:
            await query.edit_message_text(
                "📝 Нет активных заявок",
                reply_markup=get_admin_keyboard() if db.get_user(user.id).get('is_admin') else get_moder_keyboard()
            )
            
    elif data == 'confirm_add':
        # Подтверждение добавления мошенника
        scammer_id = context.user_data.get('scammer_id')
        reason = context.user_data.get('scammer_reason')
        proofs = context.user_data.get('scammer_proofs')
        
        db.add_scammer(
            scammer_id=scammer_id,
            scammer_username=scammer_id.replace('@', ''),
            scammer_name=scammer_id,
            reason=reason,
            proofs=proofs,
            added_by=user.id
        )
        
        await query.edit_message_text(
            "✅ Заявка отправлена на проверку модераторам!",
            reply_markup=get_main_keyboard(user.id)
        )
        context.user_data['state'] = MAIN_MENU
        
    elif data == 'cancel_add':
        # Отмена добавления
        context.user_data['state'] = MAIN_MENU
        await query.edit_message_text(
            "❌ Добавление отменено",
            reply_markup=get_main_keyboard(user.id)
        )
        
    elif data == 'mailing_send':
        # Отправка рассылки
        text = context.user_data.get('mailing_text')
        users = db.get_all_users()
        sent = 0
        
        for user_data in users:
            try:
                await context.bot.send_message(
                    chat_id=user_data['user_id'],
                    text=f"📨 <b>РАССЫЛКА</b>\n\n{text}",
                    parse_mode='HTML'
                )
                sent += 1
                await asyncio.sleep(0.05)  # Anti-flood
            except:
                continue
        
        db.add_mailing(text, user.id, sent)
        await query.edit_message_text(
            f"✅ Рассылка отправлена {sent} пользователям",
            reply_markup=get_admin_keyboard()
        )
        context.user_data['state'] = ADMIN_MENU
        
    elif data == 'mailing_cancel':
        # Отмена рассылки
        context.user_data['state'] = ADMIN_MENU
        await query.edit_message_text(
            "❌ Рассылка отменена",
            reply_markup=get_admin_keyboard()
        )

# ========== ОБРАБОТЧИКИ КОМАНД АДМИНОВ ==========

async def handle_admin_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода для админ команд"""
    user = update.effective_user
    text = update.message.text
    state = context.user_data.get('state')
    
    if state == ADMIN_ADD_MODER:
        # Добавление модера
        try:
            mod_id = int(text)
            db.set_moder(mod_id, True)
            await update.message.reply_text(f"✅ Пользователь {mod_id} теперь модератор")
        except:
            await update.message.reply_text("❌ Неверный ID")
        context.user_data['state'] = ADMIN_MENU
        
    elif state == ADMIN_REMOVE_MODER:
        # Удаление модера
        try:
            mod_id = int(text)
            db.set_moder(mod_id, False)
            await update.message.reply_text(f"✅ У пользователя {mod_id} убраны права модератора")
        except:
            await update.message.reply_text("❌ Неверный ID")
        context.user_data['state'] = ADMIN_MENU

# ========== ОСНОВНАЯ ФУНКЦИЯ ==========

def main():
    """Запуск бота"""
    # Создаем приложение
    app = Application.builder().token(Config.BOT_TOKEN).build()
    
    # Добавляем обработчики команд
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("info", info_command))
    
    # Добавляем обработчики сообщений
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Добавляем обработчик коллбэков
    app.add_handler(CallbackQueryHandler(button_handler))
    
    # Добавляем обработчик админ ввода
    app.add_handler(MessageHandler(
        filters.TEXT & filters.User(user_id=Config.ADMIN_IDS), 
        handle_admin_input
    ))
    
    # Запускаем бота
    print(f"✅ Бот {Config.BOT_NAME} запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()