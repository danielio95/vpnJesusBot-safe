from module import find_child,restart_xray
from sys import argv,exit
from json import load,dump

config_file='config.json'

def delete_user(inbound_tag,email):
    global config_file
    found_inbound=0

    with open(config_file,'r') as read:
        data=load(read)

    inbounds=find_child(data,'inbounds')
    for inbound in inbounds:
        values=list(inbound.values())
        if values[0]!=inbound_tag:
            continue
        found_inbound=1

        # remove client
        settings=find_child(inbound,'settings')
        clients=find_child(settings,'clients')

        client_to_remove=None
        count=0
        for client in clients:
            count+=1
            if client.get('email')==email:
                client_to_remove=client
                break
    
        if not client_to_remove:
            print(f'no user found with email: {email}')
            return 0
        clients.remove(client_to_remove)

        # remove shortId
        streamSettings=find_child(inbound,'streamSettings')
        realitySettings=find_child(streamSettings,'realitySettings')
        shortIds=find_child(realitySettings,'shortIds')

        short_id_to_remove=None
        for short_id in shortIds:
            count-=1
            if count==0:
                short_id_to_remove=short_id
                break

        if not short_id_to_remove:
            print(f'no corresponding shortId found with email: {email}')
        else:
            shortIds.remove(short_id_to_remove)

        # dump the rest of config back
        with open(config_file,'w') as write:
            dump(data,write,indent=4)

    if not found_inbound:
        print('no such inbound')
        exit(1)

    print(f'deleted user {email}')

if __name__=='__main__':
    if len(argv)<4:
        print(f'usage: python3 {argv[0]} <inbound_tag> <email> <restart>')
        exit(1)
    
    inbound_tag=argv[1]
    email=argv[2]
    restart=argv[3]

    delete_user(inbound_tag,email)
    if restart=='1':
        restart_xray()
