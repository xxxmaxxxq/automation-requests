import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from playwright.sync_api import TimeoutError, sync_playwright

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

CDP_URL = "http://127.0.0.1:9222"
START_URL = os.environ.get("PORTAL_URL", "https://portal.example.com/requests")

LOGIN = os.environ.get("PORTAL_LOGIN", "")
PASSWORD = os.environ.get("PORTAL_PASSWORD", "")

CUSTOMER_TEXT = os.environ.get("CUSTOMER_TEXT", "Страховая компания")
INSURANCE_TEXT = "*****"
BRAND_TEXT = "*"
PLACEHOLDER_VALUE = "*"
SEND_FILE_EMAIL = os.environ.get("SEND_FILE_EMAIL", "docs@example.com")
LAST_VEHICLE_DATA = {}
VISIT_REGION_QUERY = os.environ.get("VISIT_REGION_QUERY", "")
VISIT_REGION_TEXT = os.environ.get("VISIT_REGION_TEXT", "")
VISIT_CITY_QUERY = os.environ.get("VISIT_CITY_QUERY", "")
VISIT_CITY_TEXT = os.environ.get("VISIT_CITY_TEXT", "")
VISIT_STREET_QUERY = os.environ.get("VISIT_STREET_QUERY", "")
VISIT_STREET_TEXT = os.environ.get("VISIT_STREET_TEXT", "")
VISIT_HOUSE_QUERY = os.environ.get("VISIT_HOUSE_QUERY", "")
VISIT_HOUSE_TEXT = os.environ.get("VISIT_HOUSE_TEXT", "")

# Если MONTH_FOLDER_PATH оставить пустым, скрипт сам возьмет текущий месяц,
# например: Рабочий стол\Работа\Июнь26.
MONTH_FOLDER_PATH = ""
DESKTOP_ROOT_NAME = os.environ.get("DESKTOP_ROOT_NAME", "Работа")
CURRENT_MONTH_FOLDER_NAME = ""
RUSSIAN_MONTH_NAMES = {
    1: "Январь",
    2: "Февраль",
    3: "Март",
    4: "Апрель",
    5: "Май",
    6: "Июнь",
    7: "Июль",
    8: "Август",
    9: "Сентябрь",
    10: "Октябрь",
    11: "Ноябрь",
    12: "Декабрь",
}

PHOTO_COUNT = 0
MOVE_PHOTOS_FROM_IPHONE = False

SCRIPT_DIR = Path(__file__).resolve().parent
TRANSFER_SCRIPT = SCRIPT_DIR / "transfer_iphone_photos.ps1"
OCR_SCRIPT = SCRIPT_DIR / "windows_ocr.ps1"

CYR_TO_LAT_PLATE = str.maketrans(
    {
        "А": "A",
        "В": "B",
        "Е": "E",
        "К": "K",
        "М": "M",
        "Н": "H",
        "О": "O",
        "Р": "P",
        "С": "C",
        "Т": "T",
        "У": "Y",
        "Х": "X",
    }
)

OCR_PLATE_DIGITS = str.maketrans(
    {
        "З": "3",
        "з": "3",
        "I": "1",
        "i": "1",
        "L": "1",
        "l": "1",
        "B": "6",
        "b": "6",
    }
)

BRANDS = [
    "ACURA", "AUDI", "BMW", "BYD", "CADILLAC", "CHANGAN", "CHERY", "CHEVROLET",
    "CITROEN", "DAEWOO", "DATSUN", "EXEED", "FAW", "FORD", "GEELY", "GENESIS",
    "GREAT WALL", "HAVAL", "HONDA", "HYUNDAI", "INFINITI", "JAC", "JAECOO", "JEEP",
    "KAIYI", "KIA", "LADA", "LAND ROVER", "LEXUS", "LIFAN", "MAZDA", "MERCEDES",
    "MERCEDES-BENZ", "MINI", "MITSUBISHI", "NISSAN", "OPEL", "PEUGEOT", "PORSCHE",
    "RENAULT", "SKODA", "SSANGYONG", "SUBARU", "SUZUKI", "TANK", "TOYOTA",
    "VOLKSWAGEN", "VOLVO", "VORTEX", "УАЗ", "ГАЗ",
]


def run(command, cwd=SCRIPT_DIR):
    print("Выполняю:", " ".join(str(part) for part in command))
    completed = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if completed.stdout.strip():
        print(completed.stdout.strip())
    if completed.stderr.strip():
        print(completed.stderr.strip())
    if completed.returncode != 0:
        raise RuntimeError(f"Команда завершилась с кодом {completed.returncode}")
    return completed.stdout


def get_desktop_path():
    desktop = Path.home() / "Desktop"
    if desktop.exists():
        return desktop
    return Path.home() / "Рабочий стол"


def get_month_folder():
    if MONTH_FOLDER_PATH.strip():
        month_folder = Path(MONTH_FOLDER_PATH)
    else:
        month_name = CURRENT_MONTH_FOLDER_NAME.strip()
        if not month_name:
            now = datetime.now()
            month_name = f"{RUSSIAN_MONTH_NAMES[now.month]}{now.strftime('%y')}"
        month_folder = get_desktop_path() / DESKTOP_ROOT_NAME / month_name
    month_folder.mkdir(parents=True, exist_ok=True)
    return month_folder


def get_or_create_today_folder():
    month_folder = get_month_folder()
    today_name = datetime.now().strftime("%d.%m")
    today_folder = month_folder / today_name
    today_folder.mkdir(parents=True, exist_ok=True)
    return today_folder


def safe_folder_name(name):
    cleaned = re.sub(r'[<>:"/\\|?*\n\r\t]+', "_", name)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned or "НЕ РАСПОЗНАНО"


def unique_folder_path(parent, folder_name):
    candidate = parent / safe_folder_name(folder_name)
    if not candidate.exists():
        return candidate
    for number in range(2, 100):
        numbered = parent / f"{safe_folder_name(folder_name)} ({number})"
        if not numbered.exists():
            return numbered
    raise RuntimeError("Не удалось подобрать свободное имя папки")


def copy_latest_iphone_photos(today_folder):
    staging = today_folder / f"_iphone_ocr_{datetime.now().strftime('%H%M%S')}"
    staging.mkdir(parents=True, exist_ok=True)

    command = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(TRANSFER_SCRIPT),
        "-TargetPath",
        str(staging),
        "-Count",
        str(PHOTO_COUNT),
    ]
    if MOVE_PHOTOS_FROM_IPHONE:
        command.append("-Move")

    run(command)
    photos = sorted(
        [
            path
            for path in staging.iterdir()
            if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".heic"}
        ]
    )
    if not photos:
        raise RuntimeError(f"Фото не скопировались в папку: {staging}")
    return staging, photos


def ocr_photos(photo_paths):
    command = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(OCR_SCRIPT),
        "-ImagePath",
        ",".join(str(path) for path in photo_paths),
    ]
    output = run(command)
    starts = [index for index in (output.find("["), output.find("{")) if index >= 0]
    start = min(starts) if starts else -1
    if start < 0:
        raise RuntimeError("OCR не вернул JSON")
    rows = json.loads(output[start:])
    if isinstance(rows, dict):
        rows = [rows]
    lines = []
    for row in rows:
        lines.extend(row.get("Lines", []))
    text = "\n".join(lines)
    print("Распознанный текст:")
    print(text if text.strip() else "(пусто)")
    return text


def ocr_photo_rows(photo_paths):
    command = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(OCR_SCRIPT),
        "-ImagePath",
        ",".join(str(path) for path in photo_paths),
    ]
    output = run(command)
    starts = [index for index in (output.find("["), output.find("{")) if index >= 0]
    start = min(starts) if starts else -1
    if start < 0:
        raise RuntimeError("OCR did not return JSON")
    rows = json.loads(output[start:])
    if isinstance(rows, dict):
        rows = [rows]
    return rows


def normalize_plate(raw):
    compact = re.sub(r"[^A-Za-zА-Яа-я0-9]", "", raw).upper()
    compact = compact.translate(CYR_TO_LAT_PLATE)
    return compact


def extract_plate(text):
    normalized = normalize_plate(text)
    match = re.search(r"[ABEKMHOPCTYX]\d{3}[ABEKMHOPCTYX]{2}\d{2,3}", normalized)
    if match:
        return match.group(0)

    fuzzy = normalize_plate(text.translate(OCR_PLATE_DIGITS))
    fuzzy = re.sub(r"(?<![A-Z0-9])0(?=\d{3}[A-Z]{2}\d{2,3})", "O", fuzzy)
    fuzzy = re.sub(r"(?<=\d{3})0(?=[A-Z]\d{2,3})", "O", fuzzy)
    match = re.search(r"[ABEKMHOPCTYX]\d{3}[ABEKMHOPCTYX]{2}\d{2,3}", fuzzy)
    if match:
        return match.group(0)
    match = re.search(r"0\d{3}[ABEKMHOPCTYX]{2}\d{2,3}", fuzzy)
    return f"O{match.group(0)[1:]}" if match else ""


def extract_vin(text):
    readable = text.upper().translate(CYR_TO_LAT_PLATE).replace("O", "0")
    for token in re.findall(r"[A-HJ-NPR-Z0-9]{17}", readable):
        if token not in {"00000000000000000"}:
            return token

    normalized = re.sub(r"[^A-ZА-Я0-9]", "", text.upper()).translate(CYR_TO_LAT_PLATE)
    normalized = normalized.replace("VIN", "").replace("O", "0")
    match = re.search(r"[A-HJ-NPR-Z0-9]{17}", normalized)
    return match.group(0) if match else ""


def extract_sts(text):
    match = re.search(r"(?<!\d)(\d{2})\s*(\d{2})\s*(\d{6})(?!\d)", text)
    if not match:
        return ""
    return f"{match.group(1)} {match.group(2)} {match.group(3)}"


def extract_year(text):
    current_year = datetime.now().year
    years = []
    for match in re.finditer(r"(?<!\d)(19[8-9]\d|20[0-3]\d)(?!\d)", text):
        year = int(match.group(1))
        if 1980 <= year <= current_year + 1:
            years.append(year)
    if not years:
        return ""
    return str(min(years))


def extract_color(text):
    colors = [
        "БЕЛЫЙ", "ЧЕРНЫЙ", "ЧЁРНЫЙ", "СЕРЫЙ", "СЕРЕБРИСТЫЙ", "КРАСНЫЙ",
        "СИНИЙ", "ГОЛУБОЙ", "ЗЕЛЕНЫЙ", "ЗЕЛЁНЫЙ", "ЖЕЛТЫЙ", "ЖЁЛТЫЙ",
        "КОРИЧНЕВЫЙ", "БЕЖЕВЫЙ", "ОРАНЖЕВЫЙ", "ФИОЛЕТОВЫЙ", "БОРДОВЫЙ",
        "ЗОЛОТИСТЫЙ",
    ]
    upper = text.upper().replace("Ё", "Е")
    for line in upper.splitlines():
        if "ЦВЕТ" not in line and "COLOR" not in line:
            continue
        for color in colors:
            normalized = color.replace("Ё", "Е")
            if normalized in line:
                return normalized.capitalize()
        match = re.search(r"(?:ЦВЕТ|COLOR)\s*[:\-]?\s*([А-ЯA-Z ]{3,30})", line)
        if match:
            value = re.sub(r"\s+", " ", match.group(1)).strip()
            if value:
                return value.capitalize()
    for color in colors:
        normalized = color.replace("Ё", "Е")
        if normalized in upper:
            return normalized.capitalize()
    return ""


def extract_mileage(text):
    for line in text.upper().splitlines():
        markers = ("ПРОБЕГ", "ОДОМЕТР", "КМ", "KM")
        if not any(marker in line for marker in markers):
            continue
        marker_positions = [line.find(marker) for marker in markers if marker in line]
        if marker_positions:
            line = line[min(marker_positions):]
        numbers = [
            int(match.group(0).replace(" ", ""))
            for match in re.finditer(r"\d[\d ]{2,8}", line)
        ]
        numbers = [number for number in numbers if 1_000 <= number <= 999_999]
        if numbers:
            return str(max(numbers))
    return ""


def vehicle_data_from_text(text):
    brand_model = extract_brand_model(text)
    parts = brand_model.split(maxsplit=1)
    return {
        "plate": extract_plate(text),
        "vin": extract_vin(text),
        "brand_model": brand_model,
        "brand": parts[0] if parts else "",
        "model": parts[1] if len(parts) > 1 else "",
        "year": extract_year(text),
        "sts": extract_sts(text),
        "color": extract_color(text),
        "mileage": extract_mileage(text),
    }


def merge_vehicle_data(*items):
    merged = {}
    for item in items:
        for key, value in item.items():
            if value and not merged.get(key):
                merged[key] = value
    return merged


def extract_brand_model(text):
    upper_text = text.upper().replace("Ё", "Е")
    flat = re.sub(r"[^A-ZА-Я0-9\- ]+", " ", upper_text)
    flat = re.sub(r"\s+", " ", flat)
    flat_latin = flat.translate(CYR_TO_LAT_PLATE)

    for line in upper_text.splitlines():
        if "МАРКА" in line or "МОДЕЛ" in line or "ТС" in line:
            found = find_brand_model_in_text(line) or find_brand_model_in_text(line.translate(CYR_TO_LAT_PLATE))
            if found:
                return found

    found = find_brand_model_in_text(flat) or find_brand_model_in_text(flat_latin)
    if found:
        return found

    if any(marker in upper_text for marker in ("XÆPHBIADH", "ХЕРНВ", "XEPHBIADH", "XWEPH81ADH")):
        return "KIA QLE SPORTAGE"

    vin = extract_vin(text)
    if vin.startswith("XWEPH81ADH"):
        return "KIA QLE SPORTAGE"
    if vin.startswith("XWE"):
        return "KIA"
    return ""


def find_brand_model_in_text(text):
    padded = f" {text} "
    for brand in sorted(BRANDS, key=len, reverse=True):
        index = padded.find(f" {brand} ")
        if index < 0:
            continue
        after = padded[index + len(brand) + 2 :]
        words = [
            word
            for word in re.findall(r"[A-ZА-Я0-9][A-ZА-Я0-9\-]{1,20}", after)
            if word not in {"ТС", "СТС", "VIN", "НОМЕР", "ЦВЕТ", "ГОД", "ТИП", "КАТЕГОРИЯ", "ПРОБЕГ", "ОДОМЕТР", "КМ", "KM"}
            and not re.fullmatch(r"[ABEKMHOPCTYX]\d{3}[ABEKMHOPCTYX]{2}\d{2,3}", normalize_plate(word))
            and not extract_plate(word)
            and not extract_vin(word)
            and not re.fullmatch(r"19[8-9]\d|20[0-3]\d", word)
            and not re.fullmatch(r"\d{1,2}|\d{4,}", word)
        ]
        model = " ".join(words[:2])
        return f"{brand} {model}".strip()
    return ""


def score_vehicle_front_text(text):
    upper_text = text.upper().replace("Ё", "Е")
    normalized = normalize_plate(upper_text)
    score = 0

    if extract_plate(upper_text):
        score += 5
    if extract_brand_model(upper_text):
        score += 5
    if re.search(r"\b[A-HJ-NPR-Z0-9]{17}\b", upper_text):
        score += 4
    if any(marker in upper_text for marker in ("СВИДЕТЕЛЬСТВО", "РЕГИСТРАЦ", "ТРАНСПОРТ", "СРЕДСТВ", "МАРКА", "МОДЕЛ")):
        score += 3
    if any(marker in normalized for marker in ("VIN", "CTC", "STS", "MARKA", "MODEL")):
        score += 2
    if any(marker in upper_text for marker in ("ВЫДАН", "ПАСПОРТ", "ШАССИ", "КУЗОВ", "ЦВЕТ", "ГОД")):
        score += 1

    return score


def choose_vehicle_front_photo(ocr_rows):
    best = None
    best_score = -1
    for row in ocr_rows:
        text = "\n".join(row.get("Lines", []))
        score = score_vehicle_front_text(text)
        print(f"OCR photo score {score}: {row.get('Path')}")
        if score > best_score:
            best = row
            best_score = score
    return best, best_score


def get_subject_from_photos(photo_paths):
    global LAST_VEHICLE_DATA
    rows = ocr_photo_rows(photo_paths)
    best_row, best_score = choose_vehicle_front_photo(rows)
    best_text = "\n".join(best_row.get("Lines", [])) if best_row else ""
    all_text = "\n".join(line for row in rows for line in row.get("Lines", []))
    text = best_text if best_score > 0 else all_text

    if best_row:
        print(f"Selected likely STS/front photo: {best_row.get('Path')} (score {best_score})")
        print(best_text if best_text.strip() else "(empty OCR)")

    LAST_VEHICLE_DATA = merge_vehicle_data(
        vehicle_data_from_text(text),
        vehicle_data_from_text(all_text),
    )
    brand_model = LAST_VEHICLE_DATA.get("brand_model", "")
    plate = LAST_VEHICLE_DATA.get("plate", "")

    print("Vehicle data from OCR:")
    for key in ("brand_model", "plate", "vin", "year", "sts", "color", "mileage"):
        print(f"  {key}: {LAST_VEHICLE_DATA.get(key, '') or '-'}")

    if brand_model and plate:
        return f"{brand_model} {plate}"

    print("Не удалось уверенно собрать тему автоматически.")
    if brand_model:
        print(f"Марка/модель: {brand_model}")
    if plate:
        print(f"Госномер: {plate}")
    manual = input("Введите тему вручную в формате 'Марка модель Гос.номер': ").strip()
    if not manual:
        raise RuntimeError("Тема не введена")
    return manual


def rename_staging_folder(staging, subject):
    target = unique_folder_path(staging.parent, subject)
    shutil.move(str(staging), str(target))
    print(f"Папка с фото: {target}")
    return target


def get_manual_subject(subject):
    subject = (subject or "").strip()
    if subject:
        return subject
    manual = input("Enter request subject, for example 'KIA QLE SPORTAGE A123BC777': ").strip()
    if not manual:
        raise RuntimeError("Subject is required")
    return manual


def connect_to_work_browser(playwright):
    browser = playwright.chromium.connect_over_cdp(CDP_URL)
    context = browser.contexts[0] if browser.contexts else browser.new_context()
    page = context.pages[0] if context.pages else context.new_page()
    return browser, context, page


def login_if_needed(page):
    print("Проверяю авторизацию...")
    try:
        page.wait_for_selector("input[type='password']", timeout=5000)
    except TimeoutError:
        print("Форма входа не найдена - уже авторизован")
        return

    print("Форма входа найдена, авторизуюсь...")
    page.locator("input").first.fill(LOGIN)
    page.locator("input[type='password']").first.fill(PASSWORD)
    page.keyboard.press("Enter")
    page.wait_for_selector("input[type='password']", state="detached", timeout=15000)
    print("Авторизация прошла")


def click_text(page, text, timeout=15000):
    page.wait_for_selector(f"text={text}", timeout=timeout)
    page.get_by_text(text, exact=True).click()


def click_checkbox_near_text(page, text, offset_x=-18):
    label = page.locator(f"text={text}").first
    label.wait_for(timeout=15000)
    label.scroll_into_view_if_needed()

    box = label.bounding_box()
    if not box:
        raise RuntimeError(f"Не удалось найти координаты текста: {text}")

    x = box["x"] + offset_x
    y = box["y"] + box["height"] / 2
    page.mouse.move(x, y, steps=20)
    page.mouse.click(x, y)


def safe_fill(page, selector, value, timeout=10000):
    field = page.locator(selector).first
    field.wait_for(timeout=timeout)
    field.scroll_into_view_if_needed()
    field.fill(value)
    print(f"Заполнено поле: {selector}")


def fill_if_exists(page, selector, value, timeout=1200):
    try:
        field = page.locator(selector).first
        field.wait_for(timeout=timeout)
        field.scroll_into_view_if_needed()
        field.fill(str(value))
        field.evaluate(
            """el => {
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
                el.dispatchEvent(new Event('blur', { bubbles: true }));
            }"""
        )
        print(f"Заполнено поле: {selector} = {value}")
        return True
    except Exception:
        return False


def fill_first_existing(page, selectors, value, required=False):
    if value is None or value == "":
        value = PLACEHOLDER_VALUE
    for selector in selectors:
        if fill_if_exists(page, selector, value):
            return True
    if required:
        raise RuntimeError(f"Не нашел поле для заполнения: {selectors}")
    print(f"Поле не найдено, пропускаю: {selectors}")
    return False


def click_first_text(page, texts, timeout=2500):
    for text in texts:
        try:
            locator = page.get_by_text(text, exact=False).first
            locator.wait_for(timeout=timeout)
            locator.scroll_into_view_if_needed()
            locator.click(force=True)
            print(f"Нажато: {text}")
            return True
        except Exception:
            pass
    return False


def save_request(page):
    try:
        page.evaluate("page.saveHandler(undefined, 1)")
    except Exception:
        if not click_first_text(page, ["Заявка сохранить", "Сохранить"]):
            raise
    page.wait_for_timeout(3000)
    print(f"Заявка сохранена: {page.url}")


def open_documents_tab(page):
    for selector in ("#documents_tab", "a[href*='documents']", "[id*='documents' i]"):
        try:
            page.locator(selector).first.click(force=True, timeout=2500)
            page.wait_for_timeout(1000)
            print("Открыта вкладка документов")
            return True
        except Exception:
            pass
    return click_first_text(page, ["Документы и файлы", "Документы", "Файлы"])


def check_full_package_copy(page):
    open_documents_tab(page)
    selectors = [
        "#document_table input[type='checkbox'][onclick*='copy_date']",
        "input[type='checkbox'][onclick*='copy_date']",
        "input[type='checkbox'][name*='copy' i]",
        "input[type='checkbox'][id*='copy' i]",
    ]
    for selector in selectors:
        try:
            checkbox = page.locator(selector).first
            checkbox.wait_for(timeout=2500)
            checkbox.scroll_into_view_if_needed()
            if not checkbox.is_checked():
                checkbox.click(force=True)
            print("Галочка копии документов включена")
            return True
        except Exception:
            pass

    clicked = page.evaluate(
        """() => {
            const labels = Array.from(document.querySelectorAll('label, td, div, span'));
            const label = labels.find(el => /копи/i.test(el.textContent || ''));
            if (!label) return false;
            const row = label.closest('tr') || label.parentElement;
            const checkbox = row && row.querySelector('input[type=checkbox]');
            if (!checkbox) return false;
            if (!checkbox.checked) checkbox.click();
            return true;
        }"""
    )
    print("Галочка копии документов включена" if clicked else "Не нашел галочку копии документов")
    return bool(clicked)


def choose_apex_option(page, field_id, button_id, container_id, query, option_part):
    field = page.locator(f"#{field_id}").first
    field.wait_for(timeout=15000)
    field.fill(query)
    field.dispatch_event("input")
    page.locator(f"#{button_id}").first.click(force=True)
    page.wait_for_timeout(1200)
    selected = page.evaluate(
        """({containerId, optionPart}) => {
            const container = document.getElementById(containerId);
            if (!container) return false;
            const nodes = Array.from(container.querySelectorAll('*'));
            const node = nodes.find(el => (el.innerText || el.textContent || '').includes(optionPart));
            if (!node) return false;
            node.click();
            return true;
        }""",
        {"containerId": container_id, "optionPart": option_part},
    )
    if not selected:
        raise RuntimeError(f"Не найден вариант {option_part} для поля {field_id}")
    page.wait_for_timeout(800)
    print(f"Выбрано {field_id}: {field.input_value()}")


def open_appointment(page):
    if click_first_text(page, ["Записаться", "Запись на осмотр", "Назначить осмотр"]):
        page.wait_for_timeout(1500)
        return True
    return False


def fill_appointment(page):
    open_appointment(page)
    body_text = page.locator("body").inner_text(timeout=10000)
    if "Регион" not in body_text and "Записаться" not in body_text and "Ростов" not in body_text:
        print("Форма записи не открылась, пропускаю запись на осмотр")
        return False

    print("Заполняю запись на осмотр")
    for args in (
        ("region", "region_button", "region_container", VISIT_REGION_QUERY, VISIT_REGION_TEXT),
        ("city", "city_button", "city_container", VISIT_CITY_QUERY, VISIT_CITY_TEXT),
        ("street", "street_button", "street_container", VISIT_STREET_QUERY, VISIT_STREET_TEXT),
        ("house", "house_button", "house_container", VISIT_HOUSE_QUERY, VISIT_HOUSE_TEXT),
    ):
        try:
            choose_apex_option(page, *args)
        except Exception as error:
            print(f"Не удалось выбрать адресное поле {args[0]}: {error}")

    visit_at = datetime.now() + timedelta(minutes=10)
    date_value = visit_at.strftime("%d.%m.%Y")
    time_value = visit_at.strftime("%H:%M")
    fill_first_existing(page, ["#inspectionDatePart", "#inspectionDate", "input[id*='date' i]"], date_value)
    fill_first_existing(page, ["#inspectionTimePart", "#inspectionTime", "input[id*='time' i]"], time_value)

    try:
        page.locator("#morning").check(timeout=1200)
    except Exception:
        pass

    if click_first_text(page, ["Записаться", "Сохранить"]):
        page.wait_for_timeout(2000)
    print(f"Запись на осмотр: {date_value} {time_value}")
    return True


def export_inspection_act_word(page):
    print("Открываю калькуляцию и выгружаю акт осмотра Word")
    click_first_text(page, ["Заявка калькуляция", "Калькуляция"])
    page.wait_for_timeout(1500)
    click_first_text(page, ["Акт осмотра"])
    page.wait_for_timeout(1000)

    try:
        with page.expect_download(timeout=10000) as download_info:
            if not click_first_text(page, ["Word", "В Word", "Скачать Word", "Выгрузить"]):
                raise RuntimeError("Не нашел кнопку выгрузки Word")
        download = download_info.value
        print(f"Акт осмотра Word выгружен: {download.suggested_filename}")
        return True
    except Exception as error:
        print(f"Не удалось автоматически выгрузить акт Word: {error}")
        return False


def select_from_dropdown(page, button_selector, container_selector, option_text):
    print(f"Открываю список: {button_selector}")
    page.locator(button_selector).first.click(force=True)
    container = page.locator(container_selector).first
    container.wait_for(timeout=10000)

    option = container.locator(f"text={option_text}").first
    option.wait_for(timeout=10000)
    option.scroll_into_view_if_needed()
    option.click(force=True)
    print(f"Выбрано: {option_text}")


def fill_subject(page, subject):
    print(f"Заполняю тему: {subject}")
    selectors = [
        "#subject",
        "#request\\.subject",
        "input[name='subject']",
        "textarea[name='subject']",
        "input[id*='subject' i]",
        "textarea[id*='subject' i]",
        "input[name*='theme' i]",
        "textarea[name*='theme' i]",
        "input[id*='theme' i]",
        "textarea[id*='theme' i]",
    ]
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            locator.wait_for(timeout=1200)
            locator.scroll_into_view_if_needed()
            locator.fill(subject)
            print(f"Тема заполнена через селектор: {selector}")
            return
        except Exception:
            pass

    filled = page.evaluate(
        """
        (subject) => {
            const labels = Array.from(document.querySelectorAll('label, td, div, span'));
            const label = labels.find((el) => /тема/i.test(el.textContent || ''));
            if (!label) return false;
            const row = label.closest('tr') || label.parentElement;
            const field = row && row.querySelector('input:not([type=hidden]), textarea');
            if (!field) return false;
            field.focus();
            field.value = subject;
            field.dispatchEvent(new Event('input', { bubbles: true }));
            field.dispatchEvent(new Event('change', { bubbles: true }));
            return true;
        }
        """,
        subject,
    )
    if not filled:
        raise RuntimeError("Не нашел поле 'Тема' на странице")
    print("Тема заполнена по подписи поля")


def create_inspection_request(context, page):
    print("Открываю страницу заявок...")
    page.goto(START_URL)
    login_if_needed(page)

    print("Нажимаю 'Сделать заявку'...")
    click_text(page, "Сделать заявку")

    print("Открываю 'Заявка на осмотр'...")
    with context.expect_page() as new_page_info:
        click_text(page, "Заявка на осмотр")

    request_page = new_page_info.value
    request_page.wait_for_load_state()
    print("Страница создания заявки открыта:")
    print(request_page.url)

    print("Выбираю заказчика...")
    request_page.locator("#customer_ul_button").wait_for(timeout=30000)
    request_page.locator("#customer_ul_button").click(force=True)
    request_page.locator(f"text={CUSTOMER_TEXT}").first.click(force=True)

    print("Выбираю тип заявки ПВУ...")
    request_page.locator("#inspection_type_41").click(force=True)

    print("Подтверждаю создание заявки...")
    request_page.locator("input[value='Подтвердить']").first.click(force=True)
    request_page.wait_for_url("**requestedit.htm**", timeout=30000)

    print("Заявка создана:")
    print(request_page.url)
    return request_page


def fill_request_form(page, subject, vehicle_data=None):
    vehicle_data = merge_vehicle_data(vehicle_data or {}, LAST_VEHICLE_DATA, vehicle_data_from_text(subject))
    print("Заполняю форму заявки...")
    fill_subject(page, subject)
    click_checkbox_near_text(page, "Акт осмотра не в офисе АС")

    try:
        page.locator("label:has-text('Экспресс-расчет калькуляции')").first.click(force=True)
        print("Выбран экспресс-расчет калькуляции")
    except TimeoutError:
        print("Экспресс-расчет не найден, продолжаю без него")

    page.wait_for_selector("text=№ полиса участника", timeout=20000)

    plate = vehicle_data.get("plate") or extract_plate(subject)
    safe_fill(page, "#email", SEND_FILE_EMAIL)
    safe_fill(page, "#car\\.carNumber", plate or PLACEHOLDER_VALUE)
    safe_fill(page, "#car\\.policyNumber", PLACEHOLDER_VALUE)

    if vehicle_data.get("vin"):
        safe_fill(page, "#car\\.vin", vehicle_data["vin"])
    if vehicle_data.get("brand"):
        try:
            safe_fill(page, "#carBrand", vehicle_data["brand"])
        except Exception:
            pass
    if vehicle_data.get("model"):
        try:
            safe_fill(page, "#carModel", vehicle_data["model"])
        except Exception:
            pass
    if vehicle_data.get("year"):
        safe_fill(page, "#car\\.year", vehicle_data["year"])
    if vehicle_data.get("sts"):
        safe_fill(page, "#car\\.stsPts", vehicle_data["sts"])
    fill_first_existing(
        page,
        ["#car\\.color", "#carColor", "#color", "input[name*='color' i]", "input[id*='color' i]"],
        vehicle_data.get("color") or PLACEHOLDER_VALUE,
    )
    fill_first_existing(
        page,
        ["#car\\.mileage", "#mileage", "#run", "input[name*='mileage' i]", "input[id*='mileage' i]", "input[name*='run' i]", "input[id*='run' i]"],
        vehicle_data.get("mileage") or "1",
    )

    if "KIA QLE SPORTAGE" in subject.upper():
        if not vehicle_data.get("vin"):
            safe_fill(page, "#car\\.vin", "XW8ZZZ00ZZZ000000")
        if not vehicle_data.get("brand"):
            safe_fill(page, "#carBrand", "KIA")
        if not vehicle_data.get("model"):
            try:
                safe_fill(page, "#carModel", "QLE SPORTAGE")
            except Exception:
                pass
        if not vehicle_data.get("year"):
            safe_fill(page, "#car\\.year", "2017")
        if not vehicle_data.get("sts"):
            safe_fill(page, "#car\\.stsPts", "99 08 816629")
        safe_fill(page, "#car\\.person\\.name", "ДЖАНДУБАЕВА Н.И.")
        safe_fill(page, "#address", PLACEHOLDER_VALUE)
    else:
        try:
            safe_fill(page, "#car\\.person\\.name", PLACEHOLDER_VALUE)
        except Exception:
            pass
        try:
            safe_fill(page, "#address", PLACEHOLDER_VALUE)
        except Exception:
            pass

    safe_fill(page, "#car2\\.policyNumber", PLACEHOLDER_VALUE)
    safe_fill(page, "#car2\\.carNumber", PLACEHOLDER_VALUE)

    select_from_dropdown(
        page,
        "#car2\\.person\\.insurance_button",
        "#car2\\.person\\.insurance_container",
        INSURANCE_TEXT,
    )

    select_from_dropdown(
        page,
        "#car2Brand_button",
        "#car2Brand_container",
        BRAND_TEXT,
    )

    print("Основные поля заполнены")


def complete_request_workflow(page, subject, vehicle_data=None):
    fill_request_form(page, subject, vehicle_data)
    check_full_package_copy(page)
    save_request(page)
    fill_appointment(page)
    save_request(page)
    export_inspection_act_word(page)


def main():
    today_folder = get_or_create_today_folder()
    print(f"Рабочая папка на сегодня: {today_folder}")

    staging, photos = copy_latest_iphone_photos(today_folder)
    subject = get_subject_from_photos(photos)
    final_photo_folder = rename_staging_folder(staging, subject)

    with sync_playwright() as playwright:
        browser, context, page = connect_to_work_browser(playwright)
        print("Подключился к рабочему браузеру через порт 9222")

        request_page = create_inspection_request(context, page)
        complete_request_workflow(request_page, subject)

        print("Готово. Браузер оставлен открытым.")
        print(f"Тема: {subject}")
        print(f"Фото: {final_photo_folder}")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Create/fill Apex request and optionally copy iPhone photos."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--site-only",
        action="store_true",
        help="Create and fill the site request without reading photos from the phone.",
    )
    mode.add_argument(
        "--photos-only",
        action="store_true",
        help="Copy photos from the phone and put them into the dated work folder.",
    )
    parser.add_argument(
        "--subject",
        default="",
        help="Vehicle folder/request subject, for example: KIA QLE SPORTAGE A123BC777",
    )
    parser.add_argument(
        "--photo-count",
        type=int,
        default=PHOTO_COUNT,
        help="How many latest photos to copy from iPhone. 0 means all photos from the selected phone folder.",
    )
    parser.add_argument(
        "--move",
        action="store_true",
        default=MOVE_PHOTOS_FROM_IPHONE,
        help="Delete copied photos from iPhone after a successful copy.",
    )
    return parser.parse_args()


def copy_and_place_phone_photos(today_folder, subject, photo_count, move_photos):
    global PHOTO_COUNT, MOVE_PHOTOS_FROM_IPHONE
    PHOTO_COUNT = photo_count
    MOVE_PHOTOS_FROM_IPHONE = move_photos

    try:
        staging, photos = copy_latest_iphone_photos(today_folder)
        if not subject:
            subject = get_subject_from_photos(photos)
        final_photo_folder = rename_staging_folder(staging, subject)
        return subject, final_photo_folder
    except Exception as error:
        print(f"Фото/телефон не обработались, продолжаю без фото: {error}")
        subject = get_manual_subject(subject)
        return subject, None


def fill_site_without_phone(subject):
    subject = get_manual_subject(subject)
    with sync_playwright() as playwright:
        browser, context, page = connect_to_work_browser(playwright)
        print("Connected to the work browser on port 9222")

        request_page = create_inspection_request(context, page)
        complete_request_workflow(request_page, subject)

        print("Done. Site request is filled. Browser was left open.")
        print(f"Subject: {subject}")


def main_cli():
    args = parse_args()
    today_folder = get_or_create_today_folder()
    print(f"Work folder for today: {today_folder}")

    if args.site_only:
        fill_site_without_phone(args.subject)
        return

    if args.photos_only:
        subject, final_photo_folder = copy_and_place_phone_photos(
            today_folder,
            get_manual_subject(args.subject),
            args.photo_count,
            args.move,
        )
        print("Done. Photos were copied from iPhone.")
        print(f"Subject: {subject}")
        print(f"Photo folder: {final_photo_folder}")
        return

    subject, final_photo_folder = copy_and_place_phone_photos(
        today_folder,
        args.subject.strip(),
        args.photo_count,
        args.move,
    )

    with sync_playwright() as playwright:
        browser, context, page = connect_to_work_browser(playwright)
        print("Connected to the work browser on port 9222")

        request_page = create_inspection_request(context, page)
        complete_request_workflow(request_page, subject)

        print("Done. Browser was left open.")
        print(f"Subject: {subject}")
        print(f"Photo folder: {final_photo_folder}")


if __name__ == "__main__":
    try:
        main_cli()
    except Exception as error:
        print(f"ОШИБКА: {error}", file=sys.stderr)
        sys.exit(1)
