import jwt
import time
import json
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import WebAppInfo, Message, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove

from config import config
from utils import is_valid_ipv4, zwip
from app.databases import db_service


pbx_router = Router()

@pbx_router.message(Command("pbx"))
async def cmd_pbx(message: Message):
    data = {
        "user_id": message.from_user.id,
        "exp": int(time.time()) + 10  # Токен живёт 10 секунд
    }
    token = jwt.encode(data, config.secret_pbx_key, algorithm="HS256")

    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Отправить данные", web_app=WebAppInfo(url=f"https://app.test.com/?token={token}"))]
        ],
        resize_keyboard=True
        # one_time_keyboard=True
    )
    await message.answer("Нажми кнопку ниже 👇", reply_markup=keyboard)


@pbx_router.message(F.web_app_data)
async def handle_web_app_data(message: Message):
    data = message.web_app_data.data
    answer_text = "❌ Ошибка."
    if "error" in data:
        answer_text = "❌ Ошибка. Попробуйте ещё раз."           # Token expired
    elif "ip" in data:
        ip = json.loads(data)["ip"]
        if is_valid_ipv4(ip):
            if await db_service.pbx_ip_allowed(ip=ip):
                answer_text = f"ℹ️ Ваш IP адрес <b>{zwip(ip)}</b> уже есть в разрешенных."
            elif await db_service.pbx_allow_ip(ip=ip, user_id=message.from_user.id):
                answer_text = f"✅ IP адрес <b>{zwip(ip)}</b> добавлен."
            else:
                answer_text = f"❌ Ошибка при добавлении <b>{zwip(ip)}</b> в БД."
        else:
            answer_text = "❌ Ошибка при обработке данных."

    await message.answer(answer_text, reply_markup=ReplyKeyboardRemove())
