import argparse
import sys
from logging import basicConfig, DEBUG
import logging

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
    parser = argparse.ArgumentParser(description="Update existing user data in data.json.")

    parser.add_argument("--name", required=True, help="Name of the user")
    parser.add_argument("--id", required=True, help="Unique User ID")
    parser.add_argument("--date", required=True, help="Date value")
    parser.add_argument("--months", type=int, default=0, choices=range(1, 37),
                        help="Auto-fill N months starting from today (1-36)")
    parser.add_argument("--paid", nargs='+',
                        help="Manual overrides. Supports lists '2025:1,3' and ranges '2026:1-5'")

    args = parser.parse_args()

    logger.debug("Loading data for update user id=%s", args.id)
    data = load_data()

    if args.id not in data:
        logger.error("User id not found for update: %s", args.id)
        print(f"Error: User ID '{args.id}' does not exist.")
        sys.exit(1)

    payment_structure = create_empty_payments()

    if args.months > 0:
        logger.debug("Applying duration logic months=%s", args.months)
        apply_duration_logic(payment_structure, args.months)

    if args.paid:
        logger.debug("Applying manual paid overrides: %s", args.paid)
        apply_manual_paid(payment_structure, args.paid)

    data[args.id] = {
        "name": args.name,
        "date": int(args.date),
        "payments": payment_structure,
    }

    try:
        logger.debug("Saving updated data for user id=%s", args.id)
        save_data(data)
        print(f"Success: Updated User ID '{args.id}' ({args.name}).")
    except Exception as error:
        logger.exception("Error saving data for user id=%s", args.id)
        print(f"Error saving file: {error}")

if __name__ == "__main__":
    main()
