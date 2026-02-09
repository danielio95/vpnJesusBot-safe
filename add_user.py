from module import API_PORT, API_SERVER, run_xray_api
from logging import basicConfig, DEBUG, getLogger
from tempfile import NamedTemporaryFile
from os import getenv, urandom, remove
from sys import argv, exit
from uuid import uuid4
from json import dump

basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=DEBUG,
)
logger = getLogger(__name__)

INBOUND_TAG = getenv("XRAY_INBOUND_TAG", "inbound")
LEVEL = int(getenv("XRAY_USER_LEVEL", "0"))
FLOW = getenv("XRAY_FLOW", "xtls-rprx-vision")
IP = getenv("XRAY_PUBLIC_IP", "x.x.x.x")
PORT = getenv("XRAY_PUBLIC_PORT", "443")
PBK = getenv("XRAY_REALITY_PBK", "x")
SNI = getenv("XRAY_REALITY_SNI", "x")
REALITY_SID = getenv("XRAY_REALITY_SID")
INBOUND_LISTEN = getenv("XRAY_INBOUND_LISTEN", "0.0.0.0")
INBOUND_PORT = int(getenv("XRAY_INBOUND_PORT", "8443"))
INBOUND_PROTOCOL = getenv("XRAY_INBOUND_PROTOCOL", "vless")

def build_add_user_payload(email, user_id):
    return {
        "inbounds": [
            {
                "tag": INBOUND_TAG,
                "listen": INBOUND_LISTEN,
                "port": INBOUND_PORT,
                "protocol": INBOUND_PROTOCOL,
                "settings": {
                    "clients": [
                        {
                            "id": user_id,
                            "level": LEVEL,
                            "email": email,
                            "flow": FLOW,
                        }
                    ],
                    "decryption": "none",
                    "fallbacks": [],
                },
            }
        ]
    }

def add_user(email):
    user_id = str(uuid4())
    sid = REALITY_SID or str(urandom(8).hex())
    logger.debug("Adding user email=%s user_id=%s", email, user_id)
    payload = build_add_user_payload(email, user_id)
    temp_file = None
    temp_path = None
    try:
        temp_file = NamedTemporaryFile("w", suffix=".json", delete=False)
        dump(payload, temp_file)
        temp_file.flush()
        temp_path = temp_file.name
    finally:
        if temp_file is not None:
            temp_file.close()

    try:
        result = run_xray_api([
            "adu",
            f"--server={API_SERVER}:{API_PORT}",
            temp_path,
        ])
    finally:
        if temp_path:
            try:
                remove(temp_path)
            except FileNotFoundError:
                logger.warning("Temporary payload file already removed: %s", temp_path)

    if result.returncode != 0:
        logger.error("Failed to add user: %s", result.stderr.strip() or "unknown error")
        print(result.stderr.strip() or "error: could not add user")
        return None, None

    print(f"added user {email}")
    logger.debug("User added successfully email=%s sid=%s", email, sid)
    return user_id, sid

def output_vless_string(user_id, sid):
    logger.debug("Outputting VLESS string for user_id=%s sid=%s", user_id, sid)
    print(
        f"vless://{user_id}@{IP}:{PORT}"
        f"?security=reality&encryption=none&pbk={PBK}&headerType=none"
        f"&fp=chrome&type=tcp&flow={FLOW}&sni={SNI}&sid={sid}#xray"
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
