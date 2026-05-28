import os
import json
import random
import logging
from datetime import datetime, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from telegram.constants import ParseMode
from telegram.error import Forbidden, BadRequest

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHANNEL = os.environ.get("TELEGRAM_CHANNEL", "@spreadxX")
REF_LINK = os.environ.get("POCKET_OPTION_REF_LINK", "https://po.trade")
BROADCAST_INTERVAL_MINUTES = int(os.environ.get("BROADCAST_INTERVAL_MINUTES", "30"))
STORAGE_FILE = "users.json"

PAIRS = ["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "USD/CAD",
         "EUR/GBP", "GBP/JPY", "EUR/JPY", "USD/CHF", "NZD/USD"]
EXPIRATIONS = ["1 мин", "2 мин", "3 мин", "5 мин"]
AMOUNTS = ["$1", "$5", "$10", "$25", "$50"]
DIRECTIONS = [("🔼", "ВЫШЕ (CALL)"), ("🔽", "НИЖЕ (PUT)")]

def load_users() -> set:
    if not os.path.exists(STORAGE_FILE):
        return set()
    try:
        with open(STORAGE_FILE) as f:
            return set(json.load(f).get("users", []))
    except Exception:
        return set()

def save_user(user_id: int) -> None:
    users = load_users()
    if user_id in users:
        return
    users.add(user_id)
    try:
        with open(STORAGE_FILE, "w") as f:
            json.dump({"users": list(users)}, f)
        logger.info("Новый пользователь: %d (всего: %d)", user_id, len(users))
    except Exception as e:
        logger.warning("Ошибка сохранения: %s", e)

def remove_user(user_id: int) -> None:
    users = load_users()
    users.discard(user_id)
    with open(STORAGE_FILE, "w") as f:
        json.dump({"users": list(users)}, f)

async def check_subscription(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        member = await context.bot.get_chat_member(chat_id=CHANNEL, user_id=user_id)
        return member.status in (ChatMember.MEMBER, ChatMember.ADMINISTRATOR, ChatMember.OWNER)
    except Exception as e:
        err = str(e).lower()
        if any(w in err for w in ("inaccessible", "not found", "chat not found")):
            logger.warning("Бот не администратор канала %s!", CHANNEL)
            return True
        return True

def sub_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Подписаться на канал", url=f"https://t.me/{CHANNEL.lstrip('@')}")],
        [InlineKeyboardButton("✅ Я подписался", callback_data="check_sub")],
    ])

def signal_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Ещё сигнал", callback_data="new_signal")],
        [InlineKeyboardButton("🔗 Открыть Pocket Option", url=REF_LINK)],
    ])

def make_signal_text() -> str:
    pair = random.choice(PAIRS)
    icon, direction = random.choice(DIRECTIONS)
    expiry = random.choice(EXPIRATIONS)
    amount = random.choice(AMOUNTS)
    accuracy = random.randint(75, 95)
    now = datetime.now(timezone.utc).strftime("%H:%M UTC")
    line = "─" * 26
    return (
        f"📊 <b>ТОРГОВЫЙ СИГНАЛ</b>\n{line}\n"
        f"💱 Пара: <b>{pair}</b>\n"
        f"📈 Направление: {icon} <b>{direction}</b>\n"
        f"⏱ Экспирация: <b>{expiry}</b>\n"
        f"💰 Сумма входа: <b>{amount}</b>\n"
        f"🎯 Точность: <b>{accuracy}%</b>\n"
        f"🕒 Время: {now}\n{line}\n\n"
        f"🔗 Торговать здесь:\n<a href=\"{REF_LINK}\">{REF_LINK}</a>"
    )

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    save_user(user.id)
    channel_url = f"https://t.me/{CHANNEL.lstrip('@')}"
    await update.message.reply_text(
        f"👋 Привет, <b>{user.first_name}</b>!\n\n"
        f"Я бот для торговых сигналов на <b>Pocket Option</b>.\n\n"
        f"📊 Даю сигналы по валютным парам:\n"
        f"  • Пара (EUR/USD, GBP/JPY и др.)\n"
        f"  • Направление 🔼 ВЫШЕ / 🔽 НИЖЕ\n"
        f"  • Время экспирации\n\n"
        f"🔗 Торговать через мою ссылку:\n<a href=\"{REF_LINK}\">{REF_LINK}</a>\n\n"
        f"Нажмите /signal чтобы получить сигнал.",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 Получить сигнал", callback_data="new_signal")],
            [InlineKeyboardButton("📢 Наш канал", url=channel_url)],
            [InlineKeyboardButton("🔗 Pocket Option", url=REF_LINK)],
        ]),
    )

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    channel_url = f"https://t.me/{CHANNEL.lstrip('@')}"
    await update.message.reply_text(
        "📋 <b>Команды бота:</b>\n\n"
        "/start — Главное меню\n"
        "/signal — Получить торговый сигнал\n"
        "/ref — Реферальная ссылка\n"
        "/help — Это сообщение\n\n"
        f"📢 Канал: <a href=\"{channel_url}\">{CHANNEL}</a>",
        parse_mode=ParseMode.HTML,
    )

async def cmd_signal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not await check_subscription(user.id, context):
        channel_url = f"https://t.me/{CHANNEL.lstrip('@')}"
        await update.message.reply_text(
            f"🔒 <b>Доступ закрыт</b>\n\n"
            f"Подпишитесь на <a href=\"{channel_url}\">{CHANNEL}</a> "
            f"чтобы получать бесплатные сигналы.\n\nПосле подписки нажмите кнопку 👇",
            parse_mode=ParseMode.HTML,
            reply_markup=sub_keyboard(),
        )
        return
    await update.message.reply_text(
        make_signal_text(), parse_mode=ParseMode.HTML, reply_markup=signal_keyboard()
    )

async def cmd_ref(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        f"🔗 <b>Регистрируйтесь на Pocket Option:</b>\n\n"
        f"<a href=\"{REF_LINK}\">{REF_LINK}</a>\n\n"
        f"✅ Бонус при регистрации\n✅ Минимальный депозит $5",
        parse_mode=ParseMode.HTML,
    )

async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📊 Хотите сигнал? Нажмите /signal или кнопку ниже 👇",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 Получить сигнал", callback_data="new_signal")],
        ]),
    )

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user = query.from_user
    subscribed = await check_subscription(user.id, context)
    if query.data == "check_sub":
        if subscribed:
            await query.edit_message_text(
                "✅ Подписка подтверждена!\n\n" + make_signal_text(),
                parse_mode=ParseMode.HTML, reply_markup=signal_keyboard()
            )
        else:
            await query.answer("❌ Вы ещё не подписались!", show_alert=True)
    elif query.data == "new_signal":
        if not subscribed:
            channel_url = f"https://t.me/{CHANNEL.lstrip('@')}"
            await query.edit_message_text(
                f"🔒 Подпишитесь на <a href=\"{channel_url}\">{CHANNEL}</a>.",
                parse_mode=ParseMode.HTML, reply_markup=sub_keyboard()
            )
            return
        await query.edit_message_text(
            make_signal_text(), parse_mode=ParseMode.HTML, reply_markup=signal_keyboard()
        )

async def broadcast(context: ContextTypes.DEFAULT_TYPE) -> None:
    users = load_users()
    if not users:
        return
    text = "🔔 <b>НОВЫЙ СИГНАЛ</b>\n\n" + make_signal_text()
    sent = 0
    for uid in list(users):
        try:
            await context.bot.send_message(
                chat_id=uid, text=text,
                parse_mode=ParseMode.HTML, reply_markup=signal_keyboard()
            )
            sent += 1
        except Forbidden:
            remove_user(uid)
        except Exception as e:
            logger.warning("Ошибка рассылки %d: %s", uid, e)
    logger.info("Рассылка: отправлено %d из %d", sent, len(users))

def main() -> None:
    if not TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN не задан!")
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("signal", cmd_signal))
    app.add_handler(CommandHandler("ref", cmd_ref))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    app.job_queue.run_repeating(
        broadcast,
        interval=BROADCAST_INTERVAL_MINUTES * 60,
        first=BROADCAST_INTERVAL_MINUTES * 60,
    )
    logger.info("Бот запущен. Авто-рассылка каждые %d мин.", BROADCAST_INTERVAL_MINUTES)
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
