from subprocess import run,CalledProcessError
from sys import argv,exit

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
