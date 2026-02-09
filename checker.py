from subprocess import run
from sys import argv, exit
from time import sleep

from module import API_PORT, API_SERVER, get_user_connections, get_users_from_api

MAX_DEVICES = 2
POLL_INTERVAL = 3

def delete_user(email):
    run(["python3", "delete_user.py", email], check=False)

def monitor_sessions():
    active_connections = {}
    removed_users = set()

    while True:
        emails = get_users_from_api(API_SERVER, API_PORT)

        for email in emails:
            connections = get_user_connections(email, API_SERVER, API_PORT)
            active_connections[email] = set(connections)

            connection_count = len(active_connections[email])
            print(f"{email} -> {sorted(active_connections[email])}")

            if connection_count > MAX_DEVICES and email not in removed_users:
                print(f"too many devices for {email}, removing user")
                delete_user(email)
                removed_users.add(email)

            sleep(0.1)

        sleep(POLL_INTERVAL)

if __name__ == "__main__":
    if len(argv) > 1:
        print(f"usage: python3 {argv[0]}")
        exit(1)

    monitor_sessions()
