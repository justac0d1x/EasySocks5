const shadowsocks = require('shadowsocks');

// ========== НАСТРОЙКИ ==========
const PORT = process.env.PORT || 10000;
const PASSWORD = process.env.PASSWORD || 'my-secret-password-123';
const METHOD = 'aes-256-gcm';  // Самый быстрый и безопасный

// ========== СОЗДАЁМ СЕРВЕР ==========
const config = {
  server: '0.0.0.0',      // Слушаем все интерфейсы
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
  console.log(`🌐 Адрес: https://testsocks5.onrender.com`);
});
