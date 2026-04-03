from sys import exit
from os import getenv
from json import JSONDecodeError, loads, dump
from shutil import move
from tempfile import NamedTemporaryFile
from subprocess import run
from logging import basicConfig, DEBUG, getLogger

basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=DEBUG,
)
logger = getLogger(__name__)


def find_child(data, parent):
    if parent not in data:
        logger.error("Missing key in data: %s", parent)
        print(f'error: {parent} key not found')
        exit(1)

    return data[parent]


SINGBOX_BIN = getenv("SINGBOX_BIN", "/usr/bin/sing-box")
SINGBOX_CONFIG_PATH = getenv("SINGBOX_CONFIG_PATH", "/etc/sing-box/config.json")
SINGBOX_SERVICE = getenv("SINGBOX_SERVICE", "sing-box.service")
SINGBOX_RELOAD_ACTION = getenv("SINGBOX_RELOAD_ACTION", "restart")
INBOUND_TAG = getenv("SINGBOX_INBOUND_TAG", "vless-in")
API_SERVER = getenv("SINGBOX_API_SERVER", "127.0.0.1")
API_PORT = getenv("SINGBOX_API_PORT", "9090")


def run_singbox_command(args):
    logger.debug("Running sing-box command args=%s", args)
    return run([SINGBOX_BIN] + args, capture_output=True, text=True)


def run_singbox_api(args):
    return run_singbox_command(["api"] + args)


def load_singbox_api_json(args):
    result = run_singbox_api(args)
    if result.returncode != 0:
        logger.error("sing-box api command failed: %s", result.stderr.strip() or "unknown error")
        print(result.stderr.strip() or "error: sing-box api command failed")
        return None

    output = result.stdout.strip()
    if not output:
        logger.debug("sing-box api returned empty output")
        return None

    try:
        logger.debug("Parsing sing-box api json output")
        return loads(output)
    except JSONDecodeError:
        logger.exception("Invalid json from sing-box api")
        print("error: invalid json from sing-box api")
        return None


def _load_config(config_path=SINGBOX_CONFIG_PATH):
    try:
        with open(config_path, "r", encoding="utf-8") as fh:
            return loads(fh.read())
    except FileNotFoundError:
        logger.error("sing-box config not found: %s", config_path)
        return None
    except JSONDecodeError:
        logger.exception("Invalid JSON in sing-box config: %s", config_path)
        return None


def _save_config(config_data, config_path=SINGBOX_CONFIG_PATH):
    config_dir = getenv("SINGBOX_CONFIG_DIR")
    temp_file = NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8", dir=config_dir)
    temp_path = temp_file.name
    try:
        dump(config_data, temp_file, ensure_ascii=False, indent=2)
        temp_file.flush()
    finally:
        temp_file.close()
    move(temp_path, config_path)


def _find_inbound(config_data, inbound_tag=INBOUND_TAG):
    inbounds = config_data.get("inbounds", []) if isinstance(config_data, dict) else []
    for inbound in inbounds:
        if isinstance(inbound, dict) and inbound.get("tag") == inbound_tag:
            return inbound
    return None


def _extract_users_container(inbound):
    if not isinstance(inbound, dict):
        return None
    users = inbound.get("users")
    if isinstance(users, list):
        return users

    # compatibility with possible converted configs
    settings = inbound.get("settings")
    if isinstance(settings, dict):
        users = settings.get("users") or settings.get("clients")
        if isinstance(users, list):
            return users

    return None


def update_singbox_users(mutator):
    config_data = _load_config()
    if config_data is None:
        return False, "error: sing-box config not loaded"

    inbound = _find_inbound(config_data)
    if inbound is None:
        return False, f"error: inbound tag not found ({INBOUND_TAG})"

    users = _extract_users_container(inbound)
    if users is None:
        inbound["users"] = []
        users = inbound["users"]

    changed, details = mutator(users)
    if not changed:
        return True, details

    _save_config(config_data)
    service_result = run(["sudo", "/usr/bin/systemctl", SINGBOX_RELOAD_ACTION, SINGBOX_SERVICE], capture_output=True, text=True)
    if service_result.returncode != 0:
        stderr = (service_result.stderr or service_result.stdout or "").strip()
        logger.error("Failed to %s %s: %s", SINGBOX_RELOAD_ACTION, SINGBOX_SERVICE, stderr)
        return False, stderr or f"error: failed to {SINGBOX_RELOAD_ACTION} {SINGBOX_SERVICE}"

    return True, details


def get_users_from_api(server=API_SERVER, port=API_PORT, inbound_tag=INBOUND_TAG):
    # sing-box default install may not have API enabled; use config as source of truth.
    config_data = _load_config()
    if config_data is None:
        return []

    inbound = _find_inbound(config_data, inbound_tag=inbound_tag)
    if inbound is None:
        return []

    users = _extract_users_container(inbound) or []
    names = []
    for user in users:
        if not isinstance(user, dict):
            continue
        name = user.get("name") or user.get("email")
        if name:
            names.append(str(name))

    return sorted(set(names))


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
    # Not available without sing-box API setup; keep behavior non-breaking.
    logger.debug("User connection checks require sing-box API; returning empty list for email=%s", email)
    return []
