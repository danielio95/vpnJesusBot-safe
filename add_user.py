import json
import os
import argparse
import sys
from datetime import datetime

# Configuration constants
FILENAME = "data.json"
ALLOWED_YEARS = ["2025", "2026", "2027", "2028"]
ALLOWED_MONTHS = [
    "jan", "feb", "mar", "apr", "may", "jun", 
    "jul", "aug", "sep", "oct", "nov", "dec"
]

def create_empty_payments():
    """Generates the structure with all '0's."""
    structure = {}
    for year in ALLOWED_YEARS:
        structure[year] = {month: "0" for month in ALLOWED_MONTHS}
    return structure

def apply_duration_logic(structure, months_count):
    """
    Sets 'months_count' number of months to '1' starting from current date.
    """
    if months_count < 1:
        return

    now = datetime.now()
    current_year = now.year
    current_month_idx = now.month - 1  # 0-11
    
    print(f"Auto-filling {months_count} months starting from {now.strftime('%b %Y')}...")

    for i in range(months_count):
        target_idx_total = current_month_idx + i
        
        # Calculate year offset and new month index
        year_offset = target_idx_total // 12
        final_month_idx = target_idx_total % 12
        
        final_year = str(current_year + year_offset)
        final_month_name = ALLOWED_MONTHS[final_month_idx]

        # Only set if the year exists in our allowed list
        if final_year in structure:
            structure[final_year][final_month_name] = "1"

def apply_manual_paid(structure, paid_args):
    """
    Parses strings like "2025:1,2,3" or "2027:1-10" and updates structure.
    """
    for item in paid_args:
        try:
            # 1. Check format Year:Data
            if ':' not in item:
                print(f"Warning: Skipping '{item}' (Missing colon). Format: Year:Indices")
                continue
            
            year_str, data_str = item.split(':')

            if year_str not in structure:
                print(f"Warning: Year '{year_str}' not in allowed years. Skipping.")
                continue

            # 2. Split by comma first to separate groups (e.g. "1-5,7,9-11")
            groups = data_str.split(',')
            
            for group in groups:
                # 3. Check for Range (e.g., "1-10")
                if '-' in group:
                    try:
                        start_s, end_s = group.split('-')
                        start, end = int(start_s), int(end_s)
                        
                        # Loop through the range (inclusive)
                        for val in range(start, end + 1):
                            if 1 <= val <= 12:
                                month_name = ALLOWED_MONTHS[val - 1]
                                structure[year_str][month_name] = "1"
                            else:
                                print(f"Warning: Month {val} in range {group} is out of bounds (1-12).")
                    except ValueError:
                        print(f"Warning: Invalid range format '{group}'. Use start-end (e.g., 1-10).")

                # 4. Handle Single Number (e.g., "5")
                else:
                    try:
                        val = int(group)
                        if 1 <= val <= 12:
                            month_name = ALLOWED_MONTHS[val - 1]
                            structure[year_str][month_name] = "1"
                        else:
                            print(f"Warning: Month {val} is out of bounds (1-12).")
                    except ValueError:
                        print(f"Warning: '{group}' is not a valid number.")
                        
        except Exception as e:
            print(f"Error parsing item '{item}': {e}")

def main():
    parser = argparse.ArgumentParser(description="Add user with duration and advanced manual selection.")
    
    parser.add_argument("--name", required=True, help="Name of the user")
    parser.add_argument("--id", required=True, help="Unique User ID")
    parser.add_argument("--date", required=True, help="Date value")
    
    # Duration argument (Optional, defaults to 0 if not provided)
    parser.add_argument("--months", type=int, default=0, choices=range(1, 37),
                        help="Auto-fill N months starting from today (1-36)")

    # Advanced Paid argument
    parser.add_argument("--paid", nargs='+', 
                        help="Manual overrides. Supports lists '2025:1,3' and ranges '2026:1-5'")

    args = parser.parse_args()

    # 1. Load Data
    data = {}
    if os.path.exists(FILENAME):
        try:
            with open(FILENAME, 'r', encoding='utf-8') as f:
                content = f.read()
                if content:
                    data = json.loads(content)
        except json.JSONDecodeError:
            print("Error: JSON file corrupt. Starting fresh.")

    # 2. Check Duplicates
    if args.id in data:
        print(f"Error: User ID '{args.id}' already exists.")
        sys.exit(1)

    # 3. Initialize Structure
    payment_structure = create_empty_payments()

    # 4. Apply Logic
    if args.months > 0:
        apply_duration_logic(payment_structure, args.months)
    
    if args.paid:
        apply_manual_paid(payment_structure, args.paid)

    # 5. Construct & Save
    new_entry = {
        "name": args.name,
        "date": args.date,
        "payments": payment_structure
    }

    data[args.id] = new_entry
    
    try:
        with open(FILENAME, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        print(f"Success: Added User ID '{args.id}' ({args.name}).")
    except Exception as e:
        print(f"Error saving file: {e}")

if __name__ == "__main__":
    main()
