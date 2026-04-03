from sys import argv, exit
from logging import basicConfig, DEBUG, getLogger
from module import update_singbox_users

basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=DEBUG,
)
logger = getLogger(__name__)


def delete_user(email):
    logger.debug("Deleting sing-box user email=%s", email)

    def mutator(users):
        before = len(users)
        users[:] = [
            user for user in users
            if isinstance(user, dict) and user.get("name") != email and user.get("email") != email
        ]
        removed = before - len(users)
        return removed > 0, f"removed={removed}"

    success, details = update_singbox_users(mutator)
    if not success:
        logger.error("Failed to delete user: %s", details)
        print(details or "error: could not delete user")
        return 0

    print(f"deleted user {email}")
    logger.debug("User deleted successfully email=%s details=%s", email, details)
    return 1


if __name__ == "__main__":
    if len(argv) < 2:
        print(f"usage: python3 {argv[0]} <email>")
        exit(1)

    logger.debug("Starting delete_user for email=%s", argv[1])
    delete_user(argv[1])
