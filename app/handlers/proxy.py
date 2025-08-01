import asyncio
from aiogram import Router, F
from aiogram.enums import ChatAction
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from utils import is_valid_ipv4, zwip
from config import config
from scripts.proxy import squid_add_port


proxy_router = Router()

class StateData(StatesGroup):
    proxy_text = State()


@proxy_router.message(Command("proxy"))
async def cmd_proxy(message: Message, state: FSMContext):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Squid: Добавить порт", callback_data="proxy_squid_new_port")]
#        [InlineKeyboardButton(text="external proxy", callback_data="proxy_external")],
    ])
    await message.answer(text="Выберите действие:", reply_markup=keyboard)


@proxy_router.callback_query(F.data.startswith("proxy_"))
async def process_callback_proxy(callback: CallbackQuery, state: FSMContext):
    action = callback.data.split("_", 1)[1:]

    if action[0] == "squid_new_port":
        buttons = [
            InlineKeyboardButton(text=".".join(proxy.split('.')[2:]), callback_data=f"proxy_{proxy}")
            for proxy in config.proxy_local
        ]
        inline_keyboard = [buttons[i:i + 4] for i in range(0, len(buttons), 4)]
        keyboard = InlineKeyboardMarkup(inline_keyboard=inline_keyboard)
        await callback.message.edit_text(text="Выберите прокси <b>192.168.</b>", reply_markup=keyboard)
    elif is_valid_ipv4(action[0]):
        await state.update_data(selected_ip=action[0])
        await state.set_state(StateData.proxy_text)
        await callback.message.edit_text(f"<b>{zwip(action[0])}</b>\nУкажите прокси &lt;IP:PORT&gt;:")
        await callback.answer()


@proxy_router.message(StateData.proxy_text)
async def process_proxy_text(message: Message, state: FSMContext):
    selected_ip = (await state.get_data()).get("selected_ip")
    proxies = message.text.split()

    error = ""
    for item in proxies:
        ip_port = item.split(":")
        if (
                len(ip_port) != 2 or "" in ip_port or
                not is_valid_ipv4(ip_port[0]) or
                not ip_port[1].isdigit() or not 1024 <= int(ip_port[1]) <= 65535
        ):
            error += f"{zwip(item)} ‒ ❌ Неверный IP:PORT\n"

    if error:
        await message.answer(f"<b>{zwip(selected_ip)}</b>:\n\n{error}")
    else:
        # Периодическая отправка TYPING во время выполнения
        async def send_typing():
            while True:
                await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)
                await asyncio.sleep(3)

        # Запускаем TYPING в фоне
        typing_task = asyncio.create_task(send_typing())

        result = await squid_add_port(selected_ip," ".join(set(proxies)))

        # Отменяем TYPING
        typing_task.cancel()

        if result.squid:
            response = f"<b>Squid {zwip(selected_ip)}</b>:\n"
            for item in result.squid:
                response += f"{zwip(item.ip)}:{item.port} ‒ "
                if item.status == '1':
                    response += f"<b>{item.port2}</b> ✅\n"
                elif item.status == '0':
                    response += f"используется на порту <b>{item.port2}</b> ❌\n"
            await message.answer(f"{response}")
        else:
            await message.answer(result.error)

    await state.clear()
