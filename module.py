from subprocess import run, CalledProcessError
from sys import argv, exit
from os import getenv
from json import loads, dump, JSONDecodeError
from tempfile import NamedTemporaryFile
from os import remove

XRAY_BIN = getenv("XRAY_BIN", "./xray")
XRAY_API_ADDRESS = getenv("XRAY_API_ADDRESS", "127.0.0.1")
XRAY_API_PORT = getenv("XRAY_API_PORT", "10002")
XRAY_INBOUND_TAG = getenv("XRAY_INBOUND_TAG", "inbound")
XRAY_USER_LEVEL = int(getenv("XRAY_USER_LEVEL", "0"))
XRAY_USER_FLOW = getenv("XRAY_USER_FLOW", "xtls-rprx-vision")
XRAY_MAX_DEVICES = int(getenv("XRAY_MAX_DEVICES", "2"))

def restart_xray():
    try:
        run(['sudo','systemctl','restart','xray.service'],check=True)
        print('xray restarted')
    except CalledProcessError as error:
        print(f'error: {error}')

def find_child(data,parent):
    if parent not in data:
        print(f'error: {parent} key not found')
        exit(1)

    return data[parent]

def xray_server():
    return f"{XRAY_API_ADDRESS}:{XRAY_API_PORT}"

def run_xray_api(args, check=False):
    command = [XRAY_BIN, "api", *args, f"--server={xray_server()}"]
    return run(command, capture_output=True, text=True, check=check)

def run_xray_api_with_payload(command, payload, check=False):
    temp_file = NamedTemporaryFile("w", delete=False, encoding="utf-8")
    try:
        dump(payload, temp_file, ensure_ascii=False, indent=4)
        temp_file.flush()
        temp_file.close()
        command_args = [XRAY_BIN, "api", command, f"--server={xray_server()}", temp_file.name]
        return run(command_args, capture_output=True, text=True, check=check)
    finally:
        try:
            remove(temp_file.name)
        except FileNotFoundError:
            pass

def parse_xray_json(output, context):
    try:
        return loads(output)
    except JSONDecodeError:
        print(f"error: failed to parse xray api output for {context}")
        return {}

def list_users_from_stats():
    output = run_xray_api(["statsquery", "--pattern", "user>>>"])
    if output.returncode != 0:
        print("error: failed to query stats for users")
        return []
    data = parse_xray_json(output.stdout.strip(), "statsquery")
    stats = data.get("stat", [])
    emails = set()
    for item in stats:
        name = item.get("name", "")
        parts = name.split(">>>")
        if len(parts) >= 2 and parts[0] == "user":
            emails.add(parts[1])
    return sorted(emails)

def get_online_devices(email):
    output = run_xray_api(["statsonlineiplist", "-email", email])
    if output.returncode != 0:
        return set()
    data = parse_xray_json(output.stdout.strip(), f"statsonlineiplist:{email}")
    ips = data.get("ips", [])
    return set(ips)

def add_user_via_api(email, inbound_tag=None, level=None, flow=None, user_id=None):
    inbound_tag = inbound_tag or XRAY_INBOUND_TAG
    level = XRAY_USER_LEVEL if level is None else level
    flow = flow or XRAY_USER_FLOW
    payload = {
        "inbounds": [
            {
                "tag": inbound_tag,
                "settings": {
                    "clients": [
                        {
                            "id": user_id,
                            "level": level,
                            "email": email,
                            "flow": flow,
                        }
                    ]
                },
            }
        ]
    }
    return run_xray_api_with_payload("adu", payload)

def remove_user_via_api(email, inbound_tag=None):
    inbound_tag = inbound_tag or XRAY_INBOUND_TAG
    payload = {
        "inbounds": [
            {
                "tag": inbound_tag,
                "settings": {
                    "clients": [
                        {
                            "email": email,
                        }
                    ]
                },
            }
        ]
    }
    return run_xray_api_with_payload("rmu", payload)
