const socks = require('socksv5');
const http = require('http');
const net = require('net');

// ========== НАСТРОЙКИ ==========
const PORT = process.env.PORT || 8080;  // Единый порт для всего
const HOST = '0.0.0.0';

// ========== СОСТОЯНИЕ ==========
const stats = {
  startTime: Date.now(),
  connections: 0,
  totalConnections: 0,
  errors: 0
};

// ========== СОЗДАЁМ TCP СЕРВЕР ==========
const server = net.createServer((socket) => {
  // Читаем первый байт, чтобы определить протокол
  socket.once('data', (data) => {
    const firstByte = data[0];
    
    // SOCKS5 начинается с 0x05
    if (firstByte === 0x05) {
      // Передаём управление SOCKS5 обработчику
      handleSocks(socket, data);
    } else {
      // Иначе считаем это HTTP-запросом
      handleHttp(socket, data);
    }
  });
});

// ========== ОБРАБОТЧИК SOCKS5 ==========
function handleSocks(socket, firstData) {
  // Создаём SOCKS5 сервер для этого сокета
  const socksServer = socks.createServer((info, accept, deny) => {
    stats.connections++;
    stats.totalConnections++;
    
    console.log(`[SOCKS5] ${info.srcAddr}:${info.srcPort} -> ${info.dstAddr}:${info.dstPort}`);
    
    accept((conn) => {
      conn.on('close', () => stats.connections--);
      conn.on('error', () => stats.errors++);
    });
  });
  
  socksServer.useAuth(socks.auth.None());
  
  // Передаём первый прочитанный байт
  const fakeSocket = new net.Socket();
  fakeSocket._handle = socket._handle;
  fakeSocket.ondata = (data) => {
    socket.emit('data', data);
  };
  
  // Запускаем SOCKS5 обработку
  socksServer.emit('connection', socket);
  
  // Отправляем первый байт обратно
  socket.emit('data', firstData);
}

// ========== ОБРАБОТЧИК HTTP (JSON СТАТУС) ==========
function handleHttp(socket, firstData) {
  // Собираем остальные данные
  let data = firstData;
  socket.on('data', (chunk) => {
    data = Buffer.concat([data, chunk]);
    // Если есть конец заголовков - обрабатываем
    if (data.includes('\r\n\r\n')) {
      sendStatus(socket);
    }
  });
  
  // Если данных достаточно для заголовка
  if (data.includes('\r\n\r\n')) {
    sendStatus(socket);
  }
}

function sendStatus(socket) {
  const uptime = Math.floor((Date.now() - stats.startTime) / 1000);
  const hours = Math.floor(uptime / 3600);
  const minutes = Math.floor((uptime % 3600) / 60);
  const seconds = uptime % 60;

  const status = {
    status: 'running',
    uptime: `${hours}h ${minutes}m ${seconds}s`,
    active_connections: stats.connections,
    total_connections: stats.totalConnections,
    errors: stats.errors,
    socks_port: PORT,
    timestamp: new Date().toISOString()
  };

  const response = `HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n${JSON.stringify(status, null, 2)}`;
  socket.write(response);
  socket.end();
}

// ========== ЗАПУСК ==========
server.listen(PORT, HOST, () => {
  console.log(`✅ Сервер запущен на порту ${PORT}`);
  console.log(`📊 Статус: http://localhost:${PORT}`);
  console.log(`🔌 SOCKS5 также на порту ${PORT}`);
});

// ========== ОСТАНОВКА ==========
process.on('SIGINT', () => {
  console.log('\nОстановка...');
  server.close(() => process.exit(0));
});
