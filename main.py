import asyncio
import csv
import re
import time
import datetime
import os
from pathlib import Path
from contextlib import suppress
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

# --- Константы/настройки ---
RESULTS_DIR = Path("/root/projects/python111/results")  # Измените путь для сервера
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# ... (остальной код без изменений: DICE_MAP, DICE_FILES, BUTTON_NAME_REGEX, функции analyze_dice, create_csv_file, save_results_csv, wait_and_click_button_by_name, find_dice_files_anywhere, parse_dice остаются без изменений)

async def main():
    f = None
    browser = None
    context = None
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])  # Исправлено
            context = await browser.new_context()
            page = await context.new_page()

            await page.goto("https://betboom.ru/game/nardsgame", wait_until="domcontentloaded")

            with suppress(Exception):
                await page.wait_for_selector("button.CookieConsentPopup__PopupCookieButton-sc-1cemb3v-4", timeout=60000)
                cookie_button = await page.query_selector("button.CookieConsentPopup__PopupCookieButton-sc-1cemb3v-4")
                if cookie_button:
                    await cookie_button.click()
                    print("Нажали кнопку cookies")

            try:
                print("Ждём появления кнопки 'Отлично!'...")
                await wait_and_click_button_by_name(page, BUTTON_NAME_REGEX, timeout_ms=180_000)
                print("Нажали кнопку 'Отлично!'")
            except Exception as e:
                print(f"Ошибка при нажатии 'Отлично!': {e}")

            f, writer, filename = create_csv_file()
            print(f"Запись идёт в файл: {filename}")

            last_combo = None
            while True:
                d1, d2 = await parse_dice(page)
                if d1 is not None and d2 is not None:
                    combo = (d1, d2)
                    if combo != last_combo:
                        analysis = analyze_dice(d1, d2)
                        total = d1 + d2
                        print(f"Новая комбинация! Кубики: {d1}, {d2} (сумма: {total}) | Анализ: {analysis}")
                        save_results_csv(f, writer, d1, d2, analysis)
                        last_combo = combo
                await asyncio.sleep(1)

    except KeyboardInterrupt:
        print("\nОстановка программы пользователем (Ctrl+C).")
    except Exception as e:
        print(f"\nНеожиданная ошибка: {e}")
    finally:
        if f is not None and not f.closed:
            with suppress(Exception):
                f.flush(); os.fsync(f.fileno())
            with suppress(Exception):
                f.close()
            print("CSV-файл сохранён и закрыт.")
        if context is not None:
            with suppress(Exception):
                await context.close()
        if browser is not None:
            with suppress(Exception):
                await browser.close()
        print("Завершение работы.")

if __name__ == "__main__":
    asyncio.run(main())