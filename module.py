from sys import exit
from os import getenv
from json import JSONDecodeError, loads, dump
from shutil import move
from tempfile import NamedTemporaryFile
from subprocess import run
from logging import basicConfig, DEBUG, getLogger
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import urlopen

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
INBOUND_TAG = getenv("SINGBOX_INBOUND_TAG", "tuic-in")
API_SERVER = getenv("SINGBOX_API_SERVER", "127.0.0.1")
API_PORT = getenv("SINGBOX_API_PORT", "9090")
API_TIMEOUT_SECONDS = float(getenv("SINGBOX_API_TIMEOUT_SECONDS", "5"))
API_USER_ENDPOINTS = tuple(
    endpoint.strip() for endpoint in getenv("SINGBOX_API_USER_ENDPOINTS", "/users,/connections").split(",")
    if endpoint.strip()
)
API_CONNECTION_ENDPOINTS = tuple(
    endpoint.strip() for endpoint in getenv("SINGBOX_API_CONNECTION_ENDPOINTS", "/connections").split(",")
    if endpoint.strip()
)
API_PAGE_SIZE = int(getenv("SINGBOX_API_PAGE_SIZE", "1000"))
SYSTEMCTL_BIN = getenv("SINGBOX_SYSTEMCTL_BIN", "/usr/bin/systemctl")
SYSTEMCTL_USE_SUDO = getenv("SINGBOX_SYSTEMCTL_USE_SUDO", "0").strip() == "1"


def run_singbox_command(args):
    logger.debug("Running sing-box command args=%s", args)
    return run([SINGBOX_BIN] + args, capture_output=True, text=True)


def run_systemctl(action, service=SINGBOX_SERVICE):
    cmd = ["sudo", SYSTEMCTL_BIN, action, service]
    if SYSTEMCTL_USE_SUDO:
        cmd.insert(0, "sudo")
    logger.debug("Running systemctl command: %s", cmd)
    return run(cmd, capture_output=True, text=True)


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
    service_result = run_systemctl(SINGBOX_RELOAD_ACTION, SINGBOX_SERVICE)
    if service_result.returncode != 0:
        stderr = (service_result.stderr or service_result.stdout or "").strip()
        logger.error("Failed to %s %s: %s", SINGBOX_RELOAD_ACTION, SINGBOX_SERVICE, stderr)
        return False, stderr or f"error: failed to {SINGBOX_RELOAD_ACTION} {SINGBOX_SERVICE}"

    return True, details


def _api_base_url(server=API_SERVER, port=API_PORT):
    server = str(server).strip()
    if server.startswith(("http://", "https://")):
        return server.rstrip("/")
    return f"http://{server}:{port}".rstrip("/")


def _api_url(server, port, endpoint, params=None):
    endpoint = endpoint if endpoint.startswith("/") else f"/{endpoint}"
    url = urljoin(f"{_api_base_url(server, port)}/", endpoint.lstrip("/"))
    if params:
        url = f"{url}?{urlencode(params)}"
    return url


def _load_api_json(server, port, endpoint, params=None):
    url = _api_url(server, port, endpoint, params=params)
    try:
        with urlopen(url, timeout=API_TIMEOUT_SECONDS) as response:
            body = response.read().decode("utf-8")
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        logger.debug("API request failed url=%s error=%s", url, exc)
        return None

    if not body.strip():
        return None

    try:
        return loads(body)
    except JSONDecodeError:
        logger.debug("API returned invalid JSON url=%s body=%s", url, body[:500])
        return None


def _paginated_api_json(server, port, endpoint):
    """Fetch every page from Netrika/sing-box-style API endpoints."""
    first_page = _load_api_json(server, port, endpoint)
    if first_page is None:
        return []

    results = [first_page]
    if isinstance(first_page, dict):
        next_url = first_page.get("next") or first_page.get("next_url")
        page = first_page.get("page") or 1
        total_pages = first_page.get("total_pages") or first_page.get("pages")
        while next_url:
            try:
                with urlopen(next_url, timeout=API_TIMEOUT_SECONDS) as response:
                    next_page = loads(response.read().decode("utf-8"))
            except (HTTPError, URLError, TimeoutError, OSError, JSONDecodeError) as exc:
                logger.debug("Paginated API request failed url=%s error=%s", next_url, exc)
                break
            results.append(next_page)
            next_url = next_page.get("next") or next_page.get("next_url") if isinstance(next_page, dict) else None

        if total_pages:
            for page_no in range(int(page) + 1, int(total_pages) + 1):
                page_data = _load_api_json(server, port, endpoint, {"page": page_no, "limit": API_PAGE_SIZE})
                if page_data is not None:
                    results.append(page_data)
    return results


def _items_from_payload(payload):
    if isinstance(payload, list):
        for item in payload:
            yield item
        return

    if not isinstance(payload, dict):
        return

    for key in ("users", "clients", "connections", "items", "data", "results", "statuses"):
        value = payload.get(key)
        if isinstance(value, list):
            for item in value:
                yield item
        elif isinstance(value, dict):
            for item in _items_from_payload(value):
                yield item

    # Some status endpoints are shaped as {"user@example": [connections...]}.
    for key, value in payload.items():
        if key in {"users", "clients", "connections", "items", "data", "results", "statuses", "page", "pages", "total_pages", "next", "next_url"}:
            continue
        if isinstance(value, (list, dict)):
            yield {"name": key, "connections": value}


def _user_name_from_item(item):
    if not isinstance(item, dict):
        return None
    for key in ("name", "email", "user", "username", "client", "client_id"):
        value = item.get(key)
        if value:
            return str(value)
    return None


def _api_user_names(server=API_SERVER, port=API_PORT):
    names = []
    for endpoint in API_USER_ENDPOINTS:
        for payload in _paginated_api_json(server, port, endpoint):
            for item in _items_from_payload(payload):
                name = _user_name_from_item(item)
                if name:
                    names.append(name)
    return sorted(set(names))


def get_users_from_api(server=API_SERVER, port=API_PORT, inbound_tag=INBOUND_TAG):
    api_names = _api_user_names(server, port)
    if api_names:
        return api_names

    # If the API is unavailable, use config as a non-breaking fallback.
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


def _item_belongs_to_user(item, email):
    if not isinstance(item, dict):
        return False
    wanted = str(email)
    for key in ("name", "email", "user", "username", "client", "client_id"):
        value = item.get(key)
        if value is not None and str(value) == wanted:
            return True
    return False


def _connection_entries_for_item(item):
    if not isinstance(item, dict):
        return [item]
    for key in ("connections", "clients", "devices", "sessions", "ips"):
        value = item.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            return list(value.values())
    return [item]


def get_user_connections(email, server=API_SERVER, port=API_PORT):
    connections = []
    for endpoint in API_CONNECTION_ENDPOINTS:
        for payload in _paginated_api_json(server, port, endpoint):
            for item in _items_from_payload(payload):
                if not _item_belongs_to_user(item, email):
                    continue
                for connection in _connection_entries_for_item(item):
                    normalized = normalize_connection(connection)
                    if normalized:
                        connections.append(normalized)

    if not connections:
        logger.debug("No active connections found from API for email=%s", email)
    return sorted(set(connections))
