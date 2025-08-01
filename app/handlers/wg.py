import pyotp
import json
import iuliia
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from utils import is_valid_ipv4
from config import config
from scripts.wg import (
    wg_get_users, wg_get_user_ips, wg_get_user_config, wg_set_del, wg_set_add, wg_del_user, wg_add_user)


wg_router = Router()


class StateData(StatesGroup):
    waiting_for_2FA = State()
    waiting_for_yes_no = State()
    waiting_for_ip = State()
    waiting_for_name = State()


def cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🚫 Отмена", callback_data="cancel")
        ]
    ])


def yes_no_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="ДА", callback_data="yes"),
            InlineKeyboardButton(text="НЕТ", callback_data="no")
        ]
    ])


def verify_totp_code(user_code: str) -> bool:
    """Проверяет введенный пользователем TOTP код"""
    secret = config.TOTP_SECRET
    totp = pyotp.TOTP(secret)
    return totp.verify(user_code, valid_window=1)  # допускаем погрешность в 1 интервал (30 сек)


async def request_2fa(callback: CallbackQuery, state: FSMContext,
                      action: str = None, user: str = None, ip: str = None):
    """Запрашивает 2FA код у пользователя"""
    await state.update_data(action=action, user=user, ip=ip)
    await state.set_state(StateData.waiting_for_2FA)
    await callback.message.edit_text(
        f"🔐 Для выполнения действия требуется 2FA аутентификация.\n" +
        f"Введите код из приложения аутентификатора:\n\n",
        reply_markup=cancel_keyboard()
    )


# Обработчик ввода 2FA кода
@wg_router.message(StateData.waiting_for_2FA)
async def process_2fa_code(message: Message, state: FSMContext):
    code = message.text.strip()
    # Получаем данные и текущие попытки
    data = await state.get_data()
    attempts = data.get("attempts", 2)
    attempts -= 1
    await state.update_data(attempts=attempts)
    # Проверяем формат кода (должен быть 6 цифр)
    if not code.isdigit() or len(code) != 6:
        if attempts:
            await message.answer("❌ Код должен состоять из 6 цифр. Попробуйте еще раз:")
        else:
            await message.answer("🚫 Действие отменено. Начните заново.")
            await state.clear()
        return

    if verify_totp_code(code):
        action = data.get("action")
        user = data.get("user")
        ip = data.get("ip")
        # Выполняем защищенное действие
        if action == "add":
            chainset = data.get("chainset")
            await add_user(message, user, chainset)
        elif action == "del":
            await del_user(message, user)
        elif action == "set_add":
            await set_add(message, user, ip)
        elif action == "set_del":
            await set_del(message, user, ip)
        elif action == "config_show":
            await config_show(message, user)
        elif action == "config_update":
            await config_show(message, user, update=True)
        await state.clear()
    else:
        if attempts:
            await message.answer("❌ Неверный код. Попробуйте еще раз:")
        else:
            await message.answer("🚫 Действие отменено. Начните заново.")
            await state.clear()


# Обработчик ввода IP
@wg_router.message(StateData.waiting_for_ip)
async def process_ip(message: Message, state: FSMContext):
    ip = message.text.strip()
    # Получаем данные и текущие попытки
    data = await state.get_data()
    attempts = data.get("attempts", 2)
    attempts -= 1
    await state.update_data(attempts=attempts)
    if not is_valid_ipv4(ip):
        if attempts:
            await message.answer("❌ Неверный IP адрес. Попробуйте еще раз:")
        else:
            await message.answer("🚫 Действие отменено. Начните заново.")
            await state.clear()
        return

    # Проверка ip
    user = data.get("user")
    result = await wg_get_user_ips(name=user)
    try:
        wg_user_ips = json.loads(result.output)
        if wg_user_ips and ip in wg_user_ips:
            await message.answer(f"У пользователя <code>{user}</code> уже есть доступ к <code>{ip}</code>.")
            await state.clear()
        else:
            await state.update_data(ip=ip)
            await state.set_state(StateData.waiting_for_yes_no)
            await message.answer(
                f"➕ Добавить доступ к <code>{ip}</code> для <code>{user}</code>:",
                reply_markup=yes_no_keyboard()
            )
    except Exception as e:
        if result.error:
            await message.answer(f"❌ {result.error}")
        else:
            await message.answer(f"❌ {e}")


# Обработчик ввода имени
@wg_router.message(StateData.waiting_for_name)
async def process_name(message: Message, state: FSMContext):
    name = message.text.strip()
    # Получаем данные и текущие попытки
    data = await state.get_data()
    attempts = data.get("attempts", 2)
    attempts -= 1
    await state.update_data(attempts=attempts)
    if not len(name.split()) == 2:
        if attempts:
            await message.answer("❗ Введите <b>ровно два слова</b> — имя и фамилию,\nнапример: <code>Олег Иванов</code>")
        else:
            await message.answer("🚫 Действие отменено. Начните заново.")
            await state.clear()
        return

    # Проверка имени
    name = iuliia.TELEGRAM.translate(name)
    result = await wg_get_users()
    try:
        wg_users = json.loads(result.output)
        if wg_users and name in [item['name'] for item in wg_users]:
            await message.answer(f"Пользователь <code>{name}</code> уже есть.")
            await state.clear()
        else:
            chainset = name.split()[0][0].lower() + name.split()[1].lower()
            await state.update_data(action="add",user=name,chainset=chainset)
            await state.set_state(StateData.waiting_for_yes_no)
            await message.answer(
                f"➕ Добавить пользователя <code>{name}, {chainset}</code>:",
                reply_markup=yes_no_keyboard()
            )
    except Exception as e:
        if result.error:
            await message.answer(f"❌ {result.error}")
        else:
            await message.answer(f"❌ {e}")


# Функции выполнения защищенных действий
async def add_user(message, user, chainset):
    result = await wg_add_user(name=user,chainset=chainset)
    try:
        config_data = json.loads(result.output)
        await message.answer(
            f"📄 Конфигурация пользователя\n<b>{user}</b>:\n\n" +
            f"<code># {config_data['Peer']}\n" +
            f"[Interface]\n" +
            f"PrivateKey = {config_data['PrivateKey']}\n" +
            f"Address = {config_data['ip']}/32\n\n" +
            f"[Peer]\n" +
            f"PublicKey = {config.WG_PublicKey}\n" +
            f"PresharedKey = {config_data['PresharedKey']}\n" +
            f"AllowedIPs = 192.168.10.0/21\n" +
            f"Endpoint = 21.22.23.24:51820\n" +
            f"PersistentKeepalive = 16</code>"
        )
    except Exception as e:
        if result.error:
            await message.answer(f"❌ {result.error}")
        else:
            await message.answer(f"❌ {e}")


async def del_user(message, user):
    result = await wg_del_user(name=user)
    try:
        data = json.loads(result.output)
        if data["success"]:
            await message.answer(f"✅ Пользователь <code>{user}</code> удален.")
        else:
            await message.answer("❌ Ошибка.")
    except Exception as e:
        if result.error:
            await message.answer(f"❌ {result.error}")
        else:
            await message.answer(f"❌ {e}")


async def config_show(message: Message, user: str, update: bool = False):
    result = await wg_get_user_config(name=user, update=update)
    try:
        config_data = json.loads(result.output)
        await message.answer(
            f"📄 Конфигурация пользователя\n<b>{user}</b>:\n\n" +
            f"<code># {config_data['Peer']}\n" +
            f"[Interface]\n" +
            f"PrivateKey = {config_data['PrivateKey']}\n" +
            f"Address = {config_data['ip']}/32\n\n" +
            f"[Peer]\n" +
            f"PublicKey = {config.WG_PublicKey}\n" +
            f"PresharedKey = {config_data['PresharedKey']}\n" +
            f"AllowedIPs = 192.168.10.0/21\n" +
            f"Endpoint = 21.22.23.24:51820\n" +
            f"PersistentKeepalive = 16</code>"
        )
    except Exception as e:
        if result.error:
            await message.answer(f"❌ {result.error}")
        else:
            await message.answer(f"❌ {e}")


async def set_add(message, user, ip):
    result = await wg_set_add(name=user, ip=ip)
    try:
        data = json.loads(result.output)
        if data["success"]:
            await message.answer(f"✅ Доступ к <code>{ip}</code> для <code>{user}</code> добавлен.")
        else:
            await message.answer("❌ Ошибка.")
    except Exception as e:
        if result.error:
            await message.answer(f"❌ {result.error}")
        else:
            await message.answer(f"❌ {e}")


async def set_del(message, user, ip):
    result = await wg_set_del(name=user, ip=ip)
    try:
        data = json.loads(result.output)
        if data["success"]:
            await message.answer(f"✅ Доступ к <code>{ip}</code> для <code>{user}</code> удалён.")
        else:
            await message.answer("❌ Ошибка.")
    except Exception as e:
        if result.error:
            await message.answer(f"❌ {result.error}")
        else:
            await message.answer(f"❌ {e}")


@wg_router.message(Command("wg"))
async def cmd_proxy(message: Message, state: FSMContext):
    # Очищаем состояние при новом запуске команды
    await state.clear()

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 Список", callback_data="list")],
        [InlineKeyboardButton(text="➕ Добавить", callback_data="add")],
        [InlineKeyboardButton(text="❌ Удалить", callback_data="del")],
        [InlineKeyboardButton(text="📄 Конфигурация", callback_data="config")],
        [InlineKeyboardButton(text="🔧 Доступы", callback_data="set")]
    ])
    await message.answer(text="Выберите действие:", reply_markup=keyboard)


@wg_router.callback_query(F.data.in_({"add", "list", "config", "set"}))
async def process_simple_callbacks(callback: CallbackQuery, state: FSMContext):
    data = callback.data
    if data == "add":
        await state.set_state(StateData.waiting_for_name)
        await callback.message.edit_text(
            text="Укажите <code>Имя Фамилия</code> для нового пользователя:",
            reply_markup=cancel_keyboard()
        )
    elif data == "list":
        result = await wg_get_users()
        try:
            wg_users = json.loads(result.output)
            await callback.message.edit_text(
                f"<b>Список пользователей</b>:\n\n" +
                "\n".join(f"— <code>{item['name']}</code> {item['ip']}" for item in wg_users)
            )
        except Exception as e:
            if result.error:
                await callback.message.answer(f"❌ {result.error}")
            else:
                await callback.message.answer(f"❌ {e}")
    elif data == "config":
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔍 Показать", callback_data="config_show")],
            [InlineKeyboardButton(text="🔁 Обновить", callback_data="config_update")]
        ])
        await callback.message.edit_text(text="📄 Конфигурация:", reply_markup=keyboard)
    elif data == "set":
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔍 Список доступов", callback_data="set_list")],
            [InlineKeyboardButton(text="➕ Добавить доступ", callback_data="set_add")],
            [InlineKeyboardButton(text="❌ Удалить доступ", callback_data="set_del")]
        ])
        await callback.message.edit_text(text="🔧 Управление доступами:", reply_markup=keyboard)
    await callback.answer()


# Универсальная функция для показа списка пользователей
async def show_users(callback: CallbackQuery):
    action = callback.data
    action_text = {
        "del": "❌ Удалить пользователя:",
        "set_list": "🔍 Посмотреть доступы:",
        "set_add": "➕ Добавить доступ:",
        "set_del": "❌ Удалить доступ:",
        "config_show": "🔍 Показать конфигурацию:",
        "config_update": "🔁 Обновить конфигурацию:"
    }
    result = await wg_get_users()
    try:
        wg_users = json.loads(result.output)
        buttons = [
            InlineKeyboardButton(text=item["name"], callback_data=f"user|{item['name']}|{action}")
            for item in wg_users
        ]
        inline_keyboard = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
        keyboard = InlineKeyboardMarkup(inline_keyboard=inline_keyboard)
        await callback.message.edit_text(
            f"{action_text.get(action, 'Выберите пользователя:')}\n\n",
            reply_markup=keyboard
        )
    except Exception as e:
        if result.error:
            await callback.message.answer(f"❌ {result.error}")
        else:
            await callback.message.answer(f"❌ {e}")
    await callback.answer()


# Обработка выбора пользователя
@wg_router.callback_query(F.data.startswith("user"))
async def process_callback_user(callback: CallbackQuery, state: FSMContext):
    _, user, action = callback.data.split("|")

    if action == "del":
        await state.update_data(action="del", user=user)
        await state.set_state(StateData.waiting_for_yes_no)
        await callback.message.edit_text(
            f"❌ Удалить пользователя <code>{user}</code>:",
            reply_markup=yes_no_keyboard()
        )
        await callback.answer()

    elif action in {"config_show", "config_update"}:
        await request_2fa(callback, state, action=action, user=user)

    elif action == "set_list":
        result = await wg_get_user_ips(name=user)
        try:
            wg_user_ips = json.loads(result.output)
            if wg_user_ips:
                # Разбиваем на пары для двух колонок
                # if len(wg_user_ips) > 10:
                #
                #     mid = (len(wg_user_ips) + 1) // 2
                #     left = wg_user_ips[:mid]
                #     right = wg_user_ips[mid:]
                #
                #     # Находим максимальную длину в левой колонке
                #     max_left_length = max(len(ip) for ip in left)
                #
                #     lines = []
                #     for i in range(len(left)):
                #         if i < len(right):
                #             # Форматируем строку с фиксированной шириной
                #             left_formatted = f"{left[i]:<{max_left_length}}"
                #             right_formatted = f"{right[i]}"
                #             lines.append(f"— <code>{left_formatted}</code>    — <code>{right_formatted}</code>")
                #         else:
                #             lines.append(f"— <code>{left[i]}</code>")
                #
                #     ip_text = "\n".join(lines)
                # else:
                #     ip_text = "\n".join(f"— <code>{ip}</code>" for ip in wg_user_ips)
                #
                # await callback.message.edit_text(f"🔍 Доступы пользователя\n<b>{user}</b>:\n\n{ip_text}")
                await callback.message.edit_text(
                    f"🔍 Доступы пользователя\n<b>{user}</b>:\n\n" +
                    "\n".join(f"— <code>{ip}</code>" for ip in wg_user_ips)
                )
            else:
                await callback.message.edit_text(f"У пользователя <code>{user}</code> нет доступов.")
            await state.clear()
        except Exception as e:
            if result.error:
                await callback.message.answer(f"❌ {result.error}")
            else:
                await callback.message.answer(f"❌ {e}")

    elif action == "set_add":
        await state.update_data(action=action, user=user)
        await state.set_state(StateData.waiting_for_ip)
        await callback.message.edit_text(
            text="Укажите IP адрес:",
            reply_markup=cancel_keyboard()
        )

    elif action == "set_del":
        result = await wg_get_user_ips(name=user)
        try:
            wg_user_ips = json.loads(result.output)
            if wg_user_ips:
                buttons = [
                    InlineKeyboardButton(text=ip, callback_data=f"set_del|{user}|{ip}")
                    for ip in wg_user_ips
                ]
                inline_keyboard = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
                keyboard = InlineKeyboardMarkup(inline_keyboard=inline_keyboard)
                await callback.message.edit_text("❌ Удалить доступ к:\n\n",reply_markup=keyboard)
            else:
                await callback.message.edit_text(f"У пользователя <code>{user}</code> нет доступов.")
            await callback.answer()
        except Exception as e:
            if result.error:
                await callback.message.answer(f"❌ {result.error}")
            else:
                await callback.message.answer(f"❌ {e}")


# Обработчик для раздела "Доступ", "Конфигурация"
@wg_router.callback_query(F.data.in_({"del", "set_list", "set_add", "set_del", "config_show", "config_update"}))
async def process_callback_access(callback: CallbackQuery):
    await show_users(callback)


@wg_router.callback_query(F.data.startswith("set_del|"))
async def process_callback_set_del(callback: CallbackQuery, state: FSMContext):
    _, user, ip = callback.data.split("|")
    if user and ip:
        await state.update_data(action="set_del", user=user, ip=ip)
        await state.set_state(StateData.waiting_for_yes_no)
        await callback.message.edit_text(
            f"❌ Удалить доступ к <code>{ip}</code> для <code>{user}</code>:",
            reply_markup=yes_no_keyboard()
        )
    else:
        await callback.message.edit_text(text=f"❌ Ошибка.")
        await state.clear()
    await callback.answer()


# Обработка нажатия кнопок ДА/НЕТ
@wg_router.callback_query(StateData.waiting_for_yes_no, F.data.in_(["yes", "no"]))
async def process_confirmation(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    action = data.get("action")
    user = data.get("user")
    ip = data.get("ip")
    if callback.data == "yes":
        await request_2fa(callback, state, action=action, user=user, ip=ip)
    else:
        await callback.message.edit_text("🚫 Действие отменено.")
        await state.clear()
    await callback.answer()


# Обработчик отмены
@wg_router.callback_query(F.data == "cancel")
async def process_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(text="🚫 Действие отменено.")
    await callback.answer()
