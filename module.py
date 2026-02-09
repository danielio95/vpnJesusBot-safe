from sys import exit
from os import getenv
from logging import basicConfig, DEBUG, getLogger
from json import JSONDecodeError, loads
from subprocess import run, CalledProcessError

basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=DEBUG,
)
logger = getLogger(__name__)

#def restart_xray():
#    try:
#        run(['sudo','systemctl','restart','xray.service'],check=True)
#        print('xray restarted')
#        logger.debug("xray service restarted successfully")
#    except CalledProcessError as error:
#        logger.exception("Failed to restart xray service")
#        print(f'error: {error}')

def find_child(data,parent):
    if parent not in data:
        logger.error("Missing key in data: %s", parent)
        print(f'error: {parent} key not found')
        exit(1)

    return data[parent]

XRAY_BIN = getenv("XRAY_BIN", "./xray")
API_SERVER = getenv("XRAY_API_SERVER", "127.0.0.1")
API_PORT = getenv("XRAY_API_PORT", "10002")
INBOUND_TAG = getenv("XRAY_INBOUND_TAG", "inbound")

def run_xray_api(args):
    logger.debug("Running xray api command args=%s", args)
    return run([XRAY_BIN, "api"] + args, capture_output=True, text=True)

def load_xray_api_json(args):
    result = run_xray_api(args)
    if result.returncode != 0:
        logger.error("xray api command failed: %s", result.stderr.strip() or "unknown error")
        print(result.stderr.strip() or "error: xray api command failed")
        return None

    output = result.stdout.strip()
    if not output:
        logger.debug("xray api returned empty output")
        return None

    try:
        logger.debug("Parsing xray api json output")
        return loads(output)
    except JSONDecodeError:
        logger.exception("Invalid json from xray api")
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
    logger.debug("Extracted %s emails from stats", len(emails))
    return sorted(emails)

def get_users_from_api(server=API_SERVER, port=API_PORT, inbound_tag=INBOUND_TAG):
    logger.debug(
        "Fetching users from api server=%s port=%s inbound_tag=%s",
        server,
        port,
        inbound_tag,
    )
    data = load_xray_api_json([
        "inbounduser",
        f"--server={server}:{port}",
        f"-tag={inbound_tag}",
    ])
    if not data:
        logger.debug("No data returned from api")
        return []

    users = data.get("users", [])
    if isinstance(users, dict):
        users = [users]
    if not isinstance(users, list):
        logger.debug("Unexpected users type=%s", type(users))
        return []
    emails = [entry.get("email") for entry in users if isinstance(entry, dict)]
    filtered = sorted({email for email in emails if email})
    logger.debug("Collected %s emails from inbound users", len(filtered))
    return filtered

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
    logger.debug("Fetching user connections email=%s server=%s port=%s", email, server, port)
    data = load_xray_api_json([
        "statsonlineiplist",
        f"--server={server}:{port}",
        "-email",
        email,
    ])
    if not data:
        logger.debug("No connection data returned for email=%s", email)
        return []

    ips = data.get("ips", [])
    if isinstance(ips, dict):
        ips = [ips]
    if not isinstance(ips, list):
        logger.debug("Unexpected ips type=%s for email=%s", type(ips), email)
        return []
    connections = [normalize_connection(entry) for entry in ips]
    logger.debug("Normalized %s connections for email=%s", len(connections), email)
    return connections
