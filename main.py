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

# Глобальная переменная для времени запуска
start_time = time.time()

def handle_http_client(client_socket, addr):
    """Обработка HTTP запросов для health check"""
    try:
        # Получаем запрос
        request = client_socket.recv(1024).decode('utf-8', errors='ignore')
        
        # Проверяем путь
        if 'GET /' in request or 'HEAD /' in request:
            # Формируем JSON ответ
            uptime_seconds = int(time.time() - start_time)
            uptime_str = str(timedelta(seconds=uptime_seconds))
            
            response_data = {
                "status": "ok",
                "service": "SOCKS5 Proxy",
                "uptime_seconds": uptime_seconds,
                "uptime_human": uptime_str,
                "timestamp": datetime.now().isoformat(),
                "version": "1.0",
                "socks5_port": 1080,
                "http_port": 8443
            }
            
            response_json = json.dumps(response_data, indent=2)
            
            response = (
                "HTTP/1.1 200 OK\r\n"
                "Content-Type: application/json\r\n"
                f"Content-Length: {len(response_json)}\r\n"
                "Connection: close\r\n"
                "\r\n"
                f"{response_json}"
            )
            
            client_socket.send(response.encode())
        else:
            # 404 для других запросов
            response = (
                "HTTP/1.1 404 Not Found\r\n"
                "Content-Type: text/plain\r\n"
                "Content-Length: 9\r\n"
                "Connection: close\r\n"
                "\r\n"
                "Not Found"
            )
            client_socket.send(response.encode())
            
    except Exception as e:
        print(f"[-] HTTP ошибка от {addr}: {e}")
    finally:
        try:
            client_socket.close()
        except:
            pass

def handle_socks5_client(client_socket, addr):
    """Обработка SOCKS5 клиентов"""
    try:
        # 1. Приветствие SOCKS5
        data = client_socket.recv(262)
        if not data or data[0] != 0x05:
            client_socket.close()
            return
        
        # Отправляем ответ на приветствие (без аутентификации)
        client_socket.send(b'\x05\x00')
        
        # 2. Получаем запрос
        request = client_socket.recv(4)
        if len(request) < 4:
            client_socket.close()
            return
        
        ver, cmd, rsv, atyp = struct.unpack('!BBBB', request)
        
        # Поддерживаем только CONNECT команду
        if cmd != 0x01:
            client_socket.close()
            return
        
        # Парсим адрес назначения
        if atyp == 0x01:  # IPv4
            addr_bytes = client_socket.recv(4)
            if len(addr_bytes) < 4:
                client_socket.close()
                return
            addr = socket.inet_ntoa(addr_bytes)
            port_bytes = client_socket.recv(2)
            if len(port_bytes) < 2:
                client_socket.close()
                return
            port = struct.unpack('!H', port_bytes)[0]
        elif atyp == 0x03:  # Доменное имя
            addr_len_byte = client_socket.recv(1)
            if not addr_len_byte:
                client_socket.close()
                return
            addr_len = addr_len_byte[0]
            addr_bytes = client_socket.recv(addr_len)
            if len(addr_bytes) < addr_len:
                client_socket.close()
                return
            addr = addr_bytes.decode()
            port_bytes = client_socket.recv(2)
            if len(port_bytes) < 2:
                client_socket.close()
                return
            port = struct.unpack('!H', port_bytes)[0]
        else:
            client_socket.close()
            return
        
        print(f"[+] SOCKS5: {addr[0]}:{port}")
        
        # 3. Устанавливаем соединение с целевым сервером
        try:
            remote_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            remote_socket.settimeout(10)
            remote_socket.connect((addr, port))
        except Exception as e:
            print(f"[-] Ошибка подключения к {addr}:{port}: {e}")
            client_socket.close()
            return
        
        # Отправляем успешный ответ
        reply = b'\x05\x00\x00\x01'
        reply += socket.inet_aton('0.0.0.0')
        reply += struct.pack('!H', 0)
        client_socket.send(reply)
        
        # 4. Проксируем трафик
        def forward_data(source, dest):
            try:
                while True:
                    rlist, _, _ = select.select([source], [], [], 5)
                    if not rlist:
                        continue
                    data = source.recv(4096)
                    if not data:
                        break
                    dest.send(data)
            except:
                pass
            finally:
                try:
                    source.close()
                except:
                    pass
                try:
                    dest.close()
                except:
                    pass
        
        # Создаем потоки для двусторонней передачи
        t1 = threading.Thread(target=forward_data, args=(client_socket, remote_socket))
        t2 = threading.Thread(target=forward_data, args=(remote_socket, client_socket))
        t1.daemon = True
        t2.daemon = True
        t1.start()
        t2.start()
        
        # Ждем завершения
        t1.join()
        t2.join()
        
    except Exception as e:
        print(f"[-] SOCKS5 ошибка от {addr}: {e}")
    finally:
        try:
            client_socket.close()
        except:
            pass

def start_http_server(host='0.0.0.0', port=8443):
    """HTTP сервер для health check"""
    http_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    http_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    http_server.bind((host, port))
    http_server.listen(10)
    
    print(f"[+] HTTP Health Check запущен на {host}:{port}")
    
    while True:
        try:
            client, addr = http_server.accept()
            print(f"[+] HTTP запрос от {addr}")
            thread = threading.Thread(target=handle_http_client, args=(client, addr))
            thread.daemon = True
            thread.start()
        except Exception as e:
            print(f"[-] HTTP ошибка: {e}")

def start_socks5_server(host='0.0.0.0', port=1080):
    """SOCKS5 сервер"""
    socks5_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    socks5_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    socks5_server.bind((host, port))
    socks5_server.listen(100)
    
    print(f"[+] SOCKS5 сервер запущен на {host}:{port}")
    
    while True:
        try:
            client, addr = socks5_server.accept()
            print(f"[+] SOCKS5 подключение от {addr}")
            thread = threading.Thread(target=handle_socks5_client, args=(client, addr))
            thread.daemon = True
            thread.start()
        except Exception as e:
            print(f"[-] SOCKS5 ошибка: {e}")

def main():
    # Получаем порты из переменных окружения или используем значения по умолчанию
    http_port = int(os.environ.get('HTTP_PORT', 8443))
    socks5_port = int(os.environ.get('SOCKS5_PORT', 1080))
    
    print("=" * 50)
    print("SOCKS5 Proxy Server with HTTP Health Check")
    print("=" * 50)
    print(f"[+] HTTP Health Check порт: {http_port}")
    print(f"[+] SOCKS5 прокси порт: {socks5_port}")
    print(f"[+] Health Check URL: http://0.0.0.0:{http_port}/")
    print("=" * 50)
    
    # Запускаем HTTP сервер в отдельном потоке
    http_thread = threading.Thread(target=start_http_server, args=('0.0.0.0', http_port))
    http_thread.daemon = True
    http_thread.start()
    
    # Запускаем SOCKS5 сервер в основном потоке
    start_socks5_server('0.0.0.0', socks5_port)

if __name__ == "__main__":
    main()
