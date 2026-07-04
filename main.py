import socket
import struct
import threading
import select
import os
import sys
import signal

def handle_client(client_socket):
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
        
        # 4. Проксируем трафик (улучшенная версия)
        def forward_data(source, dest):
            try:
                while True:
                    # Используем select для неблокирующей передачи
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
