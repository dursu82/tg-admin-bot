from aiogram.dispatcher.middlewares.base import BaseMiddleware
from aiogram.types import Message, BotCommand, BotCommandScopeChat

from app.databases import db_service


class AccessMiddleware(BaseMiddleware):
    async def __call__(self, handler, message: Message, data: dict):
        if message.text and message.text.startswith("/"):
            cmd = [BotCommand(command="start", description="Начать работу с ботом"),]
            commands = await db_service.get_user_commands(message.from_user.id)

            # Добавляем команды в меню, соответствующие роли пользователя
            if commands:
                for name, description in commands:
                    cmd.append(BotCommand(command=name, description=description))

            # Устанавливаем меню команд для текущего пользователя
            await message.bot.set_my_commands(
                commands=cmd,
                scope=BotCommandScopeChat(chat_id=message.chat.id)
            )

            # Проверка доступа к команде
            if not message.text.startswith("/start") and \
                (not commands or message.text[1:] not in {name for name, _ in commands}):
                await message.answer("У вас нет доступа к этой команде.")
                return

        return await handler(message, data)  # Продолжаем выполнение, если доступ разрешён
