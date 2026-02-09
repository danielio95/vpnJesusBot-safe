from module import add_user_via_api
from sys import argv, exit
from os import getenv
from uuid import uuid4

VRAY_IP = getenv("XRAY_PUBLIC_IP", "x.x.x.x")
VRAY_PORT = getenv("XRAY_PUBLIC_PORT", "443")
VRAY_PBK = getenv("XRAY_REALITY_PBK", "x")
VRAY_SNI = getenv("XRAY_REALITY_SNI", "x")

def output_vless_string(user_id):
    print(
        f"vless://{user_id}@{VRAY_IP}:{VRAY_PORT}"
        f"?security=reality&encryption=none&pbk={VRAY_PBK}"
        f"&headerType=none&fp=chrome&type=tcp&flow=xtls-rprx-vision"
        f"&sni={VRAY_SNI}#xray"
    )

if __name__=='__main__':
    if len(argv)<2:
        print(f'usage: python3 {argv[0]} <email>')
        exit(1)

    email=argv[1]
    user_id=str(uuid4())
    output = add_user_via_api(email, user_id=user_id)
    if output.returncode != 0:
        print(output.stderr.strip() or "error: failed to add user via api")
        exit(1)

    print(f"added user {email}")
    output_vless_string(user_id)
