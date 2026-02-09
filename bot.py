from os import getenv, path, listdir
from datetime import datetime, timedelta
from json import load, dump, JSONDecodeError
from logging.handlers import RotatingFileHandler
from typing import Optional
from telegram import Update, ReplyKeyboardMarkup
from logging import basicConfig, DEBUG, getLogger
from add_user import add_user as add_xray_user, FLOW, IP, PBK, PORT, SNI
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters

# --- CONFIGURATION ---
ADMIN_ID = getenv("TELEGRAM_ADMIN_ID")
BOT_TOKEN = getenv("TELEGRAM_BOT_TOKEN")
DATA_FILE = "users.json"
MAX_PAYMENT_YEAR = 2026

basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=DEBUG,
    handlers=[
        # Writes to output.log, max 5MB, keeps 2 old copies, utf-8 encoding
        RotatingFileHandler("log/output.log", maxBytes=5*1024*1024, backupCount=2, encoding='utf-8')
    ]
)
logger = getLogger(__name__)

# --- MESSAGES ---

msg_error = "Возникла проблема. Пожалуйста, сообщите администратору."
msg_paid_full = "Оплачено до 2026 года."
msg_paid = "Всё готово. Оплата не требуется."
msg_unpaid = "Для дальнейшего использования VPN необходимо внести оплату."
msg_noID = "Мне не удалось найти ваш ID в базе данных."
msg_question = "Пожалуйста, задайте свой вопрос, ответ появится здесь в течение 24 часов."
msg_question_sent = "Вопрос отправлен! Ожидайте ответа."
msg_menu = "Выберите действие:"
msg_next_payment = "Следующий платеж в"

admin_sent = "Ответ отправлен пользователю "
admin_id_error = "В сообщении не удалось найти ID пользователя или ID сообщения."
admin_error = "Ошибка при отправке ответа: "

# --- BUTTONS ---

btn_1 = "Проверить мой платеж"
btn_2 = "Задать вопрос"
btn_3 = "Получить конфиг"
btn_instruction = "инструкция"
btn_next = "дальше"

instruction_platforms = {
    "ios": "ios",
    "android": "android",
    "windows": "windows",
    "macos": "macos",
    "linux": "linux",
}

MONTH_MAP = {
    1: 'jan', 2: 'feb', 3: 'mar', 4: 'apr', 5: 'may', 6: 'jun',
    7: 'jul', 8: 'aug', 9: 'sep', 10: 'oct', 11: 'nov', 12: 'dec'
}

# --- DATA MANAGEMENT ---

def _normalize_payment_value(value):
    if isinstance(value, bool):
        return int(value)
    try:
        return 1 if int(value) == 1 else 0
    except (TypeError, ValueError):
        return 0

def _prune_payments(payments):
    if not isinstance(payments, dict):
        return {}
    cleaned = {}
    for year_key, months in payments.items():
        year_str = str(year_key)
        if not year_str.isdigit():
            continue
        year = int(year_str)
        if year > MAX_PAYMENT_YEAR:
            continue
        if year != MAX_PAYMENT_YEAR:
            continue
        month_data = months if isinstance(months, dict) else {}
        cleaned[year_str] = {
            month: _normalize_payment_value(month_data.get(month, 0))
            for month in MONTH_MAP.values()
        }
    return cleaned

def _normalize_xray_data(xray_data, default_email=""):
    data = xray_data if isinstance(xray_data, dict) else {}
    return {
        "email": data.get("email", default_email) or default_email,
        "id": data.get("id", ""),
        "shortid": data.get("shortid", ""),
    }

def _normalize_user_entry(user_id_str, entry):
    base = entry if isinstance(entry, dict) else {}
    return {
        "name": base.get("name", ""),
        "date": base.get("date", 1),
        "payments": _prune_payments(base.get("payments", {})),
        "xray": _normalize_xray_data(base.get("xray", {}), default_email=user_id_str),
    }

def _normalize_users_data(data):
    if not isinstance(data, dict):
        return {}
    return {
        str(user_id): _normalize_user_entry(str(user_id), entry)
        for user_id, entry in data.items()
    }

def load_user_data(filename=DATA_FILE):
    """
    Loads user data from the JSON file.
    Returns an empty dict if file is missing or broken.
    """
    base_path = path.dirname(__file__)
    file_path = path.join(base_path, filename)
    logger.debug("Loading user data from %s", file_path)
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = load(f)
            normalized = _normalize_users_data(data)
            logger.debug("Loaded user data: %s users", len(normalized))
            return normalized
    except FileNotFoundError:
        logger.exception("User data file not found: %s", file_path)
        return {}
    except JSONDecodeError:
        logger.exception("User data file is invalid JSON: %s", file_path)
        return {}
    except Exception:
        logger.exception("Unexpected error while loading user data: %s", file_path)
        return {}

# func for validating vpn after the payment

def save_bot_data(data, filename=DATA_FILE):
    """
    Saves the dictionary back to the JSON file.
    """
    base_path = path.dirname(__file__)
    file_path = path.join(base_path, filename)
    with open(file_path, 'w', encoding='utf-8') as f:
        dump(_normalize_users_data(data), f, indent=4, ensure_ascii=False)

def get_user_entry(all_users_data, user_id_str, user_name=""):
    entry = _normalize_user_entry(user_id_str, all_users_data.get(user_id_str, {}))
    if user_name and not entry.get("name"):
        entry["name"] = user_name
    all_users_data[user_id_str] = entry
    return entry

def _build_initial_payments(current_month_idx):
    year_key = str(MAX_PAYMENT_YEAR)
    payments = {year_key: {month: 0 for month in MONTH_MAP.values()}}
    payments[year_key][MONTH_MAP[current_month_idx]] = 1
    return payments

def initialize_user_entry(all_users_data, user_id_str, user_name):
    now = datetime.now()
    due_date = now + timedelta(days=3)
    entry = {
        "name": user_name or "",
        "date": due_date.day,
        "payments": _build_initial_payments(now.month),
        "xray": {
            "email": user_id_str,
            "id": "",
            "shortid": "",
        },
    }
    all_users_data[user_id_str] = entry
    return entry

def build_vless_config(user_id, sid):
    return (
        f"vless://{user_id}@{IP}:{PORT}"
        f"?security=reality&encryption=none&pbk={PBK}&headerType=none"
        f"&fp=chrome&type=tcp&flow={FLOW}&sni={SNI}&sid={sid}#xray"
    )

def ensure_year(payments, year):
    if year != MAX_PAYMENT_YEAR:
        return
    year_key = str(year)
    if year_key not in payments or not isinstance(payments[year_key], dict):
        payments[year_key] = {}
    for month in MONTH_MAP.values():
        payments[year_key][month] = _normalize_payment_value(payments[year_key].get(month, 0))

def mark_current_month_paid(all_users_data, user_id_str, user_name):
    now = datetime.now()
    curr_year = now.year
    curr_month_key = MONTH_MAP[now.month]
    next_month_idx = now.month + 1
    next_year = curr_year
    if next_month_idx > 12:
        next_month_idx = 1
        next_year += 1
    next_month_key = MONTH_MAP[next_month_idx]

    user_entry = get_user_entry(all_users_data, user_id_str, user_name)
    payments = user_entry["payments"]

    ensure_year(payments, curr_year)
    ensure_year(payments, next_year)
    if curr_year == MAX_PAYMENT_YEAR:
        payments[str(curr_year)][curr_month_key] = 1
    if next_year == MAX_PAYMENT_YEAR:
        payments[str(next_year)][next_month_key] = 0

# --- LOGIC HELPERS ---

PAID_STATUS = "1"
UNPAID_STATUS = "0"

MONTH_MAP = {
    1: 'jan', 2: 'feb', 3: 'mar', 4: 'apr', 5: 'may', 6: 'jun',
    7: 'jul', 8: 'aug', 9: 'sep', 10: 'oct', 11: 'nov', 12: 'dec'
}

def _get_month_status(payments, year, month_idx):
    return str(payments.get(str(year), {}).get(MONTH_MAP[month_idx], UNPAID_STATUS))

def get_payment_status(user_data):
    """
    1. If current month is unpaid -> Unpaid.
    2. If current month is paid and today <= due_day -> Paid.
    3. If current month is paid and today > due_day:
       - If next month is unpaid -> Unpaid.
       - If next month is paid -> Paid.
    """
    payments = user_data.get("payments", {})
    logger.debug("Calculating payment status for user data keys: %s", list(user_data.keys()))

    try:
        due_day = int(user_data.get("date", 1))
    except (ValueError, TypeError):
        logger.exception("Invalid due day value: %s", user_data.get("date"))
        due_day = 1

    now = datetime.now()
    curr_year = now.year
    curr_month_idx = now.month
    curr_day = now.day

    curr_month_key = MONTH_MAP[curr_month_idx]
    curr_status = str(payments.get(str(curr_year), {}).get(curr_month_key, "0"))

    logger.debug(
        "Current payment status: year=%s month=%s due_day=%s status=%s",
        curr_year,
        curr_month_key,
        due_day,
        curr_status,
    )
    if curr_status == "0":
        return msg_unpaid, None

    next_month_idx = curr_month_idx + 1
    next_year = curr_year
    if next_month_idx > 12:
        next_month_idx = 1
        next_year += 1
    next_month_key = MONTH_MAP[next_month_idx]
    next_status = str(payments.get(str(next_year), {}).get(next_month_key, "0"))

    logger.debug(
        "Next month status: year=%s month=%s status=%s current_day=%s",
        next_year,
        next_month_key,
        next_status,
        curr_day,
    )
    if curr_day > due_day and next_status == "0":
        return msg_unpaid, None

    # If we are here, user has access. Now find the Next Payment Date.
    # We start searching from the month AFTER the current month.
    search_month_idx = curr_month_idx + 1
    search_year = curr_year

    # Determine next unpaid date for info
    search_year = curr_year
    search_month_idx = curr_month_idx
    if curr_day > due_day:
        search_year = next_year
        search_month_idx = next_month_idx

    next_unpaid_str = None
    for y in range(search_year, MAX_PAYMENT_YEAR + 1):
        m_start = search_month_idx if y == search_year else 1
        for m in range(m_start, 13):
            m_key = MONTH_MAP[m]

            # Look up in JSON. Default to '0' (Unpaid) if year/month missing
            val = str(payments.get(str(y), {}).get(m_key, "0"))


            logger.debug("Scan payment status: year=%s month=%s status=%s", y, m_key, val)
            if val == "0":
                # Found the first unpaid month (e.g., Feb)
                # But we want to show the expiration date, which is in the PREVIOUS month (e.g., Jan)

                prev_m = m - 1
                prev_y = y
                if prev_m < 1:
                    prev_m = 12
                    prev_y -= 1

                prev_key = MONTH_MAP[prev_m]

                next_unpaid_str = f"{due_day} {prev_key} {prev_y}"
                break
        if next_unpaid_str:
            break

    if next_unpaid_str:
        logger.debug("Next unpaid month resolved to %s", next_unpaid_str)
        return msg_paid, next_unpaid_str
    else:
        # Loop finished and no "0" was found.
        # This means they are paid up to the end of your configured years.
        logger.debug("No unpaid months found; returning paid full.")
        return msg_paid, msg_paid_full


def _get_instruction_steps(platform_name):
    base_path = path.dirname(__file__)
    platform_path = path.join(base_path, "instructions", platform_name)
    if not path.isdir(platform_path):
        return []
    steps = []
    for entry in listdir(platform_path):
        step_path = path.join(platform_path, entry)
        if not path.isdir(step_path):
            continue
        if not entry.startswith("step"):
            continue
        step_number_str = entry.replace("step", "", 1)
        if not step_number_str.isdigit():
            continue
        steps.append((int(step_number_str), entry))
    steps.sort(key=lambda item: item[0])
    return [entry for _, entry in steps]


def _get_step_files(step_path):
    files = []
    for entry in listdir(step_path):
        entry_path = path.join(step_path, entry)
        if path.isfile(entry_path):
            files.append(entry_path)
    return sorted(files)


async def _send_instruction_step(
    update: Update,
    platform_name: str,
    step_folder: str,
    reply_markup: Optional[ReplyKeyboardMarkup] = None,
):
    base_path = path.dirname(__file__)
    step_path = path.join(base_path, platform_name, step_folder)
    if not path.isdir(step_path):
        await update.message.reply_text(msg_error)
        return

    files = _get_step_files(step_path)
    if not files:
        await update.message.reply_text(msg_error)
        return

    image_exts = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
    text_exts = {".txt", ".text"}
    last_index = len(files) - 1
    for index, entry_path in enumerate(files):
        _, ext = path.splitext(entry_path.lower())
        markup = reply_markup if index == last_index else None
        if ext in text_exts:
            with open(entry_path, "r", encoding="utf-8") as handle:
                content = handle.read().strip()
            if content:
                await update.message.reply_text(content, reply_markup=markup)
        elif ext in image_exts:
            with open(entry_path, "rb") as handle:
                await update.message.reply_photo(photo=handle, reply_markup=markup)

# def get_payment_status(user_data):
#     """
#     Checks the 'Relevant' month based on the due date.
#     1. If today <= due_date: Check CURRENT month.
#     2. If today > due_date: Check NEXT month.
#     """
#     payments = user_data.get("payments", {})
#     
#     # Get user's billing day
#     try:
#         due_day = int(user_data.get("date", "1"))
#     except (ValueError, TypeError):
#         due_day = 1
# 
#     month_map = {
#         1: 'jan', 2: 'feb', 3: 'mar', 4: 'apr', 5: 'may', 6: 'jun',
#         7: 'jul', 8: 'aug', 9: 'sep', 10: 'oct', 11: 'nov', 12: 'dec'
#     }
# 
#     now = datetime.now()
#     check_year = now.year
#     check_month_idx = now.month
#     curr_day = now.day
# 
#     # LOGIC FIX:
#     # If we are PAST the due date (e.g., Today is 26th, Due is 3rd),
#     # then the payment that matters right now is for the NEXT month.
#     if curr_day > due_day:
#         check_month_idx += 1
#         if check_month_idx > 12:
#             check_month_idx = 1
#             check_year += 1
# 
#     # Now get the status of the RELEVANT month (Current or Next)
#     check_month_key = month_map[check_month_idx]
#     status = str(payments.get(str(check_year), {}).get(check_month_key, "0"))
# 
#     if status == "0":
#         return msg_unpaid, None
#     else:
#         # If the relevant month is Paid ("1"), 
#         # then the NEXT payment due is the month AFTER that.
#         next_due_idx = check_month_idx + 1
#         next_due_year = check_year
#         
#         if next_due_idx > 12:
#             next_due_idx = 1
#             next_due_year += 1
#             
#         next_month_str = month_map[next_due_idx]
#         next_payment_date = f"{due_day} {next_month_str} {next_due_year}"
#         
#         return msg_paid, next_payment_date

# def get_payment_status(user_data):
#     """
#     1. Checks if current month is "0" -> Unpaid.
#     2. If "1", checks if today is past the user's due 'date' -> Unpaid.
#     3. If today is before due 'date', returns Paid + Next Payment Date (next month).
#     """
#     payments = user_data.get("payments", {})
# 
#     # Get user's billing day (default to 1 if missing)
#     try:
#         due_day = int(user_data.get("date", "1"))
#     except (ValueError, TypeError):
#         due_day = 1
# 
#     month_map = {
#         1: 'jan', 2: 'feb', 3: 'mar', 4: 'apr', 5: 'may', 6: 'jun',
#         7: 'jul', 8: 'aug', 9: 'sep', 10: 'oct', 11: 'nov', 12: 'dec'
#     }
# 
#     now = datetime.now()
#     curr_year = now.year
#     curr_month_idx = now.month
#     curr_day = now.day
# 
#     # 1. Check the JSON value for THIS month
#     curr_month_key = month_map[curr_month_idx]
#     is_paid_in_json = str(payments.get(str(curr_year), {}).get(curr_month_key, "0"))
# 
#     # LOGIC:
#     # If JSON says "0" -> Strictly Unpaid
#     if is_paid_in_json == "0":
#         return msg_unpaid, None
# 
#     # If JSON says "1" -> Check the specific Date
#     elif is_paid_in_json == "1":
#         if curr_day > due_day:
#             # Paid for month, but passed the cut-off date -> Unpaid
#             return msg_unpaid, None
#         else:
#             # Paid and within valid time -> Paid
#             # Calculate Next Month for the message
#             next_m_idx = curr_month_idx + 1
#             next_y = curr_year
# 
#             if next_m_idx > 12:
#                 next_m_idx = 1
#                 next_y += 1
# 
#             next_month_str = month_map[next_m_idx]
#             next_payment_date = f"{due_day} {next_month_str} {next_y}"
# 
#             return msg_paid, next_payment_date
# 
#     # Fallback if key missing
#     return msg_unpaid, None

# --- HANDLERS ---

async def handle_start_or_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Main handler for user messages.
    """
    user_id_str = str(update.effective_user.id)
    user_text = update.message.text
    logger.debug(
        "Incoming message: user_id=%s text=%s awaiting_question=%s",
        user_id_str,
        user_text,
        context.user_data.get('awaiting_question'),
    )
    
    # Retrieve the global data
    all_users_data = context.bot_data.get('user_info', {})
    logger.debug("Loaded %s users from bot_data", len(all_users_data))

    # Define the main keyboard menu
    keyboard = [[btn_1], [btn_3], [btn_2], [btn_instruction]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    # --- LOGIC 1: CHECK PAYMENT ---
    if user_text == btn_1:
        context.user_data['awaiting_question'] = False
        context.user_data['instruction_mode'] = False

        found_user = all_users_data.get(user_id_str)

        if found_user:
            logger.debug("Found user data for user_id=%s", user_id_str)
            curr_status, next_info = get_payment_status(found_user)

            if curr_status == msg_paid:
                # Check if it's the special "All Paid" message or a normal date
                if msg_paid_full in next_info:
                     await update.message.reply_text(f"✅ {msg_paid}\n{next_info}", reply_markup=reply_markup)
                else:
                     await update.message.reply_text(f"✅ {msg_paid}\n{msg_next_payment} {next_info}", reply_markup=reply_markup)
            else:
                await update.message.reply_text(f"⚠️ {msg_unpaid}", reply_markup=reply_markup)
        else:
            logger.debug("No user data found for user_id=%s", user_id_str)
            await update.message.reply_text(msg_noID, reply_markup=reply_markup)

    # if user_text == btn_1:
    #     context.user_data['awaiting_question'] = False

    #     found_user = all_users_data.get(user_id_str)

    #     if found_user:
    #         # curr_status will be either msg_paid or msg_unpaid
    #         # next_info will be the date string OR None
    #         curr_status, next_info = get_payment_status(found_user)

    #         if curr_status == msg_paid:
    #             # If paid, we show the success msg AND the next date
    #             await update.message.reply_text(f"✅ {msg_paid}\nNext payment is at {next_info}", reply_markup=reply_markup)
    #         else:
    #             # If unpaid, we just show the error message
    #             await update.message.reply_text(f"⚠️ {msg_unpaid}", reply_markup=reply_markup)
    #     else:
    #         await update.message.reply_text(msg_noID, reply_markup=reply_markup)

    # if user_text == btn_1:
    #     context.user_data['awaiting_question'] = False

    #     # Direct lookup (since JSON keys are now IDs)
    #     found_user = all_users_data.get(user_id_str)

    #     if found_user:
    #         curr_status, next_unpaid = get_payment_status(found_user)

    #         if next_unpaid:
    #             # Current is paid, show the next future payment date
    #             await update.message.reply_text(f"{curr_status}\nThe next payment is in {next_unpaid}", reply_markup=reply_markup)
    #         else:
    #             # Current is unpaid (msg_unpaid) OR fully paid forever (msg_paid)
    #             await update.message.reply_text(curr_status, reply_markup=reply_markup)
    #     else:
    #         await update.message.reply_text(msg_noID, reply_markup=reply_markup)

    # --- LOGIC 2: TRIGGER QUESTION MODE ---
    elif user_text == btn_2:
        context.user_data['awaiting_question'] = True
        context.user_data['instruction_mode'] = False
        logger.debug("User %s entered question mode", user_id_str)
        await update.message.reply_text(msg_question, reply_markup=reply_markup)

    # --- LOGIC 2.4: INSTRUCTION MENU ---
    elif user_text == btn_instruction:
        context.user_data['awaiting_question'] = False
        context.user_data['instruction_mode'] = True
        context.user_data['instruction_platform'] = None
        context.user_data['instruction_step'] = 0
        platform_buttons = [[name] for name in instruction_platforms.keys()]
        instruction_markup = ReplyKeyboardMarkup(platform_buttons, resize_keyboard=True)
        await update.message.reply_text(msg_menu, reply_markup=instruction_markup)

    elif context.user_data.get('instruction_mode') is True and user_text in instruction_platforms:
        context.user_data['awaiting_question'] = False
        platform_key = instruction_platforms[user_text]
        steps = _get_instruction_steps(platform_key)
        if not steps:
            context.user_data['instruction_mode'] = False
            context.user_data['instruction_platform'] = None
            context.user_data['instruction_step'] = 0
            await update.message.reply_text(msg_error, reply_markup=reply_markup)
        else:
            context.user_data['instruction_platform'] = platform_key
            context.user_data['instruction_step'] = 0
            next_markup = ReplyKeyboardMarkup([[btn_next]], resize_keyboard=True)
            if len(steps) == 1:
                await _send_instruction_step(update, platform_key, steps[0], reply_markup=reply_markup)
                context.user_data['instruction_mode'] = False
                context.user_data['instruction_platform'] = None
                context.user_data['instruction_step'] = 0
            else:
                await _send_instruction_step(update, platform_key, steps[0], reply_markup=next_markup)
                context.user_data['instruction_step'] = 1

    elif context.user_data.get('instruction_mode') is True and user_text == btn_next:
        platform_key = context.user_data.get('instruction_platform')
        if not platform_key:
            context.user_data['instruction_mode'] = False
            await update.message.reply_text(msg_menu, reply_markup=reply_markup)
        else:
            steps = _get_instruction_steps(platform_key)
            step_index = context.user_data.get('instruction_step', 0)
            if step_index >= len(steps):
                context.user_data['instruction_mode'] = False
                context.user_data['instruction_platform'] = None
                context.user_data['instruction_step'] = 0
                await update.message.reply_text(msg_menu, reply_markup=reply_markup)
            else:
                next_markup = ReplyKeyboardMarkup([[btn_next]], resize_keyboard=True)
                is_last_step = step_index == len(steps) - 1
                step_markup = reply_markup if is_last_step else next_markup
                await _send_instruction_step(update, platform_key, steps[step_index], reply_markup=step_markup)
                context.user_data['instruction_step'] = step_index + 1
                if is_last_step:
                    context.user_data['instruction_mode'] = False
                    context.user_data['instruction_platform'] = None
                    context.user_data['instruction_step'] = 0

    # --- LOGIC 2.5: GENERATE CONFIG ---
    elif user_text == btn_3:
        context.user_data['awaiting_question'] = False
        context.user_data['instruction_mode'] = False
        user_name = update.effective_user.first_name
        if user_id_str in all_users_data:
            user_entry = get_user_entry(all_users_data, user_id_str, user_name)
        else:
            user_entry = initialize_user_entry(all_users_data, user_id_str, user_name)
        xray_info = user_entry["xray"]
        if not xray_info.get("email"):
            xray_info["email"] = user_id_str

        user_id = xray_info.get("id")
        sid = xray_info.get("shortid")
        if not user_id or not sid:
            user_id, sid = add_xray_user(xray_info["email"])
            if not user_id or not sid:
                await update.message.reply_text(msg_error, reply_markup=reply_markup)
                return
            xray_info["id"] = user_id
            xray_info["shortid"] = sid

        save_bot_data(all_users_data)

        config_string = build_vless_config(user_id, sid)
        await update.message.reply_text(config_string, reply_markup=reply_markup)

    # --- LOGIC 3: PROCESS THE QUESTION TEXT ---
    elif context.user_data.get('awaiting_question') is True:
        context.user_data['awaiting_question'] = False
        
        # We catch the message ID here so we can reply to it later
        user_msg_id = update.message.message_id

        # Format the message for the Admin
        # Added 'Message ID' field so we can parse it back
        msg_to_admin = (
            f"NEW QUESTION\n\n"
            f"user ID: {user_id_str}\n"
            f"message ID: {user_msg_id}\n"
            f"name: {update.effective_user.first_name}\n"
            f"question:\n{user_text}"
        )
        
        logger.debug("Forwarding user question to admin_id=%s", ADMIN_ID)
        try:
            await context.bot.send_message(chat_id=ADMIN_ID, text=msg_to_admin)
            await update.message.reply_text(msg_question_sent, reply_markup=reply_markup)
        except Exception:
            logger.exception("Failed to forward question from user_id=%s to admin", user_id_str)
            await update.message.reply_text(msg_error, reply_markup=reply_markup)

    # --- DEFAULT: SHOW MENU ---
    else:
        logger.debug("Fallback to menu for user_id=%s", user_id_str)
        context.user_data['instruction_mode'] = False
        await update.message.reply_text(msg_menu, reply_markup=reply_markup)


async def handle_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler for Admin replies. Extracts User ID and Message ID to send a proper reply.
    """
    if update.message.reply_to_message:
        original_text = update.message.reply_to_message.text
        logger.debug("Admin reply received. Original text: %s", original_text)
        
        try:
            # Parse User ID and Message ID from the helper text
            user_text = "user ID: "
            message_text = "message ID: "
            if user_text in original_text and message_text in original_text:
                
                # Extract User ID
                part1 = original_text.split(user_text)[1]
                target_user_id = part1.split("\n")[0].strip()
                
                # Extract Message ID
                part2 = original_text.split(message_text)[1]
                target_msg_id = int(part2.split("\n")[0].strip())
                
                admin_response = update.message.text
                
                # Send text as a REPLY to the specific message ID
                await context.bot.send_message(
                    chat_id=target_user_id,
                    text=admin_response,
                    reply_to_message_id=target_msg_id
                )
                logger.debug(
                    "Admin response forwarded to user_id=%s message_id=%s",
                    target_user_id,
                    target_msg_id,
                )
                await update.message.reply_text(admin_sent + target_user_id)
            else:
                logger.debug("Admin reply missing user_id or message_id in original text.")
                await update.message.reply_text(admin_id_error)
                
        except Exception:
            logger.exception("Error while handling admin reply.")
            await update.message.reply_text(admin_error)
    else:
        logger.debug("Admin message without reply_to_message; ignoring.")


async def handle_error(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.exception("Unhandled exception in bot update: %s", update)

if __name__ == '__main__':
    if not BOT_TOKEN:
        print("error: TELEGRAM_BOT_TOKEN environment variable not set.")
        exit()
    logger.debug("Starting bot with admin_id=%s data_file=%s", ADMIN_ID, DATA_FILE)

    application = ApplicationBuilder().token(BOT_TOKEN).build()
    
    user_data = load_user_data()
    application.bot_data['user_info'] = user_data
    #print(user_data)
    #print(application.bot_data['user_info'])
    
    admin_reply_handler = MessageHandler(
        filters.TEXT & filters.REPLY & filters.User(user_id=int(ADMIN_ID)), 
        handle_admin_reply
    )
    application.add_handler(admin_reply_handler)
    
    echo_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), handle_start_or_text)
    application.add_handler(echo_handler)
    application.add_error_handler(handle_error)
    
    print("bot is running...")
    application.run_polling(poll_interval=0.0)
