from module import remove_user_via_api
from sys import argv, exit

if __name__=='__main__':
    if len(argv)<2:
        print(f'usage: python3 {argv[0]} <email>')
        exit(1)

    email=argv[1]
    output = remove_user_via_api(email)
    if output.returncode != 0:
        print(output.stderr.strip() or "error: failed to remove user via api")
        exit(1)

    print(f"deleted user {email}")
