from config import config
from databases import Database


class DatabaseService:
    def __init__(self):
        self.database = Database(f"postgresql+asyncpg://{config.DB_URL}")

    async def connect(self):
        await self.database.connect()

    async def disconnect(self):
        await self.database.disconnect()

    async def get_user_commands(self, user_id: int) -> list[tuple[str, str]]:
        query = """
            SELECT c.name, c.description
            FROM tg_users u
            LEFT JOIN tg_role_commands rc ON u.role_name = rc.role_name
            LEFT JOIN tg_commands c ON rc.command_name = c.name
            WHERE u.id = :user_id;
        """
        rows = await self.database.fetch_all(query, {"user_id": user_id})
        return [(row["name"], row["description"]) for row in rows]

    async def pbx_allow_ip(self, ip: str, user_id: int) -> bool:
        query = "INSERT INTO pbx_allowlist (src, id, is_bot) VALUES (:ip, :user_id, :is_bot)"
        try:
            await self.database.execute(query, {"ip": ip, "user_id": user_id, "is_bot": True})
            return True
        except Exception as e:
            # return e  # Возвращаем объект ошибки
            return False

    async def pbx_ip_allowed(self, ip: str) -> bool:
        # CAST - это стандартная SQL-функция для приведения типа данных
        # src типа inet
        query = "SELECT 1 FROM pbx_allowlist WHERE src = CAST(:ip AS inet) LIMIT 1"
        try:
            row = await self.database.fetch_one(query, {"ip": ip})
            return row is not None
        except Exception as e:
            print(f"Ошибка при проверке IP: {e}")
            return False


db_service = DatabaseService()
