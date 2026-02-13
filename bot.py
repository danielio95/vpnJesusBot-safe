from sys import stdout
from uuid import uuid4
from html import unescape
from subprocess import run, PIPE, STDOUT
from typing import Optional
from urllib.parse import quote
from requests import post, get
from argparse import ArgumentParser
from os import getenv, path, listdir
from asyncio import to_thread, sleep
from telegram.error import BadRequest
from telegram.constants import ParseMode
from json import load, dump, JSONDecodeError
from datetime import datetime, timedelta, time
from logging.handlers import RotatingFileHandler
from telegram import Update, ReplyKeyboardMarkup, InputMediaPhoto
from logging import INFO, WARNING, DEBUG, StreamHandler, basicConfig, getLogger
from add_user import add_user as add_xray_user, add_user_with_id as add_xray_user_with_id, FLOW, IP, PBK, PORT, SNI
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

# --- CONFIGURATION ---
ADMIN_ID = getenv("TELEGRAM_ADMIN_ID")
BOT_TOKEN = getenv("TELEGRAM_BOT_TOKEN")
DATA_FILE = "users.json"
MAX_PAYMENT_YEAR = 2026
YOOKASSA_SHOP_ID = getenv("YOOKASSA_SHOP_ID", "").strip()
YOOKASSA_SECRET_KEY = getenv("YOOKASSA_SECRET_KEY", "").strip()
YOOKASSA_RETURN_URL = getenv("YOOKASSA_RETURN_URL", "https://google.com").strip()
YOOKASSA_API_BASE = "https://api.yookassa.ru/v3"
PAYMENT_POLL_INTERVAL_SECONDS = 10
PAYMENT_POLL_ATTEMPTS = 60

def configure_logging(stdout_log_mode: str = "enable"):
    if stdout_log_mode == "debug":
        root_level = DEBUG
        stdout_level = DEBUG
    elif stdout_log_mode == "enable":
        root_level = INFO
        stdout_level = INFO
    else:
        root_level = INFO
        stdout_level = WARNING

    basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=root_level,
        handlers=[
            # Writes to output.log, max 5MB, keeps 2 old copies, utf-8 encoding
            RotatingFileHandler("log/output.log", maxBytes=5*1024*1024, backupCount=2, encoding='utf-8'),
            StreamHandler(stdout),
        ],
        force=True,
    )
    for handler in getLogger().handlers:
        if isinstance(handler, StreamHandler) and getattr(handler, "stream", None) is stdout:
            handler.setLevel(stdout_level)


configure_logging()
logger = getLogger(__name__)

# --- MESSAGES ---

msg_error = "Возникла проблема. Пожалуйста, сообщите администратору."
msg_paid_full = "Оплачено до конца 2026 года."
msg_paid = "Всё готово. Оплата не требуется."
msg_unpaid = "Для дальнейшего использования VPN необходимо внести оплату."
msg_payment_pending = "Платёж создан и ожидает подтверждения. Конфиг будет доступен после успешной оплаты."
msg_payment_success = "Поздравляю с покупкой! Ты можешь посмотреть свою конфигурацию нажав на Получить конфиг"
msg_noID = "Мне не удалось найти ваш ID в базе данных."
msg_question = "Пожалуйста, задайте свой вопрос, ответ появится здесь в течение 12 часов."
msg_question_sent = "Вопрос отправлен! Ожидайте ответа."
msg_menu = "Выберите действие:"
msg_choose_device = "Выберите устройство:"
msg_instruction_controls = "Нажмите «Дальше» или «Отменить»."
msg_instruction_wait = "Подождите, отправляю следующий шаг…"
msg_next_payment = "Следующий платеж в"
msg_welcome = (
    "Привет! 👋\n\n"
    "Твой профиль: <name and surname>.\n"
    "Поздравляю с бесплатной подпиской на 3 дня! 🎉\n\n"
    "Добро пожаловать в VPN Jesus — здесь мы поможем тебе безопасно и легко выйти в интернет "
    "без ограничений. Нажми на кнопку «Инструкция», чтобы получить пошаговое подключение, "
    "а затем выбери нужное действие в меню ниже."
)
msg_welcome_back = (
    "С возвращением! 👋\n\n"
    "Твой профиль: <name and surname>.\n"
    "Бесплатный 3-дневный доступ можно получить только один раз.\n\n"
    "Выбери нужное действие в меню ниже."
)

admin_sent = "Ответ отправлен пользователю "
admin_id_error = "В сообщении не удалось найти ID пользователя или ID сообщения."
admin_error = "Ошибка при отправке ответа: "

MSG = "telegram:@vpnjesusbot"

# --- BUTTONS ---

btn_1 = "Продлить/проверить мой платеж"
btn_1_legacy = "Проверить мой платеж"
btn_2 = "Задать вопрос"
btn_3 = "Получить конфиг"
btn_instruction = "Инструкция"
btn_next = "Дальше ➡️"
btn_cancel = "Отменить ❌"
btn_pay_1_month = "1 мес - 1 руб"
btn_pay_2_month = "2 мес - 2 руб"
btn_pay_3_month = "3 мес - 3 руб"
btn_cancel_pending_payment = "Отменить незавершённый платёж"
btn_restart_xray = "restart xray"
btn_stop_xray = "stop xray"
btn_start_xray = "start xray"

PAYMENT_BUTTONS = {
    btn_pay_1_month: {"months": 1, "amount": 1},
    btn_pay_2_month: {"months": 2, "amount": 2},
    btn_pay_3_month: {"months": 3, "amount": 3},
}

instruction_platforms = {
    "ios": "ios",
    "android": "android",
    "windows": "windows",
    "macos": "macos",
    "linux": "linux",
}


def build_instruction_next_markup(platform_key: str, step_index: int):
    if platform_key in {"android", "ios"} and step_index == 0:
        keyboard = [[btn_next, btn_3], [btn_cancel]]
    else:
        keyboard = [[btn_next], [btn_cancel]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

MONTH_MAP = {
    1: 'jan', 2: 'feb', 3: 'mar', 4: 'apr', 5: 'may', 6: 'jun',
    7: 'jul', 8: 'aug', 9: 'sep', 10: 'oct', 11: 'nov', 12: 'dec'
}

RU_MONTH_MAP = {
    'jan': 'января',
    'feb': 'февраля',
    'mar': 'марта',
    'apr': 'апреля',
    'may': 'мая',
    'jun': 'июня',
    'jul': 'июля',
    'aug': 'августа',
    'sep': 'сентября',
    'oct': 'октября',
    'nov': 'ноября',
    'dec': 'декабря',
}


def is_admin_user(user_id_str: str) -> bool:
    return bool(ADMIN_ID) and user_id_str == str(ADMIN_ID)


def build_main_menu_markup(user_id_str: Optional[str] = None):
    keyboard = [[btn_1], [btn_3], [btn_2], [btn_instruction]]
    if user_id_str and is_admin_user(user_id_str):
        keyboard.extend([[btn_restart_xray], [btn_stop_xray], [btn_start_xray]])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def build_payment_options_markup():
    keyboard = [[btn_pay_1_month], [btn_pay_2_month], [btn_pay_3_month], [btn_cancel]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def build_pending_payment_markup():
    keyboard = [[btn_cancel_pending_payment], [btn_cancel]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def run_xray_service_command(action: str):
    return run(
        ["sudo", "/usr/bin/systemctl", action, "xray.service"],
        stdout=PIPE,
        stderr=STDOUT,
        text=True,
        check=False,
    )

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
        "offloaded": bool(data.get("offloaded", False)),
        "offloaded_at": data.get("offloaded_at"),
    }

def _normalize_user_entry(user_id_str, entry):
    base = entry if isinstance(entry, dict) else {}
    pending_payment = base.get("pending_payment")
    if not isinstance(pending_payment, dict):
        pending_payment = None
    trial_data = base.get("trial") if isinstance(base.get("trial"), dict) else {}
    return {
        "name": base.get("name", ""),
        "date": base.get("date", 1),
        "payments": _prune_payments(base.get("payments", {})),
        "xray": _normalize_xray_data(base.get("xray", {}), default_email=user_id_str),
        "pending_payment": pending_payment,
        "trial": {
            "is_used": bool(trial_data.get("is_used", False)),
            "granted_at": trial_data.get("granted_at"),
        },
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
        "pending_payment": None,
        "trial": {
            "is_used": True,
            "granted_at": now.isoformat(),
        },
    }

    logger.debug("[XRAY SYNC] creating new user entry user_id=%s email=%s", user_id_str, user_id_str)
    user_id, sid = add_xray_user(user_id_str)
    if user_id and sid:
        entry["xray"]["id"] = user_id
        entry["xray"]["shortid"] = sid
        entry["xray"]["offloaded"] = False
        entry["xray"]["offloaded_at"] = None
        logger.info("[XRAY SYNC] created and loaded new user user_id=%s email=%s uuid=%s", user_id_str, user_id_str, user_id)
    else:
        logger.error("[XRAY SYNC] failed to create xray user for new user_id=%s email=%s", user_id_str, user_id_str)

    all_users_data[user_id_str] = entry
    return entry


def _mask_secret(secret):
    if not secret:
        return "<empty>"
    if len(secret) <= 6:
        return "***"
    return f"{secret[:3]}***{secret[-3:]}"


def _resolve_payment_start_month(user_entry):
    now = datetime.now()
    due_day = int(user_entry.get("date", 1) or 1)
    payments = user_entry.get("payments", {})

    curr_year = now.year
    curr_month_idx = now.month
    curr_status = _get_month_status(payments, curr_year, curr_month_idx)
    logger.debug(
        "[PAYMENT START] user_due_day=%s curr_year=%s curr_month=%s curr_status=%s curr_day=%s",
        due_day,
        curr_year,
        MONTH_MAP[curr_month_idx],
        curr_status,
        now.day,
    )
    if curr_status == UNPAID_STATUS:
        return curr_year, curr_month_idx

    next_month_idx = curr_month_idx + 1
    next_year = curr_year
    if next_month_idx > 12:
        next_month_idx = 1
        next_year += 1

    next_status = _get_month_status(payments, next_year, next_month_idx)
    if now.day > due_day and next_status == UNPAID_STATUS:
        return next_year, next_month_idx

    for year in range(curr_year, MAX_PAYMENT_YEAR + 1):
        month_start = curr_month_idx if year == curr_year else 1
        for month_idx in range(month_start, 13):
            if _get_month_status(payments, year, month_idx) == UNPAID_STATUS:
                return year, month_idx

    return MAX_PAYMENT_YEAR, 12


def mark_months_paid(user_entry, months_count):
    payments = user_entry.get("payments", {})
    start_year, start_month = _resolve_payment_start_month(user_entry)
    logger.info(
        "[PAYMENT APPLY] Applying paid months=%s starting from %s-%s",
        months_count,
        start_year,
        MONTH_MAP.get(start_month),
    )

    year = start_year
    month = start_month
    remaining = max(0, int(months_count))
    while remaining > 0 and year <= MAX_PAYMENT_YEAR:
        ensure_year(payments, year)
        if year == MAX_PAYMENT_YEAR:
            month_key = MONTH_MAP[month]
            payments[str(year)][month_key] = 1
            logger.debug("[PAYMENT APPLY] marked paid year=%s month=%s", year, month_key)
            remaining -= 1
        month += 1
        if month > 12:
            month = 1
            year += 1

    user_entry["payments"] = payments


def apply_subscription_extension(user_entry, months_count):
    curr_status, _ = get_payment_status(user_entry)
    if curr_status != msg_paid:
        user_entry["date"] = datetime.now().day
        logger.info("[PAYMENT APPLY] user inactive, resetting due day to %s", user_entry["date"])
    mark_months_paid(user_entry, months_count)

def create_yookassa_payment(amount_rub, description, user_id, months_count):
    if not YOOKASSA_SHOP_ID or not YOOKASSA_SECRET_KEY:
        logger.error(
            "[PAYMENT CREATE] Missing YooKassa credentials shop_id=%s secret=%s",
            YOOKASSA_SHOP_ID,
            _mask_secret(YOOKASSA_SECRET_KEY),
        )
        return {"error": "missing_credentials"}

    idempotence_key = str(uuid4())
    payload = {
        "amount": {"value": f"{float(amount_rub):.2f}", "currency": "RUB"},
        "payment_method_data": {"type": "bank_card"},
        "confirmation": {
            "type": "redirect",
            "return_url": YOOKASSA_RETURN_URL,
        },
        "capture": True,
        "description": description,
        "metadata": {
            "tg_user_id": user_id,
            "months": str(months_count),
        },
    }
    logger.info(
        "[PAYMENT CREATE] Creating payment idempotence=%s user_id=%s amount=%s months=%s return_url=%s",
        idempotence_key,
        user_id,
        amount_rub,
        months_count,
        YOOKASSA_RETURN_URL,
    )
    logger.debug("[PAYMENT CREATE] Request payload: %s", payload)

    try:
        response = post(
            f"{YOOKASSA_API_BASE}/payments",
            auth=(YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY),
            headers={
                "Idempotence-Key": idempotence_key,
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=30,
        )
    except Exception:
        logger.exception("[PAYMENT CREATE] request failed user_id=%s", user_id)
        return {"error": "request_failed"}

    logger.info(
        "[PAYMENT CREATE] Response status=%s user_id=%s body=%s",
        response.status_code,
        user_id,
        response.text,
    )
    if not response.ok:
        return {"error": "api_error", "status_code": response.status_code, "body": response.text}

    return response.json()


def fetch_yookassa_payment(payment_id):
    if not YOOKASSA_SHOP_ID or not YOOKASSA_SECRET_KEY:
        return {"error": "missing_credentials"}

    logger.debug("[PAYMENT STATUS] Fetching payment_id=%s", payment_id)
    try:
        response = get(
            f"{YOOKASSA_API_BASE}/payments/{payment_id}",
            auth=(YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY),
            timeout=30,
        )
    except Exception:
        logger.exception("[PAYMENT STATUS] request failed payment_id=%s", payment_id)
        return {"error": "request_failed"}

    if not response.ok:
        logger.warning(
            "[PAYMENT STATUS] non-ok status=%s payment_id=%s body=%s",
            response.status_code,
            payment_id,
            response.text,
        )
        return {"error": "api_error", "status_code": response.status_code, "body": response.text}

    data = response.json()
    logger.debug("[PAYMENT STATUS] response payment_id=%s payload=%s", payment_id, data)
    return data


def cancel_yookassa_payment(payment_id):
    if not YOOKASSA_SHOP_ID or not YOOKASSA_SECRET_KEY:
        return {"error": "missing_credentials"}

    idempotence_key = str(uuid4())
    logger.info("[PAYMENT CANCEL] cancel payment_id=%s idempotence=%s", payment_id, idempotence_key)
    try:
        response = post(
            f"{YOOKASSA_API_BASE}/payments/{payment_id}/cancel",
            auth=(YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY),
            headers={
                "Idempotence-Key": idempotence_key,
                "Content-Type": "application/json",
            },
            json={},
            timeout=30,
        )
    except Exception:
        logger.exception("[PAYMENT CANCEL] request failed payment_id=%s", payment_id)
        return {"error": "request_failed"}

    logger.info(
        "[PAYMENT CANCEL] response status=%s payment_id=%s body=%s",
        response.status_code,
        payment_id,
        response.text,
    )
    if not response.ok:
        return {"error": "api_error", "status_code": response.status_code, "body": response.text}

    return response.json()


async def monitor_payment_and_unlock(context: ContextTypes.DEFAULT_TYPE, user_id_str: str, payment_id: str):
    logger.info(
        "[PAYMENT MONITOR] started user_id=%s payment_id=%s attempts=%s interval=%s",
        user_id_str,
        payment_id,
        PAYMENT_POLL_ATTEMPTS,
        PAYMENT_POLL_INTERVAL_SECONDS,
    )
    for attempt in range(1, PAYMENT_POLL_ATTEMPTS + 1):
        data = await to_thread(fetch_yookassa_payment, payment_id)
        logger.info("[PAYMENT MONITOR] attempt=%s user_id=%s payment_id=%s data=%s", attempt, user_id_str, payment_id, data)

        all_users_data = context.bot_data.get('user_info', {})
        user_entry = all_users_data.get(user_id_str)
        if not user_entry:
            logger.warning("[PAYMENT MONITOR] user disappeared user_id=%s payment_id=%s", user_id_str, payment_id)
            return

        pending_payment = user_entry.get("pending_payment") or {}
        if pending_payment.get("payment_id") != payment_id:
            logger.warning("[PAYMENT MONITOR] pending payment changed user_id=%s existing=%s expected=%s", user_id_str, pending_payment.get("payment_id"), payment_id)
            return

        status = data.get("status") if isinstance(data, dict) else None
        paid = bool(data.get("paid", False)) if isinstance(data, dict) else False
        pending_payment["last_status"] = status
        pending_payment["last_checked_at"] = datetime.now().isoformat()
        pending_payment["attempt"] = attempt
        user_entry["pending_payment"] = pending_payment
        save_bot_data(all_users_data)

        if status == "succeeded" and paid:
            months = int(pending_payment.get("months", 1))
            apply_subscription_extension(user_entry, months)
            user_entry["pending_payment"] = None
            save_bot_data(all_users_data)
            await context.bot.send_message(chat_id=user_id_str, text=msg_payment_success, reply_markup=build_main_menu_markup(user_id_str))
            logger.info("[PAYMENT MONITOR] payment succeeded user_id=%s payment_id=%s months=%s", user_id_str, payment_id, months)
            return

        if status in {"canceled"}:
            user_entry["pending_payment"] = None
            save_bot_data(all_users_data)
            await context.bot.send_message(chat_id=user_id_str, text="Оплата была отменена. Попробуй снова, нажав на Получить конфиг.", reply_markup=build_main_menu_markup(user_id_str))
            logger.info("[PAYMENT MONITOR] payment canceled user_id=%s payment_id=%s", user_id_str, payment_id)
            return

        await sleep(PAYMENT_POLL_INTERVAL_SECONDS)

    logger.warning("[PAYMENT MONITOR] timeout user_id=%s payment_id=%s", user_id_str, payment_id)
    await context.bot.send_message(chat_id=user_id_str, text="Платёж всё ещё обрабатывается. Когда он подтвердится, я автоматически открою доступ к конфигу.")

def build_vless_config(user_id, sid):
    return (
        f"vless://{user_id}@{IP}:{PORT}"
        f"?security=reality&encryption=none&pbk={PBK}&headerType=none"
        f"&fp=chrome&type=tcp&flow={FLOW}&sni={SNI}&sid={sid}#{MSG}"
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


def _is_expired_for_offload(user_data, now=None):
    current_time = now or datetime.now()
    try:
        due_day = int(user_data.get("date", 1) or 1)
    except (TypeError, ValueError):
        due_day = 1

    if current_time.day <= due_day:
        return False

    payments = user_data.get("payments", {})
    current_unpaid = _get_month_status(payments, current_time.year, current_time.month) == UNPAID_STATUS

    next_month_idx = current_time.month + 1
    next_year = current_time.year
    if next_month_idx > 12:
        next_month_idx = 1
        next_year += 1

    next_unpaid = _get_month_status(payments, next_year, next_month_idx) == UNPAID_STATUS
    return current_unpaid or next_unpaid


def _offload_user(email):
    script_path = path.join(path.dirname(__file__), "offload_user.py")
    result = run(["python3", script_path, email], stdout=PIPE, stderr=STDOUT, text=True)
    child_output = (result.stdout or "").strip()

    if child_output:
        for line in child_output.splitlines():
            logger.debug("[OFFLOAD SCRIPT] %s", line)

    if result.returncode != 0:
        logger.error(
            "[OFFLOAD] failed email=%s returncode=%s output=%s",
            email,
            result.returncode,
            child_output,
        )
        return False

    logger.info("[OFFLOAD] success email=%s", email)
    return True


def preload_active_users_into_xray(all_users_data):
    loaded_count = 0
    skipped_count = 0

    for user_id_str, user_entry in all_users_data.items():
        normalized_entry = _normalize_user_entry(user_id_str, user_entry)
        all_users_data[user_id_str] = normalized_entry

        xray_info = normalized_entry.get("xray", {})
        email = xray_info.get("email") or user_id_str
        user_id = xray_info.get("id")
        sid = xray_info.get("shortid")

        logger.debug(
            "[XRAY PRELOAD] processing user_id=%s email=%s has_uuid=%s has_sid=%s offloaded=%s",
            user_id_str,
            email,
            bool(user_id),
            bool(sid),
            xray_info.get("offloaded"),
        )

        if not email or not user_id:
            logger.warning(
                "[XRAY PRELOAD] skip user_id=%s reason=missing_xray_fields email=%s id=%s sid=%s",
                user_id_str,
                email,
                bool(user_id),
                bool(sid),
            )
            skipped_count += 1
            continue

        success = add_xray_user_with_id(email, user_id)
        if not success:
            logger.error("[XRAY PRELOAD] failed user_id=%s email=%s", user_id_str, email)
            skipped_count += 1
            continue

        xray_info["offloaded"] = False
        xray_info["offloaded_at"] = None
        loaded_count += 1
        logger.info("[XRAY PRELOAD] loaded user_id=%s email=%s", user_id_str, email)

    if loaded_count:
        save_bot_data(all_users_data)

    logger.info("[XRAY PRELOAD] completed loaded=%s skipped=%s total=%s", loaded_count, skipped_count, len(all_users_data))
    return loaded_count, skipped_count


def run_expired_subscriptions_offload(all_users_data, reason="scheduled"):
    offloaded_count = 0
    for user_id_str, user_entry in all_users_data.items():
        normalized_entry = _normalize_user_entry(user_id_str, user_entry)
        all_users_data[user_id_str] = normalized_entry

        if not _is_expired_for_offload(normalized_entry):
            continue

        xray_info = normalized_entry.get("xray", {})
        if xray_info.get("offloaded"):
            logger.debug("[OFFLOAD] skip already offloaded user_id=%s reason=%s", user_id_str, reason)
            continue

        email = xray_info.get("email") or user_id_str
        if not email:
            logger.warning("[OFFLOAD] skip missing email user_id=%s reason=%s", user_id_str, reason)
            continue

        if _offload_user(email):
            xray_info["id"] = ""
            xray_info["shortid"] = ""
            xray_info["offloaded"] = True
            xray_info["offloaded_at"] = datetime.now().isoformat()
            offloaded_count += 1
            logger.info("[OFFLOAD] user_id=%s marked as offloaded reason=%s", user_id_str, reason)

    if offloaded_count:
        save_bot_data(all_users_data)

    logger.info("[OFFLOAD] completed reason=%s offloaded_count=%s", reason, offloaded_count)
    return offloaded_count


async def daily_expired_subscriptions_offload(context: ContextTypes.DEFAULT_TYPE):
    all_users_data = context.application.bot_data.get('user_info', {})
    await to_thread(run_expired_subscriptions_offload, all_users_data, "daily")

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

                localized_month = RU_MONTH_MAP.get(prev_key, prev_key)
                next_unpaid_str = f"{due_day} {localized_month} {prev_y}"
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


def _normalize_instruction_text(content):
    normalized = (content or "").replace('\\"', '"').replace("\\'", "'")
    return unescape(normalized)


def _split_caption_and_tail(content, caption_limit=1024):
    if len(content) <= caption_limit:
        return content, ""

    caption = content[:caption_limit]
    # Avoid clipping inside an HTML tag.
    if caption.rfind("<") > caption.rfind(">"):
        caption = caption[:caption.rfind("<")]
    caption = caption.rstrip()
    tail = content[len(caption):].lstrip() if caption else content
    return caption, tail


async def _reply_text_with_formatting_fallback(message, content, reply_markup=None):
    if not content:
        return
    try:
        await message.reply_text(content, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    except BadRequest:
        logger.warning("Failed to parse HTML in instruction text; sending plain text fallback.")
        await message.reply_text(content, reply_markup=reply_markup)


async def _reply_media_group_with_html_caption_fallback(message, media_group, caption_text):
    try:
        await message.reply_media_group(media=media_group)
    except BadRequest:
        logger.warning("Failed to parse HTML in instruction caption; retrying without formatting.")
        for media in media_group:
            if hasattr(media.media, "seek"):
                media.media.seek(0)
        fallback_group = []
        for i, media in enumerate(media_group):
            if i == 0 and caption_text:
                fallback_group.append(InputMediaPhoto(media=media.media, caption=caption_text))
            else:
                fallback_group.append(InputMediaPhoto(media=media.media))
        await message.reply_media_group(media=fallback_group)



async def _reply_photo_with_html_caption_fallback(message, image_handle, caption_text, reply_markup=None):
    try:
        await message.reply_photo(photo=image_handle, caption=caption_text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    except BadRequest:
        logger.warning("Failed to parse HTML in instruction photo caption; retrying without formatting.")
        image_handle.seek(0)
        await message.reply_photo(photo=image_handle, caption=caption_text, reply_markup=reply_markup)


def _collect_step_content(step_path):
    files = _get_step_files(step_path)
    image_exts = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
    text_exts = {".txt", ".text"}
    image_paths = []
    text_blocks = []
    for entry_path in files:
        _, ext = path.splitext(entry_path.lower())
        if ext in image_exts:
            image_paths.append(entry_path)
        elif ext in text_exts:
            with open(entry_path, "r", encoding="utf-8") as handle:
                content = handle.read().strip()
            if content:
                text_blocks.append(content)
    text_content = _normalize_instruction_text("\n\n".join(text_blocks))
    return image_paths, text_content


async def _send_instruction_step(
    update: Update,
    platform_name: str,
    step_folder: str,
    reply_markup: Optional[ReplyKeyboardMarkup] = None,
):
    base_path = path.dirname(__file__)
    step_path = path.join(base_path, "instructions", platform_name, step_folder)
    if not path.isdir(step_path):
        await update.message.reply_text(msg_error)
        return

    image_paths, text_content = _collect_step_content(step_path)
    if not image_paths and not text_content:
        await update.message.reply_text(msg_error)
        return

    if image_paths:
        caption, tail_text = _split_caption_and_tail(text_content) if text_content else (None, "")

        if len(image_paths) == 1:
            with open(image_paths[0], "rb") as image_handle:
                await _reply_photo_with_html_caption_fallback(
                    update.message,
                    image_handle,
                    caption,
                    reply_markup=reply_markup if not tail_text else None,
                )
            if tail_text:
                await _reply_text_with_formatting_fallback(update.message, tail_text, reply_markup=reply_markup)
            return

        max_media = 10
        for start in range(0, len(image_paths), max_media):
            chunk = image_paths[start:start + max_media]
            media_group = []
            open_handles = []
            for index, image_path in enumerate(chunk):
                handle = open(image_path, "rb")
                open_handles.append(handle)
                if start == 0 and index == 0 and caption:
                    media_group.append(InputMediaPhoto(media=handle, caption=caption, parse_mode=ParseMode.HTML))
                else:
                    media_group.append(InputMediaPhoto(media=handle))
            try:
                caption_for_chunk = caption if start == 0 else None
                await _reply_media_group_with_html_caption_fallback(update.message, media_group, caption_for_chunk)
            finally:
                for handle in open_handles:
                    handle.close()
        if tail_text:
            await _reply_text_with_formatting_fallback(update.message, tail_text, reply_markup=reply_markup)
            return
        #if reply_markup is not None:
        #    await update.message.reply_text(msg_instruction_controls, reply_markup=reply_markup)
        return

    await _reply_text_with_formatting_fallback(update.message, text_content, reply_markup=reply_markup)

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
    reply_markup = build_main_menu_markup(user_id_str)

    # --- LOGIC 1: CHECK PAYMENT ---
    if user_text in {btn_1, btn_1_legacy}:
        context.user_data['awaiting_question'] = False
        context.user_data['instruction_mode'] = False
        context.user_data['instruction_step_in_progress'] = False

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

            await update.message.reply_text(
                "Продлить подписку можно по кнопкам ниже:",
                reply_markup=build_payment_options_markup(),
            )
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
        context.user_data['instruction_step_in_progress'] = False
        logger.debug("User %s entered question mode", user_id_str)
        cancel_markup = ReplyKeyboardMarkup([[btn_cancel]], resize_keyboard=True)
        await update.message.reply_text(msg_question, reply_markup=cancel_markup)

    # --- LOGIC 2.3: CANCEL CURRENT FLOW ---
    elif user_text == btn_cancel:
        context.user_data['awaiting_question'] = False
        context.user_data['instruction_mode'] = False
        context.user_data['instruction_platform'] = None
        context.user_data['instruction_step'] = 0
        context.user_data['instruction_step_in_progress'] = False
        await update.message.reply_text(msg_menu, reply_markup=reply_markup)

    # --- LOGIC 2.4: INSTRUCTION MENU ---
    elif user_text == btn_instruction:
        context.user_data['awaiting_question'] = False
        context.user_data['instruction_mode'] = True
        context.user_data['instruction_platform'] = None
        context.user_data['instruction_step'] = 0
        context.user_data['instruction_step_in_progress'] = False
        #platform_buttons = [[name] for name in instruction_platforms.keys()]
        platform_names = list(instruction_platforms.keys())
        platform_buttons = [platform_names[i:i + 2] for i in range(0, len(platform_names), 2)]
        platform_buttons.append([btn_cancel])
        instruction_markup = ReplyKeyboardMarkup(platform_buttons, resize_keyboard=True)
        await update.message.reply_text(msg_choose_device, reply_markup=instruction_markup)

    elif context.user_data.get('instruction_mode') is True and user_text in instruction_platforms:
        context.user_data['awaiting_question'] = False
        platform_key = instruction_platforms[user_text]
        steps = _get_instruction_steps(platform_key)
        if not steps:
            context.user_data['instruction_mode'] = False
            context.user_data['instruction_platform'] = None
            context.user_data['instruction_step'] = 0
            context.user_data['instruction_step_in_progress'] = False
            await update.message.reply_text(msg_error, reply_markup=reply_markup)
        else:
            context.user_data['instruction_platform'] = platform_key
            context.user_data['instruction_step'] = 0
            next_markup = build_instruction_next_markup(platform_key, 0)
            if len(steps) == 1:
                await _send_instruction_step(update, platform_key, steps[0], reply_markup=reply_markup)
                await update.message.reply_text(msg_menu, reply_markup=reply_markup)
                context.user_data['instruction_mode'] = False
                context.user_data['instruction_platform'] = None
                context.user_data['instruction_step'] = 0
            else:
                await _send_instruction_step(update, platform_key, steps[0], reply_markup=next_markup)
                context.user_data['instruction_step'] = 1

    elif context.user_data.get('instruction_mode') is True and user_text == btn_next:
        if context.user_data.get('instruction_step_in_progress'):
            await update.message.reply_text(msg_instruction_wait)
            return

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
                context.user_data['instruction_step_in_progress'] = False
                await update.message.reply_text(msg_menu, reply_markup=reply_markup)
            else:
                context.user_data['instruction_step_in_progress'] = True
                next_markup = build_instruction_next_markup(platform_key, step_index)
                is_last_step = step_index == len(steps) - 1
                step_markup = reply_markup if is_last_step else next_markup
                context.user_data['instruction_step'] = step_index + 1
                try:
                    await _send_instruction_step(update, platform_key, steps[step_index], reply_markup=step_markup)
                except Exception:
                    context.user_data['instruction_step'] = step_index
                    raise
                finally:
                    context.user_data['instruction_step_in_progress'] = False

                if is_last_step:
                    await update.message.reply_text(msg_menu, reply_markup=reply_markup)
                    context.user_data['instruction_mode'] = False
                    context.user_data['instruction_platform'] = None
                    context.user_data['instruction_step'] = 0
                    context.user_data['instruction_step_in_progress'] = False

    # --- LOGIC 2.5: GENERATE CONFIG ---
    elif user_text == btn_3:
        context.user_data['awaiting_question'] = False
        payment_markup = build_payment_options_markup()
        in_instruction_flow = (
            context.user_data.get('instruction_mode') is True
            and context.user_data.get('instruction_platform')
        )
        if in_instruction_flow:
            platform_key = context.user_data.get('instruction_platform')
            step_index = context.user_data.get('instruction_step', 0)
            step_markup = build_instruction_next_markup(platform_key, max(step_index - 1, 0))
        else:
            context.user_data['instruction_mode'] = False
            context.user_data['instruction_step_in_progress'] = False
            step_markup = reply_markup

        user_name = update.effective_user.first_name
        if user_id_str in all_users_data:
            user_entry = get_user_entry(all_users_data, user_id_str, user_name)
        else:
            user_entry = initialize_user_entry(all_users_data, user_id_str, user_name)

        curr_status, _ = get_payment_status(user_entry)
        pending_payment = user_entry.get("pending_payment")
        if isinstance(pending_payment, dict) and pending_payment.get("payment_id"):
            if curr_status == msg_paid:
                logger.info(
                    "[PAYMENT CHECK] user_id=%s has active subscription, clearing stale pending payment payment_id=%s",
                    user_id_str,
                    pending_payment.get("payment_id"),
                )
                user_entry["pending_payment"] = None
                save_bot_data(all_users_data)
            else:
                logger.info(
                    "[PAYMENT CHECK] user_id=%s has pending payment payment_id=%s status=%s",
                    user_id_str,
                    pending_payment.get("payment_id"),
                    pending_payment.get("last_status"),
                )
                latest_data = await to_thread(fetch_yookassa_payment, pending_payment.get("payment_id"))
                status = latest_data.get("status") if isinstance(latest_data, dict) else None
                paid = bool(latest_data.get("paid", False)) if isinstance(latest_data, dict) else False
                logger.info(
                    "[PAYMENT CHECK] latest status user_id=%s payment_id=%s status=%s paid=%s",
                    user_id_str,
                    pending_payment.get("payment_id"),
                    status,
                    paid,
                )
                if status == "succeeded" and paid:
                    months = int(pending_payment.get("months", 1))
                    apply_subscription_extension(user_entry, months)
                    user_entry["pending_payment"] = None
                    save_bot_data(all_users_data)
                    await update.message.reply_text(msg_payment_success, reply_markup=reply_markup)
                else:
                    link = pending_payment.get("confirmation_url")
                    txt = f"{msg_payment_pending}\nСтатус: {status or 'unknown'}"
                    if link:
                        txt += f"\nСсылка на оплату: {link}\nQR: https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={quote(link)}"
                    await update.message.reply_text(txt, reply_markup=build_pending_payment_markup())
                return

        if curr_status != msg_paid:
            save_bot_data(all_users_data)
            await update.message.reply_text(f"⚠️ {msg_unpaid}", reply_markup=payment_markup)
            return

        xray_info = user_entry["xray"]
        if not xray_info.get("email"):
            xray_info["email"] = user_id_str

        user_id = xray_info.get("id")
        sid = xray_info.get("shortid")
        if not user_id or not sid:
            user_id, sid = add_xray_user(xray_info["email"])
            if not user_id or not sid:
                await update.message.reply_text(msg_error, reply_markup=step_markup)
                return
            xray_info["id"] = user_id
            xray_info["shortid"] = sid
            xray_info["offloaded"] = False
            xray_info["offloaded_at"] = None

        save_bot_data(all_users_data)

        config_string = build_vless_config(user_id, sid)
        await update.message.reply_text(config_string, reply_markup=step_markup)

    elif user_text in {btn_restart_xray, btn_stop_xray, btn_start_xray}:
        context.user_data['awaiting_question'] = False
        context.user_data['instruction_mode'] = False
        context.user_data['instruction_step_in_progress'] = False

        if not is_admin_user(user_id_str):
            await update.message.reply_text(msg_menu, reply_markup=reply_markup)
            return

        action_map = {
            btn_restart_xray: "restart",
            btn_stop_xray: "stop",
            btn_start_xray: "start",
        }
        action = action_map[user_text]
        result = await to_thread(run_xray_service_command, action)
        output = (result.stdout or "").strip()
        if result.returncode == 0:
            response = f"✅ xray {action} executed successfully."
        else:
            response = f"❌ Failed to {action} xray (code: {result.returncode})."
        if output:
            response += f"\n{output}"

        await update.message.reply_text(response, reply_markup=reply_markup)

    elif user_text in PAYMENT_BUTTONS:
        context.user_data['awaiting_question'] = False
        context.user_data['instruction_mode'] = False
        context.user_data['instruction_step_in_progress'] = False
        payment_choice = PAYMENT_BUTTONS[user_text]
        months = payment_choice["months"]
        amount = payment_choice["amount"]
        logger.info(
            "[PAYMENT FLOW] button selected user_id=%s text=%s months=%s amount=%s",
            user_id_str,
            user_text,
            months,
            amount,
        )

        user_name = update.effective_user.first_name
        if user_id_str in all_users_data:
            user_entry = get_user_entry(all_users_data, user_id_str, user_name)
        else:
            user_entry = initialize_user_entry(all_users_data, user_id_str, user_name)

        existing_pending = user_entry.get("pending_payment")
        if isinstance(existing_pending, dict) and existing_pending.get("payment_id"):
            logger.info("[PAYMENT FLOW] reusing existing pending payment user_id=%s payment_id=%s", user_id_str, existing_pending.get("payment_id"))
            link = existing_pending.get("confirmation_url")
            text = f"У тебя уже есть незавершённый платёж.\nСтатус: {existing_pending.get('last_status', 'pending')}"
            if link:
                text += f"\nСсылка на оплату: {link}\nQR: https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={quote(link)}"
            await update.message.reply_text(text, reply_markup=build_pending_payment_markup())
            return

        subscription_labels = {
            1: "Подписка Старт (1 мес )",
            2: "Подписка Стандарт ( 2 мес )",
            3: "Подписка Комфорт ( 3 мес )",
        }
        base_description = subscription_labels.get(months, f"Подписка {months} мес")
        description = f"{base_description} от user_id: {user_id_str}"
        payment_data = await to_thread(
            create_yookassa_payment,
            amount,
            description,
            user_id_str,
            months,
        )
        logger.info("[PAYMENT FLOW] create payment result user_id=%s data=%s", user_id_str, payment_data)

        if not isinstance(payment_data, dict) or payment_data.get("error"):
            await update.message.reply_text(
                "Не удалось создать платёж. Проверь настройки YooKassa и попробуй снова.",
                reply_markup=build_payment_options_markup(),
            )
            return

        confirmation_url = payment_data.get("confirmation", {}).get("confirmation_url")
        payment_id = payment_data.get("id")
        user_entry["pending_payment"] = {
            "payment_id": payment_id,
            "confirmation_url": confirmation_url,
            "months": months,
            "amount": amount,
            "created_at": datetime.now().isoformat(),
            "last_status": payment_data.get("status"),
        }
        save_bot_data(all_users_data)

        if not payment_id or not confirmation_url:
            logger.error("[PAYMENT FLOW] missing payment id or confirmation url user_id=%s payload=%s", user_id_str, payment_data)
            await update.message.reply_text(msg_error, reply_markup=build_main_menu_markup(user_id_str))
            return

        qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={quote(confirmation_url)}"
        await update.message.reply_text(
            (
                "Платёж создан ✅\n"
                f"Сумма: {amount} RUB\n"
                f"Месяцев: {months}\n"
                f"Ссылка на оплату: {confirmation_url}\n"
                f"QR: {qr_url}\n\n"
                "Я автоматически проверяю оплату. Пока оплата не подтверждена, доступ к конфигу закрыт."
            ),
            reply_markup=build_payment_options_markup(),
        )
        context.application.create_task(monitor_payment_and_unlock(context, user_id_str, payment_id))


    elif user_text == btn_cancel_pending_payment:
        context.user_data['awaiting_question'] = False
        context.user_data['instruction_mode'] = False
        context.user_data['instruction_step_in_progress'] = False

        user_name = update.effective_user.first_name
        if user_id_str in all_users_data:
            user_entry = get_user_entry(all_users_data, user_id_str, user_name)
        else:
            user_entry = initialize_user_entry(all_users_data, user_id_str, user_name)

        existing_pending = user_entry.get("pending_payment")
        if not isinstance(existing_pending, dict) or not existing_pending.get("payment_id"):
            await update.message.reply_text("У тебя нет незавершённого платежа.", reply_markup=build_payment_options_markup())
            return

        pending_payments_snapshot = []
        for pending_user_id, pending_user_entry in all_users_data.items():
            pending_data = pending_user_entry.get("pending_payment") if isinstance(pending_user_entry, dict) else None
            if isinstance(pending_data, dict) and pending_data.get("payment_id"):
                pending_payments_snapshot.append(
                    {
                        "user_id": pending_user_id,
                        "payment_id": pending_data.get("payment_id"),
                        "status": pending_data.get("last_status"),
                        "months": pending_data.get("months"),
                        "amount": pending_data.get("amount"),
                        "created_at": pending_data.get("created_at"),
                    }
                )
        logger.debug(
            "[PAYMENT CANCEL] pending payments snapshot before cancel requester=%s count=%s data=%s",
            user_id_str,
            len(pending_payments_snapshot),
            pending_payments_snapshot,
        )

        payment_id = existing_pending.get("payment_id")
        cancel_data = await to_thread(cancel_yookassa_payment, payment_id)
        status = cancel_data.get("status") if isinstance(cancel_data, dict) else None
        if isinstance(cancel_data, dict) and not cancel_data.get("error") and status in {"canceled", "succeeded", "waiting_for_capture"}:
            user_entry["pending_payment"] = None
            save_bot_data(all_users_data)
            if status == "succeeded":
                months = int(existing_pending.get("months", 1))
                apply_subscription_extension(user_entry, months)
                save_bot_data(all_users_data)
                await update.message.reply_text(
                    "Платёж уже был успешно завершён, отмена не требуется. Подписка активирована.",
                    reply_markup=build_main_menu_markup(user_id_str),
                )
            else:
                await update.message.reply_text(
                    "Незавершённый платёж отменён. Теперь можешь выбрать другой срок подписки.",
                    reply_markup=build_payment_options_markup(),
                )
            return

        latest_data = await to_thread(fetch_yookassa_payment, payment_id)
        latest_status = latest_data.get("status") if isinstance(latest_data, dict) else None
        if latest_status == "canceled":
            user_entry["pending_payment"] = None
            save_bot_data(all_users_data)
            await update.message.reply_text(
                "Незавершённый платёж уже отменён. Выбери новый срок подписки.",
                reply_markup=build_payment_options_markup(),
            )
            return

        if latest_status == "succeeded" and bool(latest_data.get("paid", False)):
            months = int(existing_pending.get("months", 1))
            apply_subscription_extension(user_entry, months)
            user_entry["pending_payment"] = None
            save_bot_data(all_users_data)
            await update.message.reply_text(msg_payment_success, reply_markup=build_main_menu_markup(user_id_str))
            return

        if latest_status in {"pending", "waiting_for_capture"}:
            logger.warning(
                "[PAYMENT CANCEL] detach pending payment after cancel failure user_id=%s payment_id=%s cancel=%s",
                user_id_str,
                payment_id,
                cancel_data,
            )
            user_entry["pending_payment"] = None
            save_bot_data(all_users_data)
            await update.message.reply_text(
                "Не удалось отменить платёж в YooKassa, но я отвязал его в боте. Теперь можешь создать новый платёж на нужный срок.",
                reply_markup=build_payment_options_markup(),
            )
            return

        await update.message.reply_text(
            "Не удалось отменить платёж прямо сейчас. Попробуй снова через минуту.",
            reply_markup=build_pending_payment_markup(),
        )

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
        context.user_data['instruction_step_in_progress'] = False
        await update.message.reply_text(msg_menu, reply_markup=reply_markup)


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['awaiting_question'] = False
    context.user_data['instruction_mode'] = False
    context.user_data['instruction_step_in_progress'] = False
    user_id_str = str(update.effective_user.id)
    reply_markup = build_main_menu_markup(user_id_str)

    all_users_data = context.bot_data.get('user_info', {})
    user_name = update.effective_user.first_name
    is_new_user = user_id_str not in all_users_data
    if not is_new_user:
        get_user_entry(all_users_data, user_id_str, user_name)
    else:
        initialize_user_entry(all_users_data, user_id_str, user_name)
    save_bot_data(all_users_data)

    full_name = " ".join(
        part for part in [update.effective_user.first_name, update.effective_user.last_name] if part
    ).strip()
    profile_name = full_name or (update.effective_user.username or "гость")

    welcome_message = msg_welcome if is_new_user else msg_welcome_back
    await update.message.reply_text(welcome_message.replace("<name and surname>", profile_name))
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
    parser = ArgumentParser(description="Run VPN Jesus bot")
    parser.add_argument(
        "--stdout-log",
        choices=["enable", "disable", "debug"],
        default="enable",
        help="Control stdout logging verbosity: debug=all logs, enable=info logs, disable=warnings and errors only.",
    )
    args = parser.parse_args()

    configure_logging(args.stdout_log)

    if not BOT_TOKEN:
        print("error: TELEGRAM_BOT_TOKEN environment variable not set.")
        exit()
    logger.debug("Starting bot with admin_id=%s data_file=%s", ADMIN_ID, DATA_FILE)

    application = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .connect_timeout(5.0)
        .read_timeout(20.0)
        .write_timeout(20.0)
        .pool_timeout(5.0)
        .build()
    )
    
    user_data = load_user_data()
    application.bot_data['user_info'] = user_data
    preload_active_users_into_xray(application.bot_data['user_info'])
    run_expired_subscriptions_offload(application.bot_data['user_info'], reason="startup")

    now = datetime.now()
    next_run = datetime.combine(now.date(), time(23, 59))
    if now >= next_run:
        next_run += timedelta(days=1)
    application.job_queue.run_repeating(
        daily_expired_subscriptions_offload,
        interval=timedelta(days=1),
        first=next_run,
        name="daily-expired-offload",
    )
    
    admin_reply_handler = MessageHandler(
        filters.TEXT & filters.REPLY & filters.User(user_id=int(ADMIN_ID)), 
        handle_admin_reply
    )
    application.add_handler(admin_reply_handler)

    application.add_handler(CommandHandler("start", handle_start))
    
    echo_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), handle_start_or_text)
    application.add_handler(echo_handler)
    application.add_error_handler(handle_error)
    
    print("bot is running...")
    #application.run_polling(poll_interval=0.0)
    application.run_polling(poll_interval=0.5, timeout=20.0, bootstrap_retries=3)
