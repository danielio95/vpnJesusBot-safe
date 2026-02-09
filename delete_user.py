from os import getenv
from sys import argv, exit

from module import API_PORT, API_SERVER, run_xray_api

INBOUND_TAG = getenv("XRAY_INBOUND_TAG", "inbound")

def delete_user(email):
    result = run_xray_api([
        "removeuser",
        f"--server={API_SERVER}:{API_PORT}",
        f"--tag={INBOUND_TAG}",
        f"--email={email}",
    ])

    if result.returncode != 0:
        print(result.stderr.strip() or "error: could not delete user")
        return 0

    print(f"deleted user {email}")
    return 1

if __name__ == "__main__":
    if len(argv) < 2:
        print(f"usage: python3 {argv[0]} <email>")
        exit(1)

    delete_user(argv[1])
