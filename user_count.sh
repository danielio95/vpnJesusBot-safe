/usr/local/xray/xray api inbounduser --server=127.0.0.1:10002 -tag=vless-in \
|grep "email" \
|grep -v "ADMIN" \
|grep -v "7724842241" \
|grep -v "619189872" \
|grep -v "5154320206" \
|grep -v "5159386538" \
|grep -v "5879603362" \
|wc -l
