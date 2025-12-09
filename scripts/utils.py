import ipaddress
import re
from typing import Literal

from rich import print

type IpVersion = Literal[4, 6]


def get_ip_version(ip: str) -> IpVersion | None:
    try:
        ipaddress.IPv4Address(ip)
        return 4
    except ValueError:
        pass
    try:
        ipaddress.IPv6Address(ip)
        return 6
    except ValueError:
        return None


IPV4SEG = "(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])"
IPV4ADDR = f"({IPV4SEG}\\.){{3,3}}{IPV4SEG}"
IPV6SEG = "[0-9a-fA-F]{1,4}"
IPV6ADDR = (
    f"({IPV6SEG}:){{7,7}}{IPV6SEG}|"  # 1:2:3:4:5:6:7:8
    f"({IPV6SEG}:){{1,7}}:|"  # 1:: 1:2:3:4:5:6:7::
    f"({IPV6SEG}:){{1,6}}:{IPV6SEG}|"  # 1::8   1:2:3:4:5:6::8   1:2:3:4:5:6::8
    f"({IPV6SEG}:){{1,5}}(:{IPV6SEG}){{1,2}}|"  # 1::7:8             1:2:3:4:5::7:8   1:2:3:4:5::8
    f"({IPV6SEG}:){{1,4}}(:{IPV6SEG}){{1,3}}|"  # 1::6:7:8           1:2:3:4::6:7:8   1:2:3:4::8
    f"({IPV6SEG}:){{1,3}}(:{IPV6SEG}){{1,4}}|"  # 1::5:6:7:8         1:2:3::5:6:7:8   1:2:3::8
    f"({IPV6SEG}:){{1,2}}(:{IPV6SEG}){{1,5}}|"  # 1::4:5:6:7:8       1:2::4:5:6:7:8   1:2::8
    f"{IPV6SEG}:((:{IPV6SEG}){{1,6}})|"  # 1::3:4:5:6:7:8     1::3:4:5:6:7:8   1::8
    f":((:{IPV6SEG}){{1,7}}|:)|"  # ::2:3:4:5:6:7:8    ::2:3:4:5:6:7:8  ::8       ::
    f"fe80:(:{IPV6SEG}){{0,4}}%[0-9a-zA-Z]{{1,}}|"  # fe80::7:8%eth0     fe80::7:8%1  (link-local IPv6 addresses with zone index)
    f"::(ffff(:0{{1,4}}){{0,1}}:){{0,1}}{IPV4ADDR}|"  # ::255.255.255.255  ::ffff:255.255.255.255  ::ffff:0:255.255.255.255 (IPv4-mapped IPv6 addresses and IPv4-translated addresses)
    f"({IPV6SEG}:){{1,4}}:{IPV4ADDR}"  # 2001:db8:3:4::192.0.2.33  64:ff9b::192.0.2.33 (IPv4-Embedded IPv6 Address)
)


def get_ip_version_re(ip: str) -> IpVersion | None:
    if re.match(rf"^{IPV4ADDR}$", ip):
        return 4
    if re.match(rf"^{IPV6ADDR}$", ip):
        return 6
    return None


# test ipv4 and v6 using the ip_type function
def test_ip_version_parsing(ip, expected: Literal[4, 6, None]):
    actual = get_ip_version(ip)
    color = "green" if actual == expected else "red"
    print(f"'{ip}' expected: {expected} got [{color}]{get_ip_version(ip)}[/{color}]")


ipv6_addrs = {
    "1:2:3:4:5:6:7:8",
    "::1",
    "1:2:3:4:5:6:7::",
    "1::8",
    "1:2:3:4:5:6::8",
    "1::7:8",
    "1:2:3:4:5::7:8",
    "1:2:3:4:5::8",
    "1::6:7:8",
    "1:2:3:4::6:7:8",
    "1:2:3:4::8",
    "1::5:6:7:8",
    "1:2:3::5:6:7:8",
    "1:2:3::8",
    "1::4:5:6:7:8",
    "1::3:4:5:6:7:8",
    "::2:3:4:5:6:7:8",
    "::8",
    "::",
}

ip_addresses: dict[str, IpVersion | None] = {
    "invalid": None,
    "127.0.0.1": 4,
    "localhost": 4,
    "127.0.0.2:8080": None,
    **{addr: 6 for addr in ipv6_addrs},
}

for ip, v in ip_addresses.items():
    test_ip_version_parsing(ip, v)
