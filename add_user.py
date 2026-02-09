from module import restart_xray,find_child
from sys import argv,exit
from os import urandom
from uuid import uuid4
from json import load,dump

config_file='config.json'
ip='x.x.x.x'
port='443'
pbk='x'
sni='x'

def add_user(inbound_tag,uuid,level,email,sid):
    global config_file

    with open(config_file,'r') as read:
        data=load(read)

    inbounds=find_child(data,'inbounds')
    for inbound in inbounds:
        values=list(inbound.values())
        if values[0]!=inbound_tag:
            continue

        # add client
        settings=find_child(inbound,'settings')
        clients=find_child(settings,'clients')
        user={
            "id":uuid,
            "level":level,
            "email":email,
            "flow":"xtls-rprx-vision"
        }
        clients.append(user)

        # add shortId
        streamSettings=find_child(inbound,'streamSettings')
        realitySettings=find_child(streamSettings,'realitySettings')
        shortIds=find_child(realitySettings,'shortIds')
        shortIds.append(sid)

        # dump the rest of config back
        with open(config_file,'w') as write:
            dump(data,write,indent=4)

        print(f'added user {email} {sid}')
        return

#def create_json(uuid,level,email):
#    user_json={
#        "id":uuid,
#        "level":level,
#        "email":email,
#        "flow":"xtls-rptx-vision"
#    }
#
#    return json.dumps(user_json,indent=4)

def output_vless_string(uuid,sid):
    global ip
    global port
    global pbk
    global sni

    print(f'vless://{uuid}@{ip}:{port}?security=reality&encryption=none&pbk={pbk}&headerType=none&fp=chrome&type=tcp&flow=xtls-rprx-vision&sni={sni}&sid={sid}#xray')

if __name__=='__main__':
    if len(argv)<5:
        print(f'usage: python3 {argv[0]} <inbound_tag> <level> <email> <restart>')
        exit(1)
    
    uuid=str(uuid4())
    sid=str(urandom(8).hex())
    inbound_tag=argv[1]
    level=int(argv[2])
    email=argv[3]
    restart=argv[4]

    #user_json=create_json(uuid,level,email)
    add_user(inbound_tag,uuid,level,email,sid)
    output_vless_string(uuid,sid)
    if restart=='1':
        restart_xray()
