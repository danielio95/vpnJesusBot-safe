from os import getenv, path
from json import load, dump, JSONDecodeError
from logging import basicConfig, INFO, error
from logging.handlers import RotatingFileHandler
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters

# --- CONFIGURATION ---
ADMIN_ID = getenv("TELEGRAM_ADMIN_ID")
BOT_TOKEN = getenv("TELEGRAM_BOT_TOKEN")
DATA_FILE = "data.json"

basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=INFO,
    handlers=[
        # Writes to output.log, max 5MB, keeps 2 old copies, utf-8 encoding
        RotatingFileHandler("output.log", maxBytes=5*1024*1024, backupCount=2, encoding='utf-8')
    ]
)

# --- MESSAGES ---

msg_error = "Возникла проблема. Пожалуйста, сообщите администратору."
msg_paid_full = "Оплачено до 2029 года."
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

# --- DATA MANAGEMENT ---

def load_user_data(filename=DATA_FILE):
    """
    Loads user data from the JSON file.
    Returns an empty dict if file is missing or broken.
    """
    base_path = path.dirname(__file__)
    file_path = path.join(base_path, filename)
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return load(f)
    except (FileNotFoundError, JSONDecodeError):
        return {}

# func for validating vpn after the payment

# def save_bot_data(data, filename=DATA_FILE):
#     """
#     Saves the dictionary back to the JSON file.
#     """
#     base_path = path.dirname(__file__)
#     file_path = path.join(base_path, filename)
#     with open(file_path, 'w', encoding='utf-8') as f:
#         dump(data, f, indent=4, ensure_ascii=False)

# --- LOGIC HELPERS ---

def get_payment_status(user_data):
    """
    1. If current month is unpaid -> Unpaid.
    2. If current month is paid and today <= due_day -> Paid.
    3. If current month is paid and today > due_day:
       - If next month is unpaid -> Unpaid.
       - If next month is paid -> Paid.
    """
    payments = user_data.get("payments", {})

    # Get user's billing day
    try:
        due_day = int(user_data.get("date", 1))
    except (ValueError, TypeError):
        due_day = 1

    month_map = {
        1: 'jan', 2: 'feb', 3: 'mar', 4: 'apr', 5: 'may', 6: 'jun',
        7: 'jul', 8: 'aug', 9: 'sep', 10: 'oct', 11: 'nov', 12: 'dec'
    }

    now = datetime.now()
    curr_year = now.year
    curr_month_idx = now.month
    curr_day = now.day

    curr_month_key = month_map[curr_month_idx]
    curr_status = str(payments.get(str(curr_year), {}).get(curr_month_key, "0"))

    if curr_status == "0":
        return msg_unpaid, None

    next_month_idx = curr_month_idx + 1
    next_year = curr_year
    if next_month_idx > 12:
        next_month_idx = 1
        next_year += 1
    next_month_key = month_map[next_month_idx]
    next_status = str(payments.get(str(next_year), {}).get(next_month_key, "0"))

    if curr_day > due_day and next_status == "0":
        return msg_unpaid, None

    # If we are here, user has access. Now find the Next Payment Date.
    # We start searching from the month AFTER the current month.
    search_month_idx = curr_month_idx + 1
    search_year = curr_year

    # Normalize start date if month overflowed
    if search_month_idx > 12:
        search_month_idx = 1
        search_year += 1

    next_unpaid_str = None

    # Loop through years (Extend range if you add 2029, 2030 to JSON)
    for y in range(search_year, 2030):
        # For the starting year, start from search_month_idx. For later years, start from Jan (1).
        m_start = search_month_idx if y == search_year else 1

        for m in range(m_start, 13):
            m_key = month_map[m]

            # Look up in JSON. Default to '0' (Unpaid) if year/month missing
            val = str(payments.get(str(y), {}).get(m_key, "0"))


            if val == "0":
                # Found the first unpaid month (e.g., Feb)
                # But we want to show the expiration date, which is in the PREVIOUS month (e.g., Jan)

                prev_m = m - 1
                prev_y = y

                # Handle year rollback (if Jan is unpaid, previous is Dec of last year)
                if prev_m < 1:
                    prev_m = 12
                    prev_y -= 1

                prev_key = month_map[prev_m]

                next_unpaid_str = f"{due_day} {prev_key} {prev_y}"
                break

            # if val == "0":
            #     # Found the first unpaid month!
            #     next_unpaid_str = f"{due_day} {m_key} {y}"
            #     break

        if next_unpaid_str:
            break

    # D. Return result
    if next_unpaid_str:
        return msg_paid, next_unpaid_str
    else:
        # Loop finished and no "0" was found.
        # This means they are paid up to the end of your configured years.
        return msg_paid, msg_paid_full

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
    
    # Retrieve the global data
    all_users_data = context.bot_data.get('user_info', {})

    # Define the main keyboard menu
    keyboard = [[btn_1], [btn_2]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    # --- LOGIC 1: CHECK PAYMENT ---
    if user_text == btn_1:
        context.user_data['awaiting_question'] = False

        found_user = all_users_data.get(user_id_str)

        if found_user:
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
        await update.message.reply_text( msg_question, reply_markup=reply_markup )

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
        
        await context.bot.send_message(chat_id=ADMIN_ID, text=msg_to_admin)
        await update.message.reply_text(msg_question_sent, reply_markup=reply_markup)

    # --- DEFAULT: SHOW MENU ---
    else:
        await update.message.reply_text(msg_menu, reply_markup=reply_markup)


async def handle_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler for Admin replies. Extracts User ID and Message ID to send a proper reply.
    """
    if update.message.reply_to_message:
        original_text = update.message.reply_to_message.text
        
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
                
                await update.message.reply_text(admin_sent+target_user_id)
            else:
                await update.message.reply_text(admin_id_error)
                
        except Exception as e:
            error(admin_error+e)
            await update.message.reply_text(admin_error)

if __name__ == '__main__':
    if not BOT_TOKEN:
        print("error: TELEGRAM_BOT_TOKEN environment variable not set.")
        exit()

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
    
    print("bot is running...")
    application.run_polling(poll_interval=0.0)
