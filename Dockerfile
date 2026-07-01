FROM teddysun/shadowsocks-libev

ENV SS_PORT=10000
ENV SS_PASSWORD=your-strong-password-here
ENV SS_METHOD=aes-256-gcm

CMD ss-server -s 0.0.0.0 -p $SS_PORT -k $SS_PASSWORD -m $SS_METHOD
