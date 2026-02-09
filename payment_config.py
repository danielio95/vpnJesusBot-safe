import json
import os
from datetime import datetime
from logging import basicConfig, DEBUG
import logging

basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=DEBUG,
)
logger = logging.getLogger(__name__)

FILENAME = "data.json"
ALLOWED_YEARS = ["2025", "2026", "2027", "2028"]
ALLOWED_MONTHS = [
    "jan", "feb", "mar", "apr", "may", "jun",
    "jul", "aug", "sep", "oct", "nov", "dec",
]
PAID = 1
UNPAID = 0

def create_empty_payments():
    logger.debug("Creating empty payments structure")
    return {year: {month: UNPAID for month in ALLOWED_MONTHS} for year in ALLOWED_YEARS}

def apply_duration_logic(structure, months_count):
    if months_count < 1:
        logger.debug("Duration logic skipped; months_count=%s", months_count)
        return

    now = datetime.now()
    current_year = now.year
    current_month_idx = now.month - 1

    print(f"Auto-filling {months_count} months starting from {now.strftime('%b %Y')}...")
    logger.debug("Applying duration months_count=%s start_year=%s start_month_idx=%s", months_count, current_year, current_month_idx)

    for i in range(months_count):
        target_idx_total = current_month_idx + i
        year_offset = target_idx_total // 12
        final_month_idx = target_idx_total % 12

        final_year = str(current_year + year_offset)
        final_month_name = ALLOWED_MONTHS[final_month_idx]

        if final_year in structure:
            structure[final_year][final_month_name] = PAID
            logger.debug("Marked paid year=%s month=%s", final_year, final_month_name)

def apply_manual_paid(structure, paid_args):
    for item in paid_args:
        try:
            if ":" not in item:
                print(f"Warning: Skipping '{item}' (Missing colon). Format: Year:Indices")
                logger.warning("Skipping manual paid item without colon: %s", item)
                continue

            year_str, data_str = item.split(":")
            if year_str not in structure:
                print(f"Warning: Year '{year_str}' not in allowed years. Skipping.")
                logger.warning("Skipping manual paid year outside allowed years: %s", year_str)
                continue

            groups = data_str.split(",")

            for group in groups:
                if "-" in group:
                    try:
                        start_s, end_s = group.split("-")
                        start, end = int(start_s), int(end_s)
                        for val in range(start, end + 1):
                            if 1 <= val <= 12:
                                month_name = ALLOWED_MONTHS[val - 1]
                                structure[year_str][month_name] = PAID
                                logger.debug("Marked paid year=%s month=%s via range %s", year_str, month_name, group)
                            else:
                                print(f"Warning: Month {val} in range {group} is out of bounds (1-12).")
                                logger.warning("Manual paid month out of bounds: %s", val)
                    except ValueError:
                        print(f"Warning: Invalid range format '{group}'. Use start-end (e.g., 1-10).")
                        logger.warning("Invalid manual paid range format: %s", group)
                else:
                    try:
                        val = int(group)
                        if 1 <= val <= 12:
                            month_name = ALLOWED_MONTHS[val - 1]
                            structure[year_str][month_name] = PAID
                            logger.debug("Marked paid year=%s month=%s via value", year_str, month_name)
                        else:
                            print(f"Warning: Month {val} is out of bounds (1-12).")
                            logger.warning("Manual paid month out of bounds: %s", val)
                    except ValueError:
                        print(f"Warning: '{group}' is not a valid number.")
                        logger.warning("Manual paid value is not a valid number: %s", group)
        except Exception as error:
            logger.exception("Error parsing manual paid item: %s", item)
            print(f"Error parsing item '{item}': {error}")

def load_data(filename=FILENAME):
    data = {}
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as file:
                content = file.read().strip()
                if content:
                    data = json.loads(content)
                    logger.debug("Loaded data entries=%s", len(data))
        except json.JSONDecodeError:
            logger.exception("JSON file corrupt: %s", filename)
            print("Error: JSON file corrupt. Starting fresh.")
    return data

def save_data(data, filename=FILENAME):
    logger.debug("Saving data entries=%s filename=%s", len(data), filename)
    with open(filename, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)
