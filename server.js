const { SocksServer } = require('socks5-server');

const port = process.env.PORT || 1080;

// Настройка аутентификации
const username = process.env.SOCKS5_USERNAME;
const password = process.env.SOCKS5_PASSWORD;

const server = new SocksServer({
    port: port,
    auth: (username, password, callback) => {
        // Проверяем логин и пароль из переменных окружения
        if (username === process.env.SOCKS5_USERNAME && 
            password === process.env.SOCKS5_PASSWORD) {
            callback(true);
        } else {
            callback(false);
        }
    }
});

server.listen(() => {
    console.log(`SOCKS5 proxy running on port ${port}`);
    if (username && password) {
        console.log('Authentication enabled');
    } else {
        console.log('Authentication disabled');
    }
});
