from json import dump
from datetime import datetime, timezone
from module import list_users_from_stats

BACKUP_FILE = "users_backup.json"

def main():
    users = list_users_from_stats()
    backup = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(users),
        "users": users,
    }

    with open(BACKUP_FILE, "w", encoding="utf-8") as file:
        dump(backup, file, ensure_ascii=False, indent=4)

    print(f"backup saved to {BACKUP_FILE} ({len(users)} users)")

if __name__ == "__main__":
    main()
