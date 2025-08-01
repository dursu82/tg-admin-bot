import asyncio
import asyncssh
import aiohttp
from dataclasses import dataclass, field
from typing import List


@dataclass
class SSHResult:
    output: str  # Вывод команды
    error: str   # Сообщение об ошибке, если есть

@dataclass
class Proxy:
    ip: str = ""
    port: str = ""
    status: str = ""
    port2: str = ""

@dataclass
class SquidResult:
    squid: List[Proxy] = field(default_factory=list)
    error: str = ""


async def ssh_exec(ip, command, username: str = "user", key_file: str = "/home/tg-bot/.ssh/key") -> SSHResult:
    try:
        async with asyncssh.connect(
            host=ip,
            username=username,
            client_keys=[key_file],
            known_hosts=None  # отключает проверку host key
        ) as conn:
            result = await conn.run(command, check=False)
            return SSHResult(output=result.stdout, error=result.stderr)
    except Exception as e:
        return SSHResult(output="", error=f"[ERROR] SSH Connection failed: {e}")


async def squid_add_port(ip: str, args: str) -> SquidResult:
    data = SquidResult()
    # 1. Выполнение squid-add-proxy.sh
    command = f"sudo /etc/squid/squid-add-proxy.sh {args}"
    result = await ssh_exec(ip, command)

    if result.output:
        # 2. Обработка вывода
        data.squid = [Proxy(*line.strip().split(":")) for line in result.output.splitlines() if line.strip()]
        # 3. Mikrotik
        async with aiohttp.ClientSession() as session:
            tasks = [session.get(f"http://{ip}:19999", timeout=aiohttp.ClientTimeout(total=0.1))
                    for ip in set([line.split(":")[0] for line in args.split()])]
            await asyncio.gather(*[task.__aenter__() for task in tasks], return_exceptions=True)
    else:
        data.error = result.error

    return data
