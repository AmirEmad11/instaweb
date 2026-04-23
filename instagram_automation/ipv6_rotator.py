"""
IPv6 Rotator
============
Picks a random IPv6 address from the configured /64 prefix and adds it to the
network interface so Linux can use it as the source address for outbound
connections from Chromium.

Prefix: 2a02:4780:28:421::/64
"""

import os
import random
import logging
import subprocess
import ipaddress

logger = logging.getLogger(__name__)

IPV6_PREFIX = os.environ.get("IPV6_PREFIX", "2a02:4780:28:421")
IPV6_INTERFACE = os.environ.get("IPV6_INTERFACE", "eth0")


def _random_hextet() -> str:
    return f"{random.randint(0x1000, 0xffff):x}"


def get_random_ipv6(prefix: str = IPV6_PREFIX) -> str:
    """
    Generate a random IPv6 address inside the configured /64 prefix.
    Example output: 2a02:4780:28:421:a1b2:c3d4:e5f6:7890
    """
    suffix = ":".join(_random_hextet() for _ in range(4))
    addr = f"{prefix}:{suffix}"
    # Validate
    ip = ipaddress.IPv6Address(addr)
    return str(ip)


def bind_ipv6_to_interface(ipv6: str, interface: str = IPV6_INTERFACE) -> bool:
    """
    Adds the given IPv6 to the interface so the kernel can use it as a source
    address for outbound connections. Requires root (or CAP_NET_ADMIN).
    Returns True on success, False otherwise (non-fatal).
    """
    try:
        cmd = ["ip", "-6", "addr", "add", f"{ipv6}/64", "dev", interface]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"[IPv6] Bound {ipv6} to {interface}", flush=True)
            logger.info(f"[IPv6] Bound {ipv6} to {interface}")
            return True
        # File exists = already bound, that's fine
        if "File exists" in result.stderr:
            return True
        # If we don't have permission, try sudo silently
        if "Operation not permitted" in result.stderr:
            sudo_cmd = ["sudo", "-n"] + cmd
            r2 = subprocess.run(sudo_cmd, capture_output=True, text=True)
            if r2.returncode == 0 or "File exists" in r2.stderr:
                print(f"[IPv6] Bound {ipv6} to {interface} (via sudo)", flush=True)
                return True
            logger.warning(f"[IPv6] sudo bind failed: {r2.stderr.strip()}")
        else:
            logger.warning(f"[IPv6] bind failed: {result.stderr.strip()}")
    except FileNotFoundError:
        logger.warning("[IPv6] 'ip' command not found - skipping bind")
    except Exception as e:
        logger.warning(f"[IPv6] bind error: {e}")
    return False


def get_and_bind_random_ipv6() -> str:
    """
    Convenience function: generate a random IPv6 from the prefix, bind it
    to the interface, and return it.
    """
    ipv6 = get_random_ipv6()
    print(f"[IPv6] Using IP: {ipv6}", flush=True)
    logger.info(f"[IPv6] Using IP: {ipv6}")
    bind_ipv6_to_interface(ipv6)
    return ipv6
