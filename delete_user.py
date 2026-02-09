from os import getenv
from sys import argv, exit
from logging import basicConfig, DEBUG, getLogger

from module import API_PORT, API_SERVER, run_xray_api

basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=DEBUG,
)
logger = getLogger(__name__)

INBOUND_TAG = getenv("XRAY_INBOUND_TAG", "inbound")

def delete_user(email):
    logger.debug("Deleting user email=%s", email)
    result = run_xray_api([
        "rmu",
        f"--server={API_SERVER}:{API_PORT}",
        f"-tag={INBOUND_TAG}",
        email
    ])

    if result.returncode != 0:
        logger.error("Failed to delete user: %s", result.stderr.strip() or "unknown error")
        print(result.stderr.strip() or "error: could not delete user")
        return 0

    print(f"deleted user {email}")
    logger.debug("User deleted successfully email=%s", email)
    return 1

if __name__ == "__main__":
    if len(argv) < 2:
        print(f"usage: python3 {argv[0]} <email>")
        exit(1)

    logger.debug("Starting delete_user for email=%s", argv[1])
    delete_user(argv[1])
