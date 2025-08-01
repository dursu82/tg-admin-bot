import asyncio
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters import CommandStart, Command
from aiogram import Router
from aiogram.types import Message
import logging

from config import config
from app.handlers import proxy_router, allowlist_router, pbx_router, zabbix_router, wg_router
from app.middlewares import AccessMiddleware
from app.databases import db_service


async def main():
    bot = Bot(token=config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    await db_service.connect()

    start_router = Router()
    common_router = Router()

    @start_router.message(CommandStart())
    async def cmd_start(message: Message):
        await message.answer(f"Your user ID: <b>{message.from_user.id}</b>")

    @common_router.message(Command("help"))
    async def cmd_help(message: Message):
        help_text = "Доступные команды:\n    /start - Начать работу с ботом"
        commands = await db_service.get_user_commands(message.from_user.id)
        if commands:
            for name, description in commands:
                help_text += f"\n    /{name} - {description}"
        await message.reply(help_text)

    # Подключаем роутеры к диспетчеру
    dp.include_router(start_router)
    dp.include_router(common_router)
    dp.include_router(proxy_router)
    dp.include_router(allowlist_router)
    dp.include_router(pbx_router)
    dp.include_router(zabbix_router)
    dp.include_router(wg_router)

    # Подключаем middleware к роутерам
    dp.message.middleware(AccessMiddleware())

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(__name__)

    asyncio.run(main())
