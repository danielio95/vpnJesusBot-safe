from uuid import uuid4
from sys import argv, exit
from os import getenv, urandom
from logging import basicConfig, DEBUG, getLogger
from module import update_singbox_users

basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=DEBUG,
)
logger = getLogger(__name__)

LEVEL = int(getenv("SINGBOX_USER_LEVEL", "1"))
FLOW = getenv("SINGBOX_FLOW", "xtls-rprx-vision")
IP = getenv("SINGBOX_PUBLIC_IP", "0.0.0.0")
PORT = getenv("SINGBOX_PUBLIC_PORT", "443")
PBK = getenv("SINGBOX_REALITY_PBK", "")
SNI = getenv("SINGBOX_REALITY_SNI", "")
SHORTID = getenv("SINGBOX_REALITY_SHORTID", "")


def _build_user_entry(email, user_id):
    entry = {
        "name": email,
        "uuid": user_id,
        "flow": FLOW,
    }
    if LEVEL >= 0:
        entry["level"] = LEVEL
    return entry


def add_user(email):
    user_id = str(uuid4())
    sid = SHORTID or str(urandom(8).hex())
    logger.debug("Adding sing-box user email=%s user_id=%s", email, user_id)

    def mutator(users):
        filtered = []
        for user in users:
            if not isinstance(user, dict):
                continue
            if user.get("name") == email or user.get("email") == email:
                continue
            filtered.append(user)
        filtered.append(_build_user_entry(email, user_id))
        users[:] = filtered
        return True, "created"

    success, details = update_singbox_users(mutator)
    if not success:
        logger.error("Failed to add user: %s", details)
        print(details or "error: could not add user")
        return None, None

    print(f"added user {email}")
    logger.debug("User added successfully email=%s sid=%s", email, sid)
    return user_id, sid


def add_user_with_id(email, user_id):
    logger.debug("Adding existing sing-box user email=%s user_id=%s", email, user_id)

    def mutator(users):
        filtered = []
        for user in users:
            if not isinstance(user, dict):
                continue
            if user.get("name") == email or user.get("email") == email:
                continue
            if user.get("uuid") == user_id:
                continue
            filtered.append(user)
        filtered.append(_build_user_entry(email, user_id))
        users[:] = filtered
        return True, "loaded"

    success, details = update_singbox_users(mutator)
    if not success:
        logger.error("Failed to add existing user: %s", details)
        return False

    logger.debug("Existing user loaded successfully email=%s user_id=%s", email, user_id)
    return True


def output_vless_string(user_id, sid):
    logger.debug("Outputting VLESS string for user_id=%s sid=%s", user_id, sid)
    print(
        f"vless://{user_id}@{IP}:{PORT}"
        f"?security=reality&encryption=none&pbk={PBK}&headerType=none"
        f"&fp=chrome&type=tcp&flow={FLOW}&sni={SNI}&sid={sid}#sing-box"
    )


if __name__ == "__main__":
    if len(argv) < 2:
        print(f"usage: python3 {argv[0]} <email>")
        exit(1)

    email = argv[1]
    logger.debug("Starting add_user with email=%s", email)
    user_id, sid = add_user(email)
    if user_id and sid:
        output_vless_string(user_id, sid)
