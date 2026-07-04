import socket
import struct
import threading
import select
import os
import sys
import signal
import json
import time
from datetime import datetime

# Глобальная переменная для времени запуска
start_time = time.time()

def handle_http_request(client_socket):
    """Обработка HTTP запросов для health check"""
    try:
        # Получаем запрос
        request = client_socket.recv(1024).decode('utf-8', errors='ignore')
        
        # Проверяем путь
        if 'GET /' in request or 'HEAD /' in request:
            # Формируем JSON ответ
            uptime_seconds = int(time.time() - start_time)
            uptime_str = str(datetime.timedelta(seconds=uptime_seconds))
            
            response_data = {
                "status": "ok",
                "service": "SOCKS5 Proxy",
                "uptime_seconds": uptime_seconds,
                "uptime_human": uptime_str,
                "timestamp": datetime.now().isoformat(),
                "version": "1.0",
                "port": 8443
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
        print(f"[-] HTTP ошибка: {e}")
    finally:
        try:
            client_socket.close()
        except:
            pass

def handle_client(client_socket):
    try:
        # Проверяем первый байт для определения протокола
        # SOCKS5 начинается с 0x05, HTTP начинается с 'G', 'P', 'H' и т.д.
        first_byte = client_socket.recv(1)
        if not first_byte:
            client_socket.close()
            return
        
        # Если это HTTP запрос (начинается с буквы)
        if first_byte in [b'G', b'P', b'H', b'C', b'O']:
            # Получаем остаток запроса
            remaining = client_socket.recv(1024)
            full_request = first_byte + remaining
            client_socket = client_socket  # Используем тот же сокет
            # Создаем новый сокет для HTTP обработки
            # Простой способ: пересоздаем объект
            http_sock = client_socket
            # Добавляем запрос обратно в буфер через новый сокет
            # Используем обертку для чтения полного запроса
            handle_http_request(client_socket)
            return
        
        # Иначе это SOCKS5
        data = first_byte + client_socket.recv(261)  # Получаем остаток приветствия
        
        # Проверяем SOCKS5 приветствие
        if len(data) < 2 or data[0] != 0x05:
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
            addr = socket.inet_ntoa(client_socket.recv(4))
            port = struct.unpack('!H', client_socket.recv(2))[0]
        elif atyp == 0x03:  # Доменное имя
            addr_len = client_socket.recv(1)[0]
            addr = client_socket.recv(addr_len).decode()
            port = struct.unpack('!H', client_socket.recv(2))[0]
        else:
            client_socket.close()
            return
        
        print(f"[+] Подключение к {addr}:{port}")
        
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
            except Exception as e:
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
        print(f"[-] Ошибка: {e}")
    finally:
        try:
            client_socket.close()
        except:
            pass

def start_server(host='0.0.0.0', port=8443):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.settimeout(60)
    server.bind((host, port))
    server.listen(100)
    
    print(f"[+] SOCKS5 сервер запущен на {host}:{port}")
    print(f"[+] Health check: http://{host}:{port}/")
    print("[+] Ожидание подключений...")
    
    # Обработка сигналов для graceful shutdown
    def signal_handler(sig, frame):
        print("\n[!] Получен сигнал завершения. Останавливаем сервер...")
        server.close()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    while True:
        try:
            client, addr = server.accept()
            print(f"[+] Новое подключение от {addr}")
            thread = threading.Thread(target=handle_client, args=(client,))
            thread.daemon = True
            thread.start()
        except socket.timeout:
            continue
        except Exception as e:
            print(f"[-] Ошибка принятия соединения: {e}")
            continue

if __name__ == "__main__":
    start_server()
