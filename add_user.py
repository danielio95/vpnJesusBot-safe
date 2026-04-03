from uuid import uuid4
from secrets import token_urlsafe
from sys import argv, exit
from os import getenv
from logging import basicConfig, DEBUG, getLogger
from module import update_singbox_users

basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=DEBUG,
)
logger = getLogger(__name__)

IP = getenv("SINGBOX_PUBLIC_IP", "0.0.0.0")
PORT = getenv("SINGBOX_PUBLIC_PORT", "443")
SNI = getenv("SINGBOX_TUIC_SNI", getenv("SINGBOX_REALITY_SNI", IP))
ALPN = getenv("SINGBOX_TUIC_ALPN", "h3")
CONGESTION_CONTROL = getenv("SINGBOX_TUIC_CONGESTION_CONTROL", "bbr")
UDP_RELAY_MODE = getenv("SINGBOX_TUIC_UDP_RELAY_MODE", "quic")
ALLOW_INSECURE = getenv("SINGBOX_TUIC_ALLOW_INSECURE", "0")


def _build_user_entry(email, user_id, password):
    return {
        "name": email,
        "uuid": user_id,
        "password": password,
    }


def add_user(email):
    user_id = str(uuid4())
    password = token_urlsafe(24)
    logger.debug("Adding sing-box TUIC user email=%s user_id=%s", email, user_id)

    def mutator(users):
        filtered = []
        for user in users:
            if not isinstance(user, dict):
                continue
            if user.get("name") == email or user.get("email") == email:
                continue
            filtered.append(user)
        filtered.append(_build_user_entry(email, user_id, password))
        users[:] = filtered
        return True, "created"

    success, details = update_singbox_users(mutator)
    if not success:
        logger.error("Failed to add user: %s", details)
        print(details or "error: could not add user")
        return None, None

    print(f"added user {email}")
    logger.debug("User added successfully email=%s password_set=%s", email, bool(password))
    return user_id, password


def add_user_with_id(email, user_id, password):
    logger.debug("Adding existing sing-box TUIC user email=%s user_id=%s", email, user_id)

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
        filtered.append(_build_user_entry(email, user_id, password))
        users[:] = filtered
        return True, "loaded"

    success, details = update_singbox_users(mutator)
    if not success:
        logger.error("Failed to add existing user: %s", details)
        return False

    logger.debug("Existing user loaded successfully email=%s user_id=%s", email, user_id)
    return True


def output_tuic_string(user_id, password):
    logger.debug("Outputting TUIC string for user_id=%s", user_id)
    print(
        f"tuic://{user_id}:{password}@{IP}:{PORT}"
        f"?alpn={ALPN}&congestion_control={CONGESTION_CONTROL}"
        f"&udp_relay_mode={UDP_RELAY_MODE}&sni={SNI}&allow_insecure={ALLOW_INSECURE}"
        "#telegram:@vpnjesusbot"
    )


if __name__ == "__main__":
    if len(argv) < 2:
        print(f"usage: python3 {argv[0]} <email>")
        exit(1)

    email = argv[1]
    logger.debug("Starting add_user with email=%s", email)
    user_id, password = add_user(email)
    if user_id and password:
        output_tuic_string(user_id, password)
