import json
from datetime import datetime

from module import API_PORT, API_SERVER, get_users_from_api

BACKUP_FILE = "users_backup.json"

def backup_users():
    users = get_users_from_api(API_SERVER, API_PORT)
    payload = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "users": [{"email": email} for email in users],
    }

    with open(BACKUP_FILE, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=4)

    print(f"backup saved to {BACKUP_FILE} ({len(users)} users)")

if __name__ == "__main__":
    backup_users()
