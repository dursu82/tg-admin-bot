from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from utils import is_valid_ipv4, zwip
from scripts.allowlist import get_db_connection
from app.databases import db_service


allowlist_router = Router()

# Определяем состояния
class StateData(StatesGroup):
    allowlist = State()


@allowlist_router.message(Command("allowlist"))
async def cmd_allowlist(message: Message, state: FSMContext):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="GW", callback_data="allowlist_GW"),
            InlineKeyboardButton(text="PBX", callback_data="allowlist_PBX")
        ]
    ])
    await message.answer(text="Добавить IP:", reply_markup=keyboard)


@allowlist_router.callback_query(F.data.startswith("allowlist_"))
async def process_callback_allowlist(callback: CallbackQuery, state: FSMContext):
    location = callback.data.split("_", 1)[1]
    await state.update_data(location=location)
    await state.set_state(StateData.allowlist)
    await callback.message.edit_text("Введите IPv4-адрес:")
    await callback.answer()


@allowlist_router.message(StateData.allowlist)
async def allowlist(message: Message, state: FSMContext):
    def build_keyboard():
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="ДА", callback_data=f"yes_{location}_{message.text}"),
                InlineKeyboardButton(text="НЕТ", callback_data="no_{location}_")
            ]
        ])

    if is_valid_ipv4(message.text):
        location = (await state.get_data()).get("location")
        if location == "GW":
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT * from blocklist where src = %s", (message.text,))
                records = cursor.fetchall()
                if records:
                    keyboard = build_keyboard()
                    await message.answer(f"Добавить в {location} allowlist?", reply_markup=keyboard)
                else:
                    await message.answer("В blocklist-e нет.")
            except Exception as e:
                await message.answer(f"Ошибка при выборке: {str(e)}")
            finally:
                cursor.close()
                conn.close()
        elif location == "PBX":
            if await db_service.pbx_ip_allowed(ip=message.text):
                await message.answer(f"ℹ️ IP адрес <b>{zwip(message.text)}</b> уже есть в разрешенных.")
            else:
                keyboard = build_keyboard()
                await message.answer(f"Добавить в {location} allowlist?", reply_markup=keyboard)
    else:
        await message.reply(f"❌ Не верно указан IP-адрес")

    await state.clear()  # Сбрасываем состояние


# Обработка нажатия кнопок
@allowlist_router.callback_query(F.data.startswith(("yes_", "no_")))
async def process_callback(callback: CallbackQuery):
    # Разделяем callback_data на команду, куда и ip
    action, location, ip = callback.data.split("_", 2)

    if action == "yes" and location == "GW":
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("INSERT INTO logDB2.allowlist (src) VALUES (%s);", (ip,))
            cursor.execute("DELETE FROM logDB2.blocklist WHERE src = %s;", (ip,))
            conn.commit()
            await callback.message.edit_text(f"{ip} добавлен в {location} allowlist")
        except Exception as e:
            await callback.message.edit_text(f"Ошибка при добавлении: {str(e)}")
        finally:
            cursor.close()
            conn.close()
    elif action == "yes" and location == "PBX":
        if await db_service.pbx_allow_ip(ip=ip, user_id=callback.from_user.id):
            await callback.message.edit_text(f"{ip} добавлен в {location} allowlist")
        else:
            await callback.message.edit_text(f"Ошибка при добавлении.")
    elif action == "no":
        await callback.message.edit_text("Действие отменено")

    await callback.answer()
