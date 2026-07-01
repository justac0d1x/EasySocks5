const socks = require('socksv5');
const http = require('http');

// ========== НАСТРОЙКИ ==========
const SOCKS_PORT = 1080;
const WEB_PORT = 8080;
const HOST = '0.0.0.0';

// ========== СОСТОЯНИЕ ==========
const stats = {
  startTime: Date.now(),
  connections: 0,
  totalConnections: 0,
  errors: 0
};

// ========== SOCKS5 ПРОКСИ ==========
const socksServer = socks.createServer((info, accept, deny) => {
  stats.connections++;
  stats.totalConnections++;
  
  console.log(`[${new Date().toISOString()}] ${info.srcAddr}:${info.srcPort} -> ${info.dstAddr}:${info.dstPort}`);

  accept((conn) => {
    conn.on('close', () => stats.connections--);
    conn.on('error', () => stats.errors++);
  });
});

socksServer.useAuth(socks.auth.None());
socksServer.listen(SOCKS_PORT, HOST, () => {
  console.log(`SOCKS5 на порту ${SOCKS_PORT}`);
});

// ========== ВЕБ СЕРВЕР (ТОЛЬКО JSON) ==========
const webServer = http.createServer((req, res) => {
  const uptime = Math.floor((Date.now() - stats.startTime) / 1000);
  const hours = Math.floor(uptime / 3600);
  const minutes = Math.floor((uptime % 3600) / 60);
  const seconds = uptime % 60;

  const data = {
    status: 'running',
    uptime: `${hours}h ${minutes}m ${seconds}s`,
    active_connections: stats.connections,
    total_connections: stats.totalConnections,
    errors: stats.errors,
    socks_port: SOCKS_PORT,
    timestamp: new Date().toISOString()
  };

  res.writeHead(200, { 
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*' 
  });
  res.end(JSON.stringify(data, null, 2));
});

webServer.listen(WEB_PORT, HOST, () => {
  console.log(`Статус: http://${HOST}:${WEB_PORT}`);
});

// ========== ОСТАНОВКА ==========
process.on('SIGINT', () => {
  console.log('\nОстановка...');
  socksServer.close(() => webServer.close(() => process.exit(0)));
});
