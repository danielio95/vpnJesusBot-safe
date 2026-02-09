from os import getenv, urandom
from sys import argv, exit
from uuid import uuid4

from module import API_PORT, API_SERVER, run_xray_api

INBOUND_TAG = getenv("XRAY_INBOUND_TAG", "inbound")
LEVEL = int(getenv("XRAY_USER_LEVEL", "0"))
FLOW = getenv("XRAY_FLOW", "xtls-rprx-vision")
IP = getenv("XRAY_PUBLIC_IP", "x.x.x.x")
PORT = getenv("XRAY_PUBLIC_PORT", "443")
PBK = getenv("XRAY_REALITY_PBK", "x")
SNI = getenv("XRAY_REALITY_SNI", "x")
REALITY_SID = getenv("XRAY_REALITY_SID")

def add_user(email):
    user_id = str(uuid4())
    sid = REALITY_SID or str(urandom(8).hex())

    result = run_xray_api([
        "adduser",
        f"--server={API_SERVER}:{API_PORT}",
        f"--tag={INBOUND_TAG}",
        f"--email={email}",
        f"--uuid={user_id}",
        f"--level={LEVEL}",
    ])

    if result.returncode != 0:
        print(result.stderr.strip() or "error: could not add user")
        return None, None

    print(f"added user {email}")
    return user_id, sid

def output_vless_string(user_id, sid):
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
    user_id, sid = add_user(email)
    if user_id and sid:
        output_vless_string(user_id, sid)
