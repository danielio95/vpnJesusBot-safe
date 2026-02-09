import json
import os
import argparse
import sys
from datetime import datetime

FILENAME = "data.json"
ALLOWED_YEARS = ["2025", "2026", "2027", "2028"]
ALLOWED_MONTHS = [
    "jan", "feb", "mar", "apr", "may", "jun",
    "jul", "aug", "sep", "oct", "nov", "dec"
]
PAID_STATUS = "1"
UNPAID_STATUS = "0"

def create_empty_payments():
    structure = {}
    for year in ALLOWED_YEARS:
        structure[year] = {month: UNPAID_STATUS for month in ALLOWED_MONTHS}
    return structure

def apply_duration_logic(structure, months_count):
    if months_count < 1:
        return

    now = datetime.now()
    current_year = now.year
    current_month_idx = now.month - 1

    print(f"Auto-filling {months_count} months starting from {now.strftime('%b %Y')}...")

    for i in range(months_count):
        target_idx_total = current_month_idx + i
        year_offset = target_idx_total // 12
        final_month_idx = target_idx_total % 12

        final_year = str(current_year + year_offset)
        final_month_name = ALLOWED_MONTHS[final_month_idx]

        if final_year in structure:
            structure[final_year][final_month_name] = PAID_STATUS

def apply_manual_paid(structure, paid_args):
    for item in paid_args:
        try:
            if ':' not in item:
                print(f"Warning: Skipping '{item}' (Missing colon). Format: Year:Indices")
                continue

            year_str, data_str = item.split(':')

            if year_str not in structure:
                print(f"Warning: Year '{year_str}' not in allowed years. Skipping.")
                continue

            groups = data_str.split(',')

            for group in groups:
                if '-' in group:
                    try:
                        start_s, end_s = group.split('-')
                        start, end = int(start_s), int(end_s)

                        for val in range(start, end + 1):
                            if 1 <= val <= 12:
                                month_name = ALLOWED_MONTHS[val - 1]
                                structure[year_str][month_name] = PAID_STATUS
                            else:
                                print(f"Warning: Month {val} in range {group} is out of bounds (1-12).")
                    except ValueError:
                        print(f"Warning: Invalid range format '{group}'. Use start-end (e.g., 1-10).")
                else:
                    try:
                        val = int(group)
                        if 1 <= val <= 12:
                            month_name = ALLOWED_MONTHS[val - 1]
                            structure[year_str][month_name] = PAID_STATUS
                        else:
                            print(f"Warning: Month {val} is out of bounds (1-12).")
                    except ValueError:
                        print(f"Warning: '{group}' is not a valid number.")
        except Exception as e:
            print(f"Error parsing item '{item}': {e}")

def main():
    parser = argparse.ArgumentParser(description="Change user data by ID with duration and manual month selection.")

    parser.add_argument("--name", required=True, help="Name of the user")
    parser.add_argument("--id", required=True, help="Unique User ID")
    parser.add_argument("--date", required=True, help="Date value")
    parser.add_argument("--months", type=int, default=0, choices=range(1, 37),
                        help="Auto-fill N months starting from today (1-36)")
    parser.add_argument("--paid", nargs='+',
                        help="Manual overrides. Supports lists '2025:1,3' and ranges '2026:1-5'")

    args = parser.parse_args()

    data = {}
    if os.path.exists(FILENAME):
        try:
            with open(FILENAME, 'r', encoding='utf-8') as f:
                content = f.read()
                if content:
                    data = json.loads(content)
        except json.JSONDecodeError:
            print("Error: JSON file corrupt. Starting fresh.")

    if args.id not in data:
        print(f"Error: User ID '{args.id}' not found.")
        sys.exit(1)

    payment_structure = create_empty_payments()

    if args.months > 0:
        apply_duration_logic(payment_structure, args.months)

    if args.paid:
        apply_manual_paid(payment_structure, args.paid)

    updated_entry = {
        "name": args.name,
        "date": args.date,
        "payments": payment_structure
    }

    data[args.id] = updated_entry

    try:
        with open(FILENAME, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        print(f"Success: Updated User ID '{args.id}' ({args.name}).")
    except Exception as e:
        print(f"Error saving file: {e}")

if __name__ == "__main__":
    main()
