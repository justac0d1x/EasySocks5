const Socks5 = require('socks5');

const port = process.env.PORT || 1080;
const username = process.env.SOCKS5_USERNAME;
const password = process.env.SOCKS5_PASSWORD;

// Создаем SOCKS5 сервер
const server = Socks5.createServer({
    auth: (info, callback) => {
        // Если аутентификация не задана - пускаем всех
        if (!username || !password) {
            return callback(true);
        }
        // Иначе проверяем логин и пароль
        callback(info.username === username && info.password === password);
    }
});

server.listen(port, '0.0.0.0', () => {
    console.log(`SOCKS5 proxy running on port ${port}`);
    console.log(`Authentication: ${username && password ? 'Enabled' : 'Disabled'}`);
});

// Обработка ошибок
server.on('error', (err) => {
    console.error('Proxy error:', err);
});
