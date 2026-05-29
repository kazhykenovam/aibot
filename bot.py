"""
FactumAudit Telegram Bot
ИИ-тестировщик и консультант по веб-разработке

Команды:
  /start   — приветствие
  /audit   — запустить аудит сайта по URL
  /html    — отправить HTML для анализа
  /seo     — SEO-советы для URL
  /ux      — UX-советы для URL
  /help    — справка
  /cancel  — отменить текущее действие

Просто напиши вопрос — бот ответит как веб-консультант.
"""

import asyncio
import logging
import os
import re
from enum import Enum, auto

import anthropic
from anthropic import AsyncAnthropic
from dotenv import load_dotenv
from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

load_dotenv()

# ── CONFIG ──────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN  = os.environ["TELEGRAM_BOT_TOKEN"] 
ANTHROPIC_KEY   = os.environ["ANTHROPIC_API_KEY"]
MODEL           = "claude-sonnet-4-20250514"

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

client = AsyncAnthropic(api_key=ANTHROPIC_KEY)

# ── CONVERSATION STATES ──────────────────────────────────────────────────────
class State(Enum):
    WAITING_URL_AUDIT  = auto()
    WAITING_URL_SEO    = auto()
    WAITING_URL_UX     = auto()
    WAITING_HTML       = auto()
    CHOOSING_CHECKS    = auto()


# ── HELPERS ─────────────────────────────────────────────────────────────────
URL_RE = re.compile(r"https?://[^\s]+")

def is_url(text: str) -> bool:
    return bool(URL_RE.match(text.strip()))

def escape_md(text: str) -> str:
    """Escape MarkdownV2 special chars."""
    for ch in r"_*[]()~`>#+-=|{}.!\\":
        text = text.replace(ch, f"\\{ch}")
    return text

async def send_typing(update: Update):
    await update.effective_chat.send_action(ChatAction.TYPING)

async def ask_claude(prompt: str, system: str = "") -> str:
    """Call Claude and return plain text response."""
    kwargs = dict(
        model=MODEL,
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )
    if system:
        kwargs["system"] = system
    msg = await client.messages.create(**kwargs)
    return msg.content[0].text


SYSTEM_CONSULTANT = """Ты — опытный веб-разработчик и консультант по UI/UX, SEO и производительности.
Отвечай на русском языке. Давай конкретные, практические советы.
Используй форматирование Telegram: *жирный*, _курсив_, `код`, блоки кода.
Будь краток — максимум 600 слов. Структурируй ответ с emoji-заголовками."""

SYSTEM_AUDITOR = """Ты — старший QA-инженер и веб-аудитор. Анализируй сайты профессионально.
Отвечай СТРОГО на русском. Используй Telegram Markdown: *жирный*, `код`.
Структура ответа:
📊 *Общая оценка* (число /100 и вердикт)
🔴 *Критичные проблемы* — список
🟡 *Предупреждения* — список  
✅ *Хорошие практики* — список
💡 *Топ-3 рекомендации* — конкретные шаги

Максимум 800 слов. Будь конкретен: называй теги, атрибуты, значения."""


# ── AUDIT HELPERS ────────────────────────────────────────────────────────────
async def run_full_audit(url: str, checks: list[str]) -> str:
    checks_str = ", ".join(checks)
    prompt = f"""Проведи детальный аудит сайта: {url}

Категории проверки: {checks_str}

Для каждой категории:
- Оцени от 0 до 100
- Найди конкретные проблемы
- Дай рекомендации

Используй Telegram Markdown форматирование."""
    return await ask_claude(prompt, SYSTEM_AUDITOR)


async def run_html_audit(html: str) -> str:
    prompt = f"""Проанализируй этот HTML-код сайта по всем параметрам:
UI/UX, доступность, SEO, производительность, функциональность.

HTML:
```html
{html[:8000]}
```

Найди конкретные проблемы в коде и дай рекомендации."""
    return await ask_claude(prompt, SYSTEM_AUDITOR)


async def run_seo_audit(url: str) -> str:
    prompt = f"""Проведи SEO-аудит сайта: {url}

Проверь:
- Title и meta description (оптимальная длина, ключевые слова)
- Заголовки H1-H6 (структура, количество)
- Open Graph и Twitter Cards
- Canonical URL и robots-директивы
- Скорость загрузки и Core Web Vitals
- Мобильная адаптация
- Внутренняя перелинковка
- Структурированные данные (schema.org)

Дай конкретные рекомендации с примерами кода где нужно."""
    return await ask_claude(prompt, SYSTEM_AUDITOR)


async def run_ux_audit(url: str) -> str:
    prompt = f"""Проведи UX-аудит сайта: {url}

Оцени:
- Первый экран (above the fold): понятен ли оффер за 5 секунд?
- Навигация: интуитивна ли структура меню?
- CTA-кнопки: заметны ли, ясен ли призыв к действию?
- Формы: сколько полей, есть ли валидация?
- Доступность (a11y): контрастность, alt-тексты, табуляция
- Мобильный опыт: размер кнопок, отступы, читаемость
- Доверие: есть ли отзывы, контакты, SSL?

Дай конкретные рекомендации по улучшению."""
    return await ask_claude(prompt, SYSTEM_AUDITOR)


# ── KEYBOARDS ────────────────────────────────────────────────────────────────
def checks_keyboard(selected: set) -> InlineKeyboardMarkup:
    options = [
        ("uiux",  "UI/UX"),
        ("func",  "Функциональность"),
        ("perf",  "Производительность"),
        ("seo",   "SEO"),
    ]
    rows = []
    for key, label in options:
        check = "✅" if key in selected else "⬜"
        rows.append([InlineKeyboardButton(f"{check} {label}", callback_data=f"check_{key}")])
    rows.append([
        InlineKeyboardButton("🚀 Запустить аудит", callback_data="run_audit"),
        InlineKeyboardButton("❌ Отмена", callback_data="cancel"),
    ])
    return InlineKeyboardMarkup(rows)


def main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔍 Аудит сайта",  callback_data="cmd_audit"),
            InlineKeyboardButton("📄 HTML-анализ",  callback_data="cmd_html"),
        ],
        [
            InlineKeyboardButton("📈 SEO-анализ",   callback_data="cmd_seo"),
            InlineKeyboardButton("🎨 UX-советы",    callback_data="cmd_ux"),
        ],
    ])


# ── HANDLERS ─────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 *Привет\\! Я FactumAudit Bot* — ИИ\\-тестировщик и консультант по веб\\-разработке\\.\n\n"
        "Что умею:\n"
        "🔍 Аудит сайта по URL — UI/UX, SEO, производительность\n"
        "📄 Анализ HTML\\-кода — найду проблемы прямо в коде\n"
        "📈 SEO\\-анализ — мета\\-теги, структура, Open Graph\n"
        "🎨 UX\\-советы — навигация, CTA, доступность\n"
        "💬 Консультации — задай любой вопрос по веб\\-разработке\n\n"
        "Выбери действие или просто напиши вопрос\\:"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=main_keyboard())


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 *Справка*\n\n"
        "/audit — аудит сайта по URL\n"
        "/html — анализ HTML\\-кода\n"
        "/seo — SEO\\-анализ сайта\n"
        "/ux — UX\\-советы\n"
        "/cancel — отменить действие\n\n"
        "💬 *Или просто напиши вопрос* — отвечу как веб\\-консультант\\.\n\n"
        "_Примеры вопросов:_\n"
        "• Как ускорить загрузку сайта?\n"
        "• Что такое Core Web Vitals?\n"
        "• Как сделать адаптивное меню?"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)


async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await update.message.reply_text("❌ Действие отменено\\.", parse_mode=ParseMode.MARKDOWN_V2, reply_markup=main_keyboard())
    return ConversationHandler.END


# ── AUDIT FLOW ───────────────────────────────────────────────────────────────
async def cmd_audit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["checks"] = {"uiux", "func", "perf", "seo"}
    msg = "🔍 *Аудит сайта*\n\nВыбери категории проверки и нажми *Запустить аудит*\\:"
    keyboard = checks_keyboard(ctx.user_data["checks"])
    if update.message:
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=keyboard)
    else:
        await update.callback_query.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=keyboard)
    return State.CHOOSING_CHECKS


async def callback_check_toggle(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    key = query.data.replace("check_", "")
    checks = ctx.user_data.setdefault("checks", {"uiux", "func", "perf", "seo"})
    if key in checks:
        checks.discard(key)
    else:
        checks.add(key)
    await query.edit_message_reply_markup(reply_markup=checks_keyboard(checks))
    return State.CHOOSING_CHECKS


async def callback_run_audit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    checks = ctx.user_data.get("checks", {"uiux", "func", "perf", "seo"})
    if not checks:
        await query.answer("Выбери хотя бы одну категорию!", show_alert=True)
        return State.CHOOSING_CHECKS

    ctx.user_data["pending_checks"] = checks
    await query.edit_message_text(
        "🌐 Отправь URL сайта для аудита\\.\n_Пример: https://example\\.com_",
        parse_mode=ParseMode.MARKDOWN_V2
    )
    return State.WAITING_URL_AUDIT


async def receive_url_audit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    if not is_url(url):
        await update.message.reply_text("⚠️ Это не похоже на URL\\. Пришли адрес вида `https://example\\.com`", parse_mode=ParseMode.MARKDOWN_V2)
        return State.WAITING_URL_AUDIT

    checks = ctx.user_data.get("pending_checks", {"uiux", "func", "perf", "seo"})
    labels = {"uiux": "UI/UX", "func": "Функциональность", "perf": "Производительность", "seo": "SEO"}
    checks_str = ", ".join(labels[c] for c in checks if c in labels)

    msg = await update.message.reply_text(f"⏳ Анализирую `{url}`\\.\\.\\.\n_Категории: {escape_md(checks_str)}_\n\nОбычно занимает 15\\-30 секунд\\.", parse_mode=ParseMode.MARKDOWN_V2)
    await send_typing(update)

    try:
        result = await run_full_audit(url, list(labels[c] for c in checks if c in labels))
        await msg.delete()
        await update.message.reply_text(result, parse_mode=ParseMode.MARKDOWN, reply_markup=main_keyboard())
    except Exception as e:
        logger.error(f"Audit error: {e}")
        await msg.edit_text("❌ Ошибка при анализе\\. Попробуй ещё раз\\.\\.", parse_mode=ParseMode.MARKDOWN_V2)

    ctx.user_data.clear()
    return ConversationHandler.END


# ── HTML FLOW ────────────────────────────────────────────────────────────────
async def cmd_html(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = "📄 *Анализ HTML\\-кода*\n\nОтправь HTML\\-код страницы \\(можно прямо в сообщении или файлом `.html`\\)\\:"
    if update.message:
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)
    else:
        await update.callback_query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)
    return State.WAITING_HTML


async def receive_html_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    html = update.message.text.strip()
    if len(html) < 20:
        await update.message.reply_text("⚠️ Слишком короткий код\\. Пришли полный HTML страницы\\.", parse_mode=ParseMode.MARKDOWN_V2)
        return State.WAITING_HTML

    msg = await update.message.reply_text("⏳ Анализирую HTML\\.\\.\\.", parse_mode=ParseMode.MARKDOWN_V2)
    await send_typing(update)
    try:
        result = await run_html_audit(html)
        await msg.delete()
        await update.message.reply_text(result, parse_mode=ParseMode.MARKDOWN, reply_markup=main_keyboard())
    except Exception as e:
        logger.error(f"HTML audit error: {e}")
        await msg.edit_text("❌ Ошибка при анализе\\.", parse_mode=ParseMode.MARKDOWN_V2)

    return ConversationHandler.END


async def receive_html_file(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc.file_name.endswith((".html", ".htm")):
        await update.message.reply_text("⚠️ Пришли файл с расширением `.html`\\.", parse_mode=ParseMode.MARKDOWN_V2)
        return State.WAITING_HTML

    file = await doc.get_file()
    content = await file.download_as_bytearray()
    html = content.decode("utf-8", errors="ignore")

    msg = await update.message.reply_text(f"⏳ Анализирую файл `{escape_md(doc.file_name)}`\\.\\.\\.", parse_mode=ParseMode.MARKDOWN_V2)
    await send_typing(update)
    try:
        result = await run_html_audit(html)
        await msg.delete()
        await update.message.reply_text(result, parse_mode=ParseMode.MARKDOWN, reply_markup=main_keyboard())
    except Exception as e:
        logger.error(f"HTML file audit error: {e}")
        await msg.edit_text("❌ Ошибка при анализе файла\\.", parse_mode=ParseMode.MARKDOWN_V2)

    return ConversationHandler.END


# ── SEO FLOW ─────────────────────────────────────────────────────────────────
async def cmd_seo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = "📈 *SEO\\-анализ*\n\nОтправь URL сайта\\:"
    if update.message:
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)
    else:
        await update.callback_query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)
    return State.WAITING_URL_SEO


async def receive_url_seo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    if not is_url(url):
        await update.message.reply_text("⚠️ Пришли URL вида `https://example\\.com`", parse_mode=ParseMode.MARKDOWN_V2)
        return State.WAITING_URL_SEO

    msg = await update.message.reply_text(f"⏳ SEO\\-анализ `{escape_md(url)}`\\.\\.\\.", parse_mode=ParseMode.MARKDOWN_V2)
    await send_typing(update)
    try:
        result = await run_seo_audit(url)
        await msg.delete()
        await update.message.reply_text(result, parse_mode=ParseMode.MARKDOWN, reply_markup=main_keyboard())
    except Exception as e:
        logger.error(f"SEO audit error: {e}")
        await msg.edit_text("❌ Ошибка при SEO\\-анализе\\.", parse_mode=ParseMode.MARKDOWN_V2)

    return ConversationHandler.END


# ── UX FLOW ──────────────────────────────────────────────────────────────────
async def cmd_ux(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = "🎨 *UX\\-советы*\n\nОтправь URL сайта\\:"
    if update.message:
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)
    else:
        await update.callback_query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)
    return State.WAITING_URL_UX


async def receive_url_ux(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    if not is_url(url):
        await update.message.reply_text("⚠️ Пришли URL вида `https://example\\.com`", parse_mode=ParseMode.MARKDOWN_V2)
        return State.WAITING_URL_UX

    msg = await update.message.reply_text(f"⏳ UX\\-анализ `{escape_md(url)}`\\.\\.\\.", parse_mode=ParseMode.MARKDOWN_V2)
    await send_typing(update)
    try:
        result = await run_ux_audit(url)
        await msg.delete()
        await update.message.reply_text(result, parse_mode=ParseMode.MARKDOWN, reply_markup=main_keyboard())
    except Exception as e:
        logger.error(f"UX audit error: {e}")
        await msg.edit_text("❌ Ошибка при UX\\-анализе\\.", parse_mode=ParseMode.MARKDOWN_V2)

    return ConversationHandler.END


# ── FREE CHAT (консультант) ───────────────────────────────────────────────────
async def free_chat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Отвечает на произвольные вопросы по веб-разработке."""
    question = update.message.text.strip()

    # Если прислали просто URL без команды — предложим меню
    if is_url(question):
        await update.message.reply_text(
            f"🌐 Вижу URL\\: `{escape_md(question)}`\n\nЧто сделать?",
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🔍 Полный аудит",  callback_data=f"quick_audit|{question}"),
                    InlineKeyboardButton("📈 SEO",            callback_data=f"quick_seo|{question}"),
                    InlineKeyboardButton("🎨 UX",             callback_data=f"quick_ux|{question}"),
                ]
            ])
        )
        return

    msg = await update.message.reply_text("💭 Думаю\\.\\.\\.", parse_mode=ParseMode.MARKDOWN_V2)
    await send_typing(update)

    try:
        answer = await ask_claude(question, SYSTEM_CONSULTANT)
        await msg.delete()
        await update.message.reply_text(answer, parse_mode=ParseMode.MARKDOWN, reply_markup=main_keyboard())
    except Exception as e:
        logger.error(f"Free chat error: {e}")
        await msg.edit_text("❌ Ошибка\\. Попробуй ещё раз\\.", parse_mode=ParseMode.MARKDOWN_V2)


# ── QUICK ACTIONS (inline кнопки из free chat) ───────────────────────────────
async def callback_quick_action(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action, url = query.data.split("|", 1)

    if action == "quick_audit":
        msg = await query.message.reply_text(f"⏳ Полный аудит `{escape_md(url)}`\\.\\.\\.", parse_mode=ParseMode.MARKDOWN_V2)
        result = await run_full_audit(url, ["UI/UX", "Функциональность", "Производительность", "SEO"])
    elif action == "quick_seo":
        msg = await query.message.reply_text(f"⏳ SEO\\-анализ `{escape_md(url)}`\\.\\.\\.", parse_mode=ParseMode.MARKDOWN_V2)
        result = await run_seo_audit(url)
    else:  # quick_ux
        msg = await query.message.reply_text(f"⏳ UX\\-анализ `{escape_md(url)}`\\.\\.\\.", parse_mode=ParseMode.MARKDOWN_V2)
        result = await run_ux_audit(url)

    await msg.delete()
    await query.message.reply_text(result, parse_mode=ParseMode.MARKDOWN, reply_markup=main_keyboard())


# ── CALLBACK ROUTER ───────────────────────────────────────────────────────────
async def callback_router(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "cmd_audit":
        return await cmd_audit(update, ctx)
    elif data == "cmd_html":
        return await cmd_html(update, ctx)
    elif data == "cmd_seo":
        return await cmd_seo(update, ctx)
    elif data == "cmd_ux":
        return await cmd_ux(update, ctx)
    elif data == "cancel":
        ctx.user_data.clear()
        await query.edit_message_text("❌ Отменено\\.", parse_mode=ParseMode.MARKDOWN_V2)
        return ConversationHandler.END


# ── APPLICATION ───────────────────────────────────────────────────────────────
def build_app() -> Application:
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Conversation: полный аудит с выбором категорий
    audit_conv = ConversationHandler(
        entry_points=[
            CommandHandler("audit", cmd_audit),
            CallbackQueryHandler(cmd_audit, pattern="^cmd_audit$"),
        ],
        states={
            State.CHOOSING_CHECKS: [
                CallbackQueryHandler(callback_check_toggle, pattern="^check_"),
                CallbackQueryHandler(callback_run_audit,    pattern="^run_audit$"),
                CallbackQueryHandler(lambda u, c: ConversationHandler.END, pattern="^cancel$"),
            ],
            State.WAITING_URL_AUDIT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_url_audit),
            ],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        per_message=False,
    )

    # Conversation: HTML-анализ
    html_conv = ConversationHandler(
        entry_points=[
            CommandHandler("html", cmd_html),
            CallbackQueryHandler(cmd_html, pattern="^cmd_html$"),
        ],
        states={
            State.WAITING_HTML: [
                MessageHandler(filters.Document.ALL, receive_html_file),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_html_text),
            ],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        per_message=False,
    )

    # Conversation: SEO
    seo_conv = ConversationHandler(
        entry_points=[
            CommandHandler("seo", cmd_seo),
            CallbackQueryHandler(cmd_seo, pattern="^cmd_seo$"),
        ],
        states={
            State.WAITING_URL_SEO: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_url_seo),
            ],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        per_message=False,
    )

    # Conversation: UX
    ux_conv = ConversationHandler(
        entry_points=[
            CommandHandler("ux", cmd_ux),
            CallbackQueryHandler(cmd_ux, pattern="^cmd_ux$"),
        ],
        states={
            State.WAITING_URL_UX: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_url_ux),
            ],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        per_message=False,
    )

    # Register handlers
    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("help",   cmd_help))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(audit_conv)
    app.add_handler(html_conv)
    app.add_handler(seo_conv)
    app.add_handler(ux_conv)
    app.add_handler(CallbackQueryHandler(callback_quick_action, pattern="^quick_"))
    app.add_handler(CallbackQueryHandler(callback_router))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, free_chat))

    return app


async def post_init(app: Application):
    await app.bot.set_my_commands([
        BotCommand("start",  "🚀 Начать работу"),
        BotCommand("audit",  "🔍 Аудит сайта по URL"),
        BotCommand("html",   "📄 Анализ HTML-кода"),
        BotCommand("seo",    "📈 SEO-анализ"),
        BotCommand("ux",     "🎨 UX-советы"),
        BotCommand("help",   "📖 Справка"),
        BotCommand("cancel", "❌ Отменить действие"),
    ])


def main():
    app = build_app()
    app.post_init = post_init
    logger.info("FactumAudit Bot запущен...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
