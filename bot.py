"""Telegram-бот: ассистент автора канала с памятью диалога.

Запуск: python bot.py
"""

from __future__ import annotations

import asyncio
import logging
import sys
from logging.handlers import RotatingFileHandler
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import (
    BotCommand,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    TelegramObject,
)
from aiogram.utils.chat_action import ChatActionSender

from api_client import AIClient, AIError
from channel import Channel, ChannelError, build_system_prompt, load_channel
from config import BASE_DIR, EFFORT_LEVELS, ConfigError, Settings, UserParams, load_settings
from context_manager import ContextManager
from text_utils import split_message

log = logging.getLogger("bot")
router = Router()

RESET_PHRASES = {"очистить контекст", "сбросить контекст", "новый диалог"}

HELP_TEXT = """Я ассистент автора канала «{channel}». Пишите задачу обычным сообщением:
«предложи 5 тем на неделю», «напиши пост про выгорание», «сделай короче», «дай другой заголовок».
Я помню последние {limit} сообщений диалога.

Команды:
/reset — очистить контекст (или напишите «очистить контекст»)
/settings — текущие параметры
/model — выбрать модель
/effort — уровень «усилия» модели
/tokens 1000 — max_tokens
/temp 0.7 — temperature 0.0–2.0 (/temp off — по умолчанию модели)
/help — эта справка"""


# ---------- доступ ----------

class AccessMiddleware(BaseMiddleware):
    """Пропускает только пользователей из ALLOWED_USER_IDS: бот тратит ваш баланс."""

    def __init__(self, allowed: frozenset[int]) -> None:
        self.allowed = allowed

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is None or user.id not in self.allowed:
            log.warning("Update from a user outside ALLOWED_USER_IDS ignored")
            return None
        return await handler(event, data)


# ---------- параметры пользователя ----------

class ParamsStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._params: dict[int, UserParams] = {}

    def get(self, user_id: int) -> UserParams:
        if user_id not in self._params:
            self._params[user_id] = UserParams(
                model=self.settings.default_model,
                max_tokens=self.settings.default_max_tokens,
                effort=self.settings.default_effort,
            )
        return self._params[user_id]


def format_settings(p: UserParams, ctx_size: int, ctx_limit: int, channel: Channel) -> str:
    temp = "по умолчанию модели" if p.temperature is None else str(p.temperature)
    return (
        f"Канал: {channel.name}\n"
        f"Модель: {p.model}\n"
        f"effort: {p.effort or 'по умолчанию модели'}\n"
        f"max_tokens: {p.max_tokens}\n"
        f"temperature: {temp}\n"
        f"Контекст: {ctx_size} из {ctx_limit} сообщений"
    )


def keyboard(prefix: str, values: list[str], current: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=("✓ " if v == current else "") + v, callback_data=f"{prefix}:{v}")]
        for v in values
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ---------- команды ----------

@router.message(CommandStart())
@router.message(Command("help"))
async def cmd_help(message: Message, ctx: ContextManager, channel: Channel) -> None:
    await message.answer(HELP_TEXT.format(channel=channel.name, limit=ctx.max_messages))


@router.message(Command("reset"))
@router.message(F.text.func(lambda t: bool(t) and t.strip().lower() in RESET_PHRASES))
async def cmd_reset(message: Message, ctx: ContextManager) -> None:
    ctx.reset(message.from_user.id)
    log.info("Context reset")
    await message.answer("Контекст очищен. Начнём заново.")


@router.message(Command("settings"))
async def cmd_settings(message: Message, ctx: ContextManager, params: ParamsStore,
                       channel: Channel) -> None:
    uid = message.from_user.id
    await message.answer(format_settings(params.get(uid), ctx.size(uid), ctx.max_messages, channel))


@router.message(Command("model"))
async def cmd_model(message: Message, command: CommandObject, params: ParamsStore,
                    settings: Settings) -> None:
    p = params.get(message.from_user.id)
    arg = (command.args or "").strip()
    if arg:
        p.model = arg
        await message.answer(f"Модель: {p.model}")
        return
    await message.answer("Выберите модель:",
                         reply_markup=keyboard("model", list(settings.available_models), p.model))


@router.message(Command("effort"))
async def cmd_effort(message: Message, command: CommandObject, params: ParamsStore) -> None:
    p = params.get(message.from_user.id)
    arg = (command.args or "").strip().lower()
    if arg:
        if arg in ("default", "off", "none"):
            p.effort = None
        elif arg in EFFORT_LEVELS:
            p.effort = arg
        else:
            await message.answer(f"Допустимо: {', '.join(EFFORT_LEVELS)} или default")
            return
        await message.answer(f"effort: {p.effort or 'по умолчанию модели'}")
        return
    await message.answer("Уровень effort:",
                         reply_markup=keyboard("effort", ["default", *EFFORT_LEVELS], p.effort or "default"))


@router.message(Command("tokens"))
async def cmd_tokens(message: Message, command: CommandObject, params: ParamsStore) -> None:
    p = params.get(message.from_user.id)
    arg = (command.args or "").strip()
    if not arg.isdigit() or not 1 <= int(arg) <= 32000:
        await message.answer(f"Сейчас max_tokens = {p.max_tokens}. Пример: /tokens 1000 (1–32000)")
        return
    p.max_tokens = int(arg)
    await message.answer(f"max_tokens: {p.max_tokens}")


@router.message(Command("temp"))
async def cmd_temp(message: Message, command: CommandObject, params: ParamsStore) -> None:
    p = params.get(message.from_user.id)
    arg = (command.args or "").strip().lower().replace(",", ".")
    if arg in ("off", "none", "default"):
        p.temperature = None
        await message.answer("temperature: по умолчанию модели")
        return
    try:
        value = float(arg)
    except ValueError:
        await message.answer("Пример: /temp 0.7 (0.0–2.0) или /temp off")
        return
    if not 0.0 <= value <= 2.0:
        await message.answer("temperature — от 0.0 до 2.0")
        return
    p.temperature = value
    await message.answer(f"temperature: {value}")


@router.callback_query(F.data.startswith("model:"))
async def cb_model(call: CallbackQuery, params: ParamsStore) -> None:
    p = params.get(call.from_user.id)
    p.model = call.data.split(":", 1)[1]
    await call.message.edit_text(f"Модель: {p.model}")
    await call.answer()


@router.callback_query(F.data.startswith("effort:"))
async def cb_effort(call: CallbackQuery, params: ParamsStore) -> None:
    p = params.get(call.from_user.id)
    value = call.data.split(":", 1)[1]
    p.effort = None if value == "default" else value
    await call.message.edit_text(f"effort: {p.effort or 'по умолчанию модели'}")
    await call.answer()


# ---------- диалог ----------

@router.message(F.text & ~F.text.startswith("/"))
async def on_text(message: Message, bot: Bot, ctx: ContextManager, params: ParamsStore,
                  ai: AIClient, system_prompt: str) -> None:
    uid = message.from_user.id
    p = params.get(uid)
    ctx.add_user(uid, message.text)

    try:
        async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
            result = await ai.complete(
                messages=ctx.get(uid),
                system=system_prompt,
                model=p.model,
                max_tokens=p.max_tokens,
                effort=p.effort,
                temperature=p.temperature,
            )
    except AIError as exc:
        ctx.rollback_last_user(uid)
        await message.answer(f"⚠️ {exc.user_message}")
        return

    if not result.text:
        ctx.rollback_last_user(uid)
        await message.answer(f"Модель вернула пустой ответ (stop_reason: {result.stop_reason}).")
        return

    ctx.add_assistant(uid, result.text)
    log.info("Context size after reply: %d", ctx.size(uid))

    for chunk in split_message(result.text):
        await message.answer(chunk)
    if result.stop_reason == "max_tokens":
        await message.answer(f"✂️ Ответ обрезан по max_tokens ({p.max_tokens}). "
                             "Напишите «продолжи» или увеличьте /tokens.")


@router.message(F.text.startswith("/"))
async def on_unknown_command(message: Message) -> None:
    await message.answer("Не знаю такой команды. Список — /help")


@router.message()
async def on_other(message: Message) -> None:
    # Фото, стикеры, голосовые и прочее не должны ронять бота
    await message.answer("Пока понимаю только текст — опишите задачу словами.")


# ---------- запуск ----------

def setup_logging(level: str) -> None:
    logs_dir = BASE_DIR / "logs"
    logs_dir.mkdir(exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    file_handler = RotatingFileHandler(logs_dir / "bot.log", maxBytes=1_000_000,
                                       backupCount=3, encoding="utf-8")
    file_handler.setFormatter(fmt)
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    logging.basicConfig(level=getattr(logging, level, logging.INFO),
                        handlers=[console, file_handler])
    # httpx на INFO печатает URL каждого запроса — держим его тише
    for noisy in ("httpx", "httpx2", "httpcore", "aiohttp.access", "openai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


async def main() -> None:
    try:
        settings = load_settings()
        channel = load_channel(settings.channel_file)
    except (ConfigError, ChannelError) as exc:
        print(f"Ошибка настройки: {exc}", file=sys.stderr)
        sys.exit(1)

    setup_logging(settings.log_level)
    log.info("Starting: channel=%s model=%s allowed_users=%d context_limit=%d",
             channel.name, settings.default_model, len(settings.allowed_user_ids),
             settings.context_max_messages)

    bot = Bot(token=settings.bot_token)
    ai = AIClient.from_settings(settings)
    dp = Dispatcher()
    access = AccessMiddleware(settings.allowed_user_ids)
    dp.message.outer_middleware(access)
    dp.callback_query.outer_middleware(access)
    dp.include_router(router)

    # Бот работает через опрос (polling): если у токена остался вебхук от прошлого
    # проекта, Telegram отвечает Conflict — снимаем его. Накопленные сообщения не трогаем.
    webhook = await bot.get_webhook_info()
    if webhook.url:
        await bot.delete_webhook(drop_pending_updates=False)
        log.warning("Webhook was set for this token and has been removed (polling mode)")

    await bot.set_my_commands([
        BotCommand(command="reset", description="Очистить контекст"),
        BotCommand(command="settings", description="Текущие параметры"),
        BotCommand(command="model", description="Выбрать модель"),
        BotCommand(command="effort", description="Уровень effort"),
        BotCommand(command="tokens", description="max_tokens"),
        BotCommand(command="temp", description="temperature"),
        BotCommand(command="help", description="Справка"),
    ])

    try:
        await dp.start_polling(
            bot,
            settings=settings,
            channel=channel,
            system_prompt=build_system_prompt(channel),
            ctx=ContextManager(settings.context_max_messages),
            params=ParamsStore(settings),
            ai=ai,
        )
    finally:
        await ai.close()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
