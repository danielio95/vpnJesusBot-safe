from module import list_users_from_stats, get_online_devices, XRAY_MAX_DEVICES
from subprocess import run
from sys import argv, exit
from time import sleep

POLL_SECONDS = 3

def delete_user(email):
    output = run(["python3", "delete_user.py", email], capture_output=True, text=True)
    if output.returncode != 0:
        print(output.stderr.strip() or f"error: failed to remove {email}")
        return False
    print(output.stdout.strip() or f"deleted user {email}")
    return True

def check_user_sessions():
    last_devices = {}

    while True:
        emails = list_users_from_stats()
        current_set = set(emails)

        for email in list(last_devices.keys()):
            if email not in current_set:
                last_devices.pop(email, None)

        for email in emails:
            devices = get_online_devices(email)
            last_devices.setdefault(email, set())

            if len(devices) > XRAY_MAX_DEVICES and len(last_devices[email]) <= XRAY_MAX_DEVICES:
                print(f"{email} exceeded {XRAY_MAX_DEVICES} devices: {sorted(devices)}")
                if delete_user(email):
                    last_devices.pop(email, None)
                    continue

            last_devices[email] = devices
            sleep(0.1)

        sleep(POLL_SECONDS)

if __name__=='__main__':
    if len(argv) > 1:
        print(f'usage: python3 {argv[0]}')
        exit(1)

    check_user_sessions()
