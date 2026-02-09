import json
from os import getenv
from subprocess import run, CalledProcessError
from sys import exit

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

XRAY_BIN = getenv("XRAY_BIN", "./xray")
API_SERVER = getenv("XRAY_API_SERVER", "127.0.0.1")
API_PORT = getenv("XRAY_API_PORT", "10002")

def run_xray_api(args):
    return run([XRAY_BIN, "api"] + args, capture_output=True, text=True)

def load_xray_api_json(args):
    result = run_xray_api(args)
    if result.returncode != 0:
        print(result.stderr.strip() or "error: xray api command failed")
        return None

    output = result.stdout.strip()
    if not output:
        return None

    try:
        return json.loads(output)
    except json.JSONDecodeError:
        print("error: invalid json from xray api")
        return None

def extract_emails_from_stats(stats):
    emails = set()
    for stat in stats:
        name = stat.get("name", "")
        if "user>>>" not in name:
            continue
        remainder = name.split("user>>>", 1)[1]
        email = remainder.split(">>>", 1)[0].strip()
        if email:
            emails.add(email)
    return sorted(emails)

def get_users_from_api(server=API_SERVER, port=API_PORT):
    data = load_xray_api_json([
        "statsquery",
        f"--server={server}:{port}",
        "--pattern",
        "user>>>",
        "--reset=false",
    ])
    if not data:
        return []

    stats = data.get("stat", [])
    if isinstance(stats, dict):
        stats = [stats]
    if not isinstance(stats, list):
        return []
    return extract_emails_from_stats(stats)

def normalize_connection(entry):
    if isinstance(entry, dict):
        ip = entry.get("ip") or entry.get("address")
        port = entry.get("port")
        if ip and port:
            return f"{ip}:{port}"
        if ip:
            return str(ip)
    if isinstance(entry, (list, tuple)) and len(entry) >= 2:
        return f"{entry[0]}:{entry[1]}"
    if isinstance(entry, str):
        return entry.strip()
    return str(entry)

def get_user_connections(email, server=API_SERVER, port=API_PORT):
    data = load_xray_api_json([
        "statsonlineiplist",
        f"--server={server}:{port}",
        "-email",
        email,
    ])
    if not data:
        return []

    ips = data.get("ips", [])
    if isinstance(ips, dict):
        ips = [ips]
    if not isinstance(ips, list):
        return []
    return [normalize_connection(entry) for entry in ips]
