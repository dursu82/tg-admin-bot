from ipaddress import ip_address, IPv4Address


def is_valid_ipv4(ip: str) -> bool:
    try:
        return isinstance(ip_address(ip), IPv4Address)
    except ValueError:
        return False

# Zero Width + IP
def zwip(ip: str) -> str:
    return ip.replace('.', '.\u200B')
