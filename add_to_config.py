import logging
from sys import exit
from argparse import ArgumentParser
from logging import basicConfig, DEBUG
from payment_config import (
    apply_duration_logic,
    apply_manual_paid,
    create_empty_payments,
    load_data,
    save_data,
)

basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=DEBUG,
)
logger = logging.getLogger(__name__)

def main():
    parser = ArgumentParser(description="Add user with duration and advanced manual selection.")
    
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
    logger.debug("Loading data for new user id=%s", args.id)
    data = load_data()

    # 2. Check Duplicates
    if args.id in data:
        logger.error("Duplicate user id detected: %s", args.id)
        print(f"Error: User ID '{args.id}' already exists.")
        exit(1)

    # 3. Initialize Structure
    payment_structure = create_empty_payments()

    # 4. Apply Logic
    if args.months > 0:
        logger.debug("Applying duration logic months=%s", args.months)
        apply_duration_logic(payment_structure, args.months)
    
    if args.paid:
        logger.debug("Applying manual paid overrides: %s", args.paid)
        apply_manual_paid(payment_structure, args.paid)

    # 5. Construct & Save
    new_entry = {
        "name": args.name,
        "date": int(args.date),
        "payments": payment_structure
    }

    data[args.id] = new_entry
    
    try:
        logger.debug("Saving data for user id=%s", args.id)
        save_data(data)
        print(f"Success: Added User ID '{args.id}' ({args.name}).")
    except Exception as e:
        logger.exception("Error saving data for user id=%s", args.id)
        print(f"Error saving file: {e}")

if __name__ == "__main__":
    main()
