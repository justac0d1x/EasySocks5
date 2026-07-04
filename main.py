import socket
import struct
import threading
import select
import os
import sys
import signal
import json
import time
from datetime import datetime, timedelta

# ─── Глобальная переменная для uptime ────────────────────────────────────────
start_time = time.time()


def handle_http_client(client_socket, addr):
    """HTTP endpoint для health check /hello."""
    try:
        request = client_socket.recv(1024).decode('utf-8', errors='ignore')
        path = request.split()[1] if request else '/'

        uptime_seconds = int(time.time() - start_time)
        uptime_str = str(timedelta(seconds=uptime_seconds))

        response_data = {
            "status": "ok",
            "service": "SOCKS5 Proxy",
            "uptime_seconds": uptime_seconds,
            "uptime_human": uptime_str,
            "timestamp": datetime.now().isoformat(),
            "version": "1.0",
            "path": path
        }

        response_json = json.dumps(response_data)

        response = (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: application/json\r\n"
            f"Content-Length: {len(response_json)}\r\n"
            "Connection: close\r\n"
            "\r\n"
            f"{response_json}"
        )
        client_socket.send(response.encode())

    except Exception as e:
        print(f"[-] HTTP ошибка от {addr}: {e}")
    finally:
        try:
            client_socket.close()
        except Exception:
            pass


def forward_data(source, dest):
    """Туннелирование данных между сокетами."""
    try:
        while True:
            # Используем select с корректными параметрами: (readable, writable, error, timeout)
            rlist, _, _ = select.select([source], [], [], 5)
            if not rlist:
                continue
            data = source.recv(4096)
            if not data:
                break
            dest.sendall(data)
    except Exception:
        pass
    finally:
        try:
            source.close()
        except Exception:
            pass
        try:
            dest.close()
        except Exception:
            pass


def handle_socks5_client(client_socket, addr):
    """Полноценный SOCKS5-обработчик с CONNECT + IPv4/IPv6/домен."""
    try:
        # ── Шаг 1: Приветствие (Greeting) ────────────────────────────────────
        data = client_socket.recv(262)
        if not data or data[0] != 0x05:
            client_socket.close()
            return

        n_methods = data[1] if len(data) > 1 else 0
        # Метод 0x00 = NO AUTHENTICATION REQUIRED
        client_socket.send(b'\x05\x00')

        # ── Шаг 2: Получаем REQUEST (CONNECT) ───────────────────────────────
        request = b''
        while len(request) < 4:
            chunk = client_socket.recv(4 - len(request))
            if not chunk:
                client_socket.close()
                return
            request += chunk

        ver, cmd, rsv, atyp = struct.unpack('!BBBB', request)

        if cmd != 0x01:  # Только CONNECT
            # Reply: Connection not allowed by ruleset
            reply = b'\x05\x02\x00\x01\x00\x00\x00\x00\x00\x00'
            client_socket.send(reply)
            client_socket.close()
            return

        # ── Шаг 3: Парсим адрес ───────────────────────────────────────────────
        target_addr = None
        target_port = None

        if atyp == 0x01:          # IPv4
            addr_bytes = b''
            while len(addr_bytes) < 4:
                chunk = client_socket.recv(4 - len(addr_bytes))
                if not chunk:
                    client_socket.close()
                    return
                addr_bytes += chunk
            target_addr = socket.inet_ntoa(addr_bytes)

            port_bytes = b''
            while len(port_bytes) < 2:
                chunk = client_socket.recv(2 - len(port_bytes))
                if not chunk:
                    client_socket.close()
                    return
                port_bytes += chunk
            target_port = struct.unpack('!H', port_bytes)[0]

        elif atyp == 0x03:        # Доменное имя
            len_byte = client_socket.recv(1)
            if not len_byte:
                client_socket.close()
                return
            addr_len = len_byte[0]

            addr_bytes = b''
            while len(addr_bytes) < addr_len:
                chunk = client_socket.recv(addr_len - len(addr_bytes))
                if not chunk:
                    client_socket.close()
                    return
                addr_bytes += chunk
            target_addr = addr_bytes.decode('utf-8', errors='replace')

            port_bytes = b''
            while len(port_bytes) < 2:
                chunk = client_socket.recv(2 - len(port_bytes))
                if not chunk:
                    client_socket.close()
                    return
                port_bytes += chunk
            target_port = struct.unpack('!H', port_bytes)[0]

        elif atyp == 0x04:        # IPv6
            addr_bytes = b''
            while len(addr_bytes) < 16:
                chunk = client_socket.recv(16 - len(addr_bytes))
                if not chunk:
                    client_socket.close()
                    return
                addr_bytes += chunk
            target_addr = socket.inet_ntop(socket.AF_INET6, addr_bytes)

            port_bytes = b''
            while len(port_bytes) < 2:
                chunk = client_socket.recv(2 - len(port_bytes))
                if not chunk:
                    client_socket.close()
                    return
                port_bytes += chunk
            target_port = struct.unpack('!H', port_bytes)[0]

        else:
            reply = b'\x05\x08\x00\x01\x00\x00\x00\x00\x00\x00'
            client_socket.send(reply)
            client_socket.close()
            return

        print(f"[+] SOCKS5: {target_addr}:{target_port}")

        # ── Шаг 4: Подключаемся к целевому серверу ────────────────────────────
        remote_socket = None
        try:
            remote_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            remote_socket.settimeout(10)
            remote_socket.connect((target_addr, target_port))
        except socket.gaierror:
            reply = b'\x05\x04\x00\x01\x00\x00\x00\x00\x00\x00'
            client_socket.send(reply)
            client_socket.close()
            return
        except Exception as e:
            print(f"[-] Не удалось подключиться к {target_addr}:{target_port}: {e}")
            reply = b'\x05\x05\x00\x01\x00\x00\x00\x00\x00\x00'  # Host unreachable
            client_socket.send(reply)
            client_socket.close()
            return

        # ── Шаг 5: Ответ об успешном CONNECT ──────────────────────────────────
        reply = b'\x05\x00\x00\x01'
        reply += socket.inet_aton('0.0.0.0')
        reply += struct.pack('!H', 0)
        client_socket.send(reply)

        # ── Шаг 6: Туннелируем трафик ────────────────────────────────────────
        t1 = threading.Thread(target=forward_data, args=(client_socket, remote_socket), daemon=True)
        t2 = threading.Thread(target=forward_data, args=(remote_socket, client_socket), daemon=True)
        t1.start()
        t2.start()
        t1.join(timeout=300)   # 5 мин макс — защита от зависших соединений
        t2.join(timeout=300)

    except Exception as e:
        print(f"[-] SOCKS5 ошибка от {addr}: {e}")
    finally:
        try:
            client_socket.close()
        except Exception:
            pass


def create_server(family, port, handler, name):
    """Фабрика сервера."""
    srv = socket.socket(family, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.settimeout(None)          # blocking — accept() в цикле
    srv.bind(('0.0.0.0', port))
    srv.listen(128)
    print(f"[+] {name} на порту {port}")
    return srv


def main():
    port = int(os.environ.get("PORT", 10000))
    http_port = port + 1          # например 10001

    print("=" * 50)
    print("  SOCKS5 Proxy Server")
    print("=" * 50)
    print(f"  SOCKS5 порт : {port}")
    print(f"  HTTP порт   : {http_port}")
    print("=" * 50)

    # Запускаем оба сервера в threads
    t_http = threading.Thread(
        target=start_server,
        args=(http_port, 'HTTP Health Check'),
        daemon=True
    )
    t_http.start()
    time.sleep(0.2)

    # SOCKS5 — главный поток
    start_server(port, 'SOCKS5 Proxy')


def start_server(port, label):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(('0.0.0.0', port))
    srv.listen(128)
    print(f"[+] {label} на порту {port}")

    while True:
        try:
            client, addr = srv.accept()
            print(f"[+] Подключение от {addr[0]}:{addr[1]}")
            if label.startswith('HTTP'):
                t = threading.Thread(target=handle_http_client, args=(client, addr), daemon=True)
            else:
                t = threading.Thread(target=handle_socks5_client, args=(client, addr), daemon=True)
            t.start()
        except Exception as e:
            print(f"[-] Ошибка ({label}): {e}")
            time.sleep(1)


if __name__ == "__main__":
    main()
