from scripts.proxy import ssh_exec, SSHResult


async def wg_get_users() -> SSHResult:
    return await ssh_exec(
        ip="192.168.10.41",
        command="sudo /etc/wireguard/wgfwctl.sh --no-help list"
    )


async def wg_get_user_ips(name: str) -> SSHResult:
    return await ssh_exec(
        ip="192.168.10.41",
        command=f"sudo /etc/wireguard/wgfwctl.sh --no-help set -l --name='{name}'"
    )


async def wg_get_user_config(name: str, update: bool = False) -> SSHResult:
    return await ssh_exec(
        ip="192.168.10.41",
        command=f"sudo /etc/wireguard/wgfwctl.sh --no-help config --name='{name}'" + (" -u" if update else "")
    )


async def wg_set_add(name: str, ip: str) -> SSHResult:
    return await ssh_exec(
        ip="192.168.10.41",
        command=f"sudo /etc/wireguard/wgfwctl.sh --no-help set --name='{name}' --ip={ip} -a"
    )


async def wg_set_del(name: str, ip: str) -> SSHResult:
    return await ssh_exec(
        ip="192.168.10.41",
        command=f"sudo /etc/wireguard/wgfwctl.sh --no-help set --name='{name}' --ip={ip} -r"
    )


async def wg_add_user(name: str, chainset: str) -> SSHResult:
    return await ssh_exec(
        ip="192.168.10.41",
        command=f"sudo /etc/wireguard/wgfwctl.sh --no-help add --name='{name}' --chainset='{chainset}'"
)


async def wg_del_user(name: str) -> SSHResult:
    return await ssh_exec(
        ip="192.168.10.41",
        command=f"sudo /etc/wireguard/wgfwctl.sh --no-help del --name='{name}'"
    )
