import mysql.connector


# Конфигурация базы данных
DB_CONFIG = {
    "host": "192.168.10.101",
    "user": "tg_bot",
    "password": "y9rLNXC1iagAGjVYVya6",
    "database": "log"
}

# Функция для подключения к БД
def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG)
