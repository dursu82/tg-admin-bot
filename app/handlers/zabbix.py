import io
import asyncio
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, BufferedInputFile
from playwright.async_api import async_playwright


zabbix_router = Router()


async def get_zabbix() -> io.BytesIO:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 2000}  # начальный размер
        )
        page = await context.new_page()

        await page.goto("http://192.168.10.10/zabbix/")
        await page.wait_for_selector('#name')
        await page.fill('#name', "tg_zabbix")
        await page.wait_for_selector('#password')
        await page.fill('#password', "LZN90onc72ADZek4Qap1")
        await page.wait_for_selector('#enter')
        await page.click('#enter')

        await page.goto("http://192.168.10.10/zabbix/zabbix.php?action=problem.view")
        await page.wait_for_selector('table.list-table', timeout=10000)

        table = await page.query_selector('table.list-table')
        box = await table.bounding_box()  # получаем размеры таблицы

        # clip при скриншоте страницы — это снимает только выбранный прямоугольник без постобработки
        # Получаем байты скриншота
        image_bytes = await page.screenshot(
            clip={
                "x": box['x'],
                "y": box['y'],
                "width": box['width'],
                "height": box['height'],
            }
        )

        await browser.close()

        # Оборачиваем байты в BytesIO
        image_buffer = io.BytesIO(image_bytes)
        image_buffer.name = "zabbix_table.png"  # нужно указать имя, чтобы Telegram понял формат
        return image_buffer


@zabbix_router.message(Command("zabbix"))
async def cmd_zabbix(message: Message):
    try:
        image = await get_zabbix()
        file = BufferedInputFile(file=image.getvalue(), filename=image.name)

        await message.answer_photo(photo=file)
    except Exception as e:
        await message.answer(f"Ошибка: {e}")
