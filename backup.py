from json import dump
from datetime import datetime
from logging import basicConfig, DEBUG, getLogger
from module import API_PORT, API_SERVER, get_users_from_api

basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=DEBUG,
)
logger = getLogger(__name__)

BACKUP_FILE = "users_backup.json"

def backup_users():
    logger.debug("Starting backup from server=%s port=%s", API_SERVER, API_PORT)
    users = get_users_from_api(API_SERVER, API_PORT)
    payload = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "users": [{"email": email} for email in users],
    }

    logger.debug("Writing backup file %s", BACKUP_FILE)
    with open(BACKUP_FILE, "w", encoding="utf-8") as file:
        dump(payload, file, ensure_ascii=False, indent=4)

    print(f"backup saved to {BACKUP_FILE} ({len(users)} users)")
    logger.debug("Backup complete users=%s", len(users))

if __name__ == "__main__":
    backup_users()
