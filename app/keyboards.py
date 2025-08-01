from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


start = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Запустить")]
    ],
    resize_keyboard=True,       # Клавиатура подстраивается под размер экрана
    one_time_keyboard=True      # Клавиатура скрывается после нажатия
)
