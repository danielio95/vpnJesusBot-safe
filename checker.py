from module import find_child
from subprocess import run
from sys import argv,exit
from json import load,loads
from time import sleep

MAX_SESSIONS=2
config_file='config.json'
log_file='check.log'
server='127.0.0.1'
port='10002'

def check_user_sessions(inbound_tag,emails):
    global server
    global port
    global log_file

    # write log
    #log=open(log_file,'a+')
    
    while True:
        for email in emails:
            output=run(f'./xray api statsonline --server={server}:{port} -email {email}',shell=True,capture_output=True,text=True)
            if output.returncode!=0:
                continue
            data=loads(output.stdout.strip())
            stat=find_child(data,'stat')
            #log.write(str(stat)+'\n')
            print(stat)

            # check if online sessions > max sessions
            if stat.get('value')>MAX_SESSIONS:
                output=run(f'./xray api statsonlineiplist --server={server}:{port} -email {email}',shell=True,capture_output=True,text=True)
                if output.returncode!=0:
                    #log.write(f'couldnt get ips for {email}')
                    print(f'couldnt get ips for {email}')
                    continue
                data=loads(output.stdout.strip())
                ips=find_child(data,'ips')
                #log.write(str(ips)+'\n')
                print(ips)
                
                # block the last ip(s)
                count=0
                for ip in ips:
                    count+=1
                    if count>MAX_SESSIONS:
                        output=run(f'./xray api sib --server={server}:{port} -outbound=block -inbound={inbound_tag} {ip}',shell=True,capture_output=True,text=True)
                        #if 'duplicate ruleTag sourceIpBlock' in output.stderr:
                        #    pass
                        if output.returncode!=0:
                            #log.write(f'couldnt block {ip} for {email}')
                            print(f'couldnt block {ip} for {email}')
                        else:
                            #log.write(f'blocked {ip} from user {email}')
                            print(f'blocked {ip} from user {email}')

            sleep(0.1)
        sleep(3)

def get_emails(inbound_tag,emails):
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

        # get clients
        settings=find_child(inbound,'settings')
        clients=find_child(settings,'clients')

        for client in clients:
            emails.append(client.get('email'))

    if not found_inbound:
        print('no such inbound')
        exit(1)

if __name__=='__main__':
    if len(argv)<2:
        print(f'usage: python3 {argv[0]} <inbound_tag>')
        exit(1)

    inbound_tag=argv[1]
    emails=[]
    get_emails(inbound_tag,emails)
    check_user_sessions(inbound_tag,emails)
