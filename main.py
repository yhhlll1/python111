import asyncio
import csv
import re
import time
import datetime
import os
from pathlib import Path
from contextlib import suppress
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=['--no-sandbox'])  # Укажите headless=True и --no-sandbox
    context = browser.new_context()
    page = context.new_page()
    # Ваш код парсинга
    browser.close()

# --- Константы/настройки ---
RESULTS_DIR = Path(r"C:\Users\User\Desktop\Результаты")  # сохраняем сюда
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# Словарь для маппинга картинок на значения кубиков
DICE_MAP = {
    "331234ece995aa78f50cc062957226bd.png": 1,
    "57e60f8a483c9d6a72b07b8d436d6777.png": 2,
    "c538525a1455e753688de63466693a4c.png": 3,
    "a1ab02b0b32c11d8a6575d2b3f578ba1.png": 4,
    "e1556dad68e361f99b529ec9543898ef.png": 5,
    "3a75e805c264fef3f225b162d59f4170.png": 6,
    "bfe63679876918b4e852b9e5b719b6c1.png": 1,
    "3b8e52be0c86b898fa53a7becb934994.png": 2,
    "9eb7d57d21072328ef12041166ecc596.png": 3,
    "77d7f166de1950e9061e47b4eb6e133a.png": 4,
    "7e9aacb22e1efe6f07b3f9b8dd97376a.png": 5,
    "a9777adb6c2576482b17252f9fe849c5.png": 6
}
DICE_FILES = set(DICE_MAP.keys())
BUTTON_NAME_REGEX = re.compile(r"^\s*Отлично!?\s*$", re.IGNORECASE)


def analyze_dice(d1, d2):
    """Анализ по сумме кубиков"""
    total = d1 + d2
    parity = "Четное" if total % 2 == 0 else "Нечетное"
    if d1 == d2:
        return f"{parity}, Пара"
    return parity


def create_csv_file():
    """Создание нового CSV с уникальным именем (кодировка UTF-8 с BOM для Excel)"""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = RESULTS_DIR / f"dice_results_{timestamp}.csv"
    f = open(filename, mode="w", newline="", encoding="utf-8-sig")  # 👈 тут заменил
    writer = csv.writer(f, delimiter=";")  # 👈 Excel лучше понимает ; как разделитель
    writer.writerow(["Время", "Кубик 1", "Кубик 2", "Сумма", "Анализ"])
    f.flush(); os.fsync(f.fileno())
    return f, writer, filename



def save_results_csv(fh, writer, d1, d2, analysis):
    """Запись строки в CSV (с немедленным сохранением на диск)"""
    now = datetime.datetime.now().strftime("%H:%M:%S")
    total = d1 + d2
    writer.writerow([now, d1, d2, total, analysis])
    fh.flush()
    with suppress(Exception):
        os.fsync(fh.fileno())


async def wait_and_click_button_by_name(page, name_regex: re.Pattern, timeout_ms: int = 180_000) -> bool:
    """Клик по кнопке 'Отлично!' (ищет и в iframe)"""
    deadline = time.monotonic() + timeout_ms / 1000
    last_err = None
    while time.monotonic() < deadline:
        try:
            loc = page.get_by_role("button", name=name_regex).first
            await loc.wait_for(state="visible", timeout=3000)
            await loc.scroll_into_view_if_needed()
            await loc.click(force=True)
            return True
        except Exception as e:
            last_err = e
        for frame in page.frames:
            try:
                floc = frame.get_by_role("button", name=name_regex).first
                await floc.wait_for(state="visible", timeout=2000)
                await floc.scroll_into_view_if_needed()
                await floc.click(force=True)
                return True
            except Exception as e:
                last_err = e
        await asyncio.sleep(0.5)
    if last_err:
        raise last_err
    raise PlaywrightTimeoutError(f"Не удалось найти кнопку за {timeout_ms} мс")


async def find_dice_files_anywhere(page, poll_ms: int = 300, timeout_ms: int = 60_000):
    """Поиск файлов кубиков"""
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        files = []
        frames = [page] + list(page.frames)
        for ctx in frames:
            try:
                found = await ctx.evaluate(
                    """(diceFiles) => {
                        const res = [];
                        const isVisible = (el) => {
                          const style = getComputedStyle(el);
                          if (style.visibility === 'hidden' || style.display === 'none') return false;
                          const r = el.getBoundingClientRect();
                          return r.width > 0 && r.height > 0;
                        };
                        const collect = (el, url) => {
                          if (!url) return;
                          const clean = url.replace(/^url\\(["']?/, '').replace(/["']?\\)$/, '');
                          const noQuery = clean.split('?')[0];
                          const file = noQuery.split('/').pop();
                          if (diceFiles.includes(file) && isVisible(el)) res.push(file);
                        };
                        document.querySelectorAll('img[src]').forEach(img => collect(img, img.src));
                        document.querySelectorAll('*').forEach(el => {
                          const bg = getComputedStyle(el).backgroundImage;
                          if (bg && bg.includes('url(')) collect(el, bg);
                        });
                        return res;
                    }""",
                    list(DICE_FILES)
                )
                files.extend(found or [])
            except Exception:
                pass
        seen = set()
        uniq = [f for f in files if not (f in seen or seen.add(f))]
        if len(uniq) >= 2:
            return uniq[:2]
        await asyncio.sleep(poll_ms / 1000)
    return []


async def parse_dice(page):
    """Парсинг кубиков"""
    try:
        dice_files = await find_dice_files_anywhere(page, poll_ms=250, timeout_ms=30_000)
        if len(dice_files) < 2:
            return None, None
        vals = []
        for fname in dice_files[:2]:
            val = DICE_MAP.get(fname)
            if val is None:
                return None, None
            vals.append(val)
        return (vals[0], vals[1]) if len(vals) == 2 else (None, None)
    except Exception as e:
        print(f"Ошибка при парсинге кубиков: {e}")
        return None, None


async def main():
    f = None
    browser = None
    context = None
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
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
