const shadowsocks = require('shadowsocks-node');

// ========== НАСТРОЙКИ ==========
const PORT = process.env.PORT || 10000;
const PASSWORD = process.env.PASSWORD || 'my-secret-password-123';
const METHOD = 'aes-256-gcm';

// ========== СОЗДАЁМ СЕРВЕР ==========
const config = {
  server: '0.0.0.0',
  port: PORT,
  password: PASSWORD,
  method: METHOD,
  timeout: 600,
  fastOpen: true
};

const server = shadowsocks.createServer(config);

server.on('error', (err) => {
  console.error('Ошибка:', err.message);
});

server.listen(() => {
  console.log(`✅ Shadowsocks запущен на порту ${PORT}`);
  console.log(`🔐 Метод: ${METHOD}`);
  console.log(`🔑 Пароль: ${PASSWORD}`);
});
