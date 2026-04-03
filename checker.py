from time import sleep
from subprocess import run
from sys import argv, exit
from logging import basicConfig, DEBUG, getLogger
from module import API_PORT, API_SERVER, get_user_connections, get_users_from_api

basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=DEBUG,
)
logger = getLogger(__name__)

MAX_DEVICES = 2
POLL_INTERVAL = 3

def delete_user(email):
    logger.debug("Deleting user via script email=%s", email)
    run(["python3", "offload_user.py", email], check=False)

def monitor_sessions():
    active_connections = {}
    removed_users = set()

    while True:
        logger.debug("Polling users from API server=%s port=%s", API_SERVER, API_PORT)
        emails = get_users_from_api(API_SERVER, API_PORT)

        for email in emails:
            connections = get_user_connections(email, API_SERVER, API_PORT)
            active_connections[email] = set(connections)

            connection_count = len(active_connections[email])
            print(f"{email} -> {sorted(active_connections[email])}")
            logger.debug("User %s connections=%s count=%s", email, sorted(active_connections[email]), connection_count)

            if connection_count > MAX_DEVICES and email not in removed_users:
                print(f"too many devices for {email}, removing user")
                logger.warning("Too many devices for user=%s, removing user", email)
                delete_user(email)
                removed_users.add(email)

            sleep(0.1)

        sleep(POLL_INTERVAL)

if __name__ == "__main__":
    if len(argv) > 1:
        print(f"usage: python3 {argv[0]}")
        exit(1)

    logger.debug("Starting session monitor max_devices=%s poll_interval=%s", MAX_DEVICES, POLL_INTERVAL)
    monitor_sessions()
