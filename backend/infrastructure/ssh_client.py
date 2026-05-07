"""
Infrastructure Layer - SSH Operations
Pure functions, no FastAPI dependency — testable without API or DB
"""

import json
import socket
from dataclasses import dataclass, asdict
from typing import Optional, Any


@dataclass
class ServerInfo:
    hostname: str
    ip: str
    os_type: str          # "linux" or "windows"
    os_version: Optional[str] = None
    cpu_model: Optional[str] = None
    cpu_count: Optional[int] = None
    memory_total: Optional[int] = None   # MB
    interfaces: Optional[list] = None    # [{name, ip, mac, pci_addr, pci_desc, speed}]
    error: Optional[str] = None


def check_online(ip: str, port: int = 22, timeout: int = 3) -> bool:
    """Check if a server is reachable via TCP (SSH port)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        return sock.connect_ex((ip, port)) == 0
    except socket.error:
        return False
    finally:
        sock.close()


def ping_icmp(ip: str, timeout: int = 3) -> bool:
    """Check if a server responds to ICMP ping."""
    import subprocess
    try:
        result = subprocess.run(
            ["ping", "-n", "1", "-w", str(timeout * 1000), ip],
            capture_output=True, timeout=timeout + 1
        )
        return result.returncode == 0
    except Exception:
        return False


def get_server_status(ip: str, port: int = 22) -> dict:
    """Get server status: online + SSH port open."""
    online = check_online(ip, port=port)
    return {"ip": ip, "online": online, "ssh_open": online}


def _exec(ssh_client, cmd: str, timeout: int = 10) -> str:
    """Execute a command via paramiko SSHClient, return stdout."""
    stdin, stdout, stderr = ssh_client.exec_command(cmd, timeout=timeout)
    return stdout.read().decode().strip()


def _is_physical_interface(iface: str) -> bool:
    return not (
        iface in ("lo",)
        or iface.startswith(("br-", "docker", "veth", "virbr", "tun", "tap"))
    )


def _pci_of_interface(ssh_client, iface: str) -> dict:
    """Get PCI address, description and speed for a network interface."""
    # Skip loopback and virtual interfaces
    if iface in ('lo',) or iface.startswith(('br-', 'docker', 'veth', 'virbr', 'tun', 'tap')):
        return {"pci_addr": None, "pci_desc": None, "speed": None}

    speed = ""
    speed_raw = _exec(ssh_client, f"cat /sys/class/net/{iface}/speed 2>/dev/null || echo ''").strip()
    if speed_raw and speed_raw.isdigit():
        speed = f"{speed_raw} Mb/s"

    # Get interface driver from sysfs
    driver_link = _exec(ssh_client, f"readlink /sys/class/net/{iface}/device/driver 2>/dev/null").strip()
    iface_driver = driver_link.split('/')[-1] if driver_link else ''

    # Build PCI addr -> (driver, description) map from lspci -nnk
    lspci_out = _exec(ssh_client, "lspci -nnk 2>/dev/null")
    import re
    pci_map = {}  # pci_addr -> {driver, desc}
    current_pci = None
    for line in lspci_out.split('\n'):
        line_s = line.lstrip()
        m = re.match(r'^([0-9a-f.:]+)\s+(.*)', line_s)
        if m:
            current_pci = m.group(1)
            rest = m.group(2)
            # Extract description after first [CATEGORY]:
            desc_m = re.match(r'.*?\]\s*:\s*(.*)', rest)
            desc = desc_m.group(1) if desc_m else rest
            # Remove subsystem [VENDOR:PRODUCT] and (rev ...)
            desc = re.sub(r'\s*\[[0-9a-f]{4}:[0-9a-f]{4}\].*', '', desc)
            desc = re.sub(r'\s*\(rev.*\)$', '', desc).strip()
            pci_map[current_pci] = {'desc': desc, 'driver': None}
        elif current_pci and 'Kernel driver in use:' in line:
            pci_map[current_pci]['driver'] = line.split('in use:')[-1].strip()
            current_pci = None

    # Try 1: driver name matches
    pci_addr = None
    pci_desc = None
    for addr, info in pci_map.items():
        if info['driver'] == iface_driver:
            pci_addr = addr
            pci_desc = info['desc']
            break

    # Try 2: fallback for ARM/RPi where drivers don't match lspci directly
    if not pci_addr:
        if iface_driver == 'macb' or iface == 'eth0':
            # Prefer Ethernet/Network first
            for addr, info in pci_map.items():
                kw = info['desc'].lower()
                if 'ethernet' in kw or 'network' in kw:
                    pci_addr = addr
                    pci_desc = info['desc']
                    break
            # Fallback: match bridge but skip host/PCI bridges (category 0604)
            if not pci_addr:
                for addr, info in pci_map.items():
                    kw = info['desc'].lower()
                    if 'bridge' in kw and 'pci bridge' not in kw and 'pcie bridge' not in kw:
                        pci_addr = addr
                        pci_desc = info['desc']
                        break
        elif iface_driver == 'brcmfmac' or iface == 'wlan0':
            for addr, info in pci_map.items():
                if any(kw in info['desc'].lower() for kw in ('network', 'wireless', 'wlan', 'wifi', '802.11')):
                    pci_addr = addr
                    pci_desc = info['desc']
                    break

    return {"pci_addr": pci_addr, "pci_desc": pci_desc, "speed": speed or None}


def _cpu_model_linux(ssh_client) -> str:
    """Get CPU model on Linux via dmidecode (most reliable on x86 servers)."""
    # dmidecode requires root, returns the processor brand string
    model = _exec(ssh_client, "dmidecode -s processor-version 2>/dev/null || echo ''").strip()
    if model:
        return model
    # Fallback: lscpu (works on most Linux distros)
    model = _exec(ssh_client, "lscpu | grep 'Model name' | cut -d: -f2 | sed 's/^ *//' 2>/dev/null || echo ''").strip()
    if model:
        return model
    # Fallback: cpuinfo
    model = _exec(ssh_client, "cat /proc/cpuinfo | grep -m1 'model name' | cut -d: -f2 | sed 's/^ *//' 2>/dev/null || echo ''").strip()
    return model


def fetch_server_info_linux(ssh_client) -> dict:
    """Fetch server info from Linux via paramiko transport."""
    try:
        hostname = _exec(ssh_client, "hostname")
        os_version = _exec(ssh_client, "cat /etc/os-release 2>/dev/null | grep PRETTY_NAME | cut -d'\"' -f2")
        cpu_model = _cpu_model_linux(ssh_client)
        cpu_count_raw = _exec(ssh_client, "nproc 2>/dev/null || echo ''")
        cpu_count = int(cpu_count_raw) if cpu_count_raw.isdigit() else None
        mem_raw = _exec(ssh_client, "free -m 2>/dev/null | grep Mem | awk '{print $2}'")
        memory_total = int(mem_raw) if mem_raw.isdigit() else None

        # Interfaces via ip -j
        raw = _exec(ssh_client, "ip -j addr show 2>/dev/null")
        interfaces = []
        if raw:
            try:
                data = json.loads(raw)
                for i in data:
                    inet_addr = next(
                        (a["local"] for a in i.get("addr_info", []) if a.get("family") == "inet"),
                        None
                    )
                    iface_name = i.get("ifname", "")
                    pci = _pci_of_interface(ssh_client, iface_name)
                    interfaces.append({
                        "name": iface_name,
                        "ip": inet_addr,
                        "mac": i.get("address"),
                        "operstate": i.get("operstate"),
                        "prefixlen": next(
                            (a.get("prefixlen") for a in i.get("addr_info", []) if a.get("family") == "inet"),
                            None
                        ),
                        "pci_addr": pci["pci_addr"],
                        "pci_desc": pci["pci_desc"],
                        "speed": pci["speed"],
                    })
            except json.JSONDecodeError:
                pass

        return {
            "hostname": hostname,
            "os_type": "linux",
            "os_version": os_version or None,
            "cpu_model": cpu_model or None,
            "cpu_count": cpu_count,
            "memory_total": memory_total,
            "interfaces": interfaces,
        }
    except Exception as e:
        return {
            "hostname": "", "os_type": "linux", "os_version": None,
            "cpu_model": None, "cpu_count": None, "memory_total": None, "interfaces": [],
            "error": str(e)
        }


def fetch_server_info_windows(ssh_client) -> dict:
    """Fetch server info from Windows via paramiko transport (PowerShell)."""
    try:
        hostname = _exec(ssh_client, 'powershell -Command "$env:COMPUTERNAME"')
        os_version = _exec(ssh_client, 'powershell -Command "(Get-WmiObject Win32_OperatingSystem).Caption"')
        cpu_model = _exec(ssh_client, 'powershell -Command "(Get-WmiObject Win32_Processor).Name"')
        cpu_raw = _exec(ssh_client, 'powershell -Command "(Get-WmiObject Win32_Processor).NumberOfCores"')
        cpu_count = int(cpu_raw) if cpu_raw.isdigit() else None
        mem_raw = _exec(ssh_client, 'powershell -Command "[math]::Round((Get-WmiObject Win32_ComputerSystem).TotalPhysicalMemory / 1MB)"')
        memory_total = int(mem_raw) if mem_raw.isdigit() else None

        # Interfaces
        raw = _exec(ssh_client, 'powershell -Command "Get-NetIPAddress -AddressFamily IPv4 | Select-Object InterfaceAlias,IPAddress | ConvertTo-Json"')
        interfaces = []
        if raw:
            try:
                data = json.loads(raw)
                if isinstance(data, dict):
                    data = [data]
                for i in data:
                    interfaces.append({
                        "name": i.get("InterfaceAlias", ""),
                        "ip": i.get("IPAddress", ""),
                        "mac": None,
                        "pci_addr": None,
                        "pci_desc": None,
                        "speed": None,
                    })
            except json.JSONDecodeError:
                pass

        return {
            "hostname": hostname,
            "os_type": "windows",
            "os_version": os_version or None,
            "cpu_model": cpu_model or None,
            "cpu_count": cpu_count,
            "memory_total": memory_total,
            "interfaces": interfaces,
        }
    except Exception as e:
        return {
            "hostname": "", "os_type": "windows", "os_version": None,
            "cpu_model": None, "cpu_count": None, "memory_total": None, "interfaces": [],
            "error": str(e)
        }


def get_server_info_via_ssh(
    ip: str,
    username: str,
    password: Optional[str] = None,
    key_file: Optional[str] = None,
    port: int = 22,
) -> ServerInfo:
    """
    Connect via SSH and fetch server info.
    Returns ServerInfo dataclass.
    """
    import paramiko

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        client.connect(
            ip,
            port=port,
            username=username,
            password=password,
            key_filename=key_file,
            timeout=10,
            look_for_keys=False,
            allow_agent=False,
        )

        # Detect OS
        os_raw = _exec(client, "uname -s 2>/dev/null || echo Windows")
        is_windows = "windows" in os_raw.lower() or os_raw == "Windows"

        data = fetch_server_info_windows(client) if is_windows else fetch_server_info_linux(client)

        return ServerInfo(
            hostname=data.get("hostname", ""),
            ip=ip,
            os_type=data.get("os_type", "unknown"),
            os_version=data.get("os_version"),
            cpu_model=data.get("cpu_model"),
            cpu_count=data.get("cpu_count"),
            memory_total=data.get("memory_total"),
            interfaces=data.get("interfaces"),
            error=data.get("error"),
        )

    except Exception as e:
        return ServerInfo(hostname="", ip=ip, os_type="unknown", error=str(e))

    finally:
        client.close()


# ─── Switch info (proprietary CLI) ───────────────────────────────────────────

@dataclass
class SwitchInfo:
    """Switch information dataclass."""
    hostname: Optional[str] = None
    os_type: Optional[str] = None    # e.g. "H3C", "Huawei VRP", "Cisco IOS"
    os_version: Optional[str] = None
    board_type: Optional[str] = None  # e.g. "S5560-28C-PWR-EI"
    uptime: Optional[str] = None
    patch_version: Optional[str] = None
    error: Optional[str] = None


def _interact_exec(ssh_client, command: str, expect_prompt: str = ">", timeout: int = 10) -> str:
    """
    Execute a command via an interactive shell session (paramiko invoke_shell).
    Waits for the command prompt to return, then returns the output.
    Suitable for network device CLIs (Huawei VRP, H3C Comware, etc.).
    Handles login banners and password-change prompts automatically.
    """
    output = ""
    chan = ssh_client.invoke_shell(width=200, height=80)
    chan.settimeout(timeout)

    # Drain any initial output (login banner, prompts)
    import time
    time.sleep(0.5)
    try:
        while chan.recv_ready():
            output += chan.recv(65535).decode('utf-8', errors='replace')
            time.sleep(0.3)
    except Exception:
        pass

    # If password-change prompt appears, answer 'N' to skip
    if "Change now" in output or "[Y/N]" in output:
        chan.send("N\r\n")
        time.sleep(0.5)
        try:
            while chan.recv_ready():
                output += chan.recv(65535).decode('utf-8', errors='replace')
                time.sleep(0.3)
        except Exception:
            pass

    # Send the command
    chan.send(command + "\r\n")

    # Read until we see the prompt again (command finished)
    while True:
        try:
            chunk = chan.recv(65535).decode('utf-8', errors='replace')
            output += chunk
            # Look at last line to check prompt
            last_line = output.split('\n')[-1].strip()
            if last_line and not last_line.startswith(command) and (last_line.endswith('>') or last_line.endswith('#')):
                cmd_pos = output.rfind(command)
                last_pos = output.rfind(last_line)
                if last_pos > cmd_pos:
                    chan.close()
                    return output
        except Exception:
            break

    chan.close()
    return output


def fetch_up_server_interfaces_via_ssh(
    ip: str,
    username: str,
    password: Optional[str] = None,
    key_file: Optional[str] = None,
    port: int = 22,
) -> tuple[list[dict], Optional[str]]:
    """Return UP physical Linux interfaces with MAC (IP optional)."""
    import paramiko

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        client.connect(
            ip,
            port=port,
            username=username,
            password=password,
            key_filename=key_file,
            timeout=10,
            look_for_keys=False,
            allow_agent=False,
        )
        raw = _exec(client, "ip -j addr show 2>/dev/null", timeout=10)
        data = json.loads(raw or "[]")
        interfaces = []
        for item in data:
            name = item.get("ifname") or ""
            mac = item.get("address") or ""
            if not _is_physical_interface(name):
                continue
            if item.get("operstate") != "UP":
                continue
            if not mac:
                continue
            inet = next((a for a in item.get("addr_info", []) if a.get("family") == "inet"), None)
            interfaces.append({
                "name": name,
                "ip": inet.get("local") if inet else None,
                "prefixlen": inet.get("prefixlen") if inet else None,
                "mac": mac.lower(),
                "operstate": item.get("operstate"),
            })
        return interfaces, None
    except Exception as e:
        return [], str(e)
    finally:
        client.close()


def stimulate_mac_learning_via_ssh(
    ip: str,
    username: str,
    iface: str,
    password: Optional[str] = None,
    key_file: Optional[str] = None,
    port: int = 22,
) -> Optional[str]:
    """Send an ARP probe (arping) from a specific interface so the switch learns its source MAC.
    Uses a broadcast or the .1 gateway as target — no working IP config required.
    """
    import paramiko

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            ip,
            port=port,
            username=username,
            password=password,
            key_filename=key_file,
            timeout=10,
            look_for_keys=False,
            allow_agent=False,
        )
        # Try arping broadcast first (works even without IP on the interface)
        # Fall back to regular ping via interface if arping not available
        _exec(
            client,
            f"arping -I {iface} -c 1 -w 2 255.255.255.255 >/dev/null 2>&1 || "
            f"arping -I {iface} -c 1 -w 2 0.0.0.0 >/dev/null 2>&1 || true",
            timeout=6,
        )
        return None
    except Exception as e:
        return str(e)
    finally:
        client.close()


def _mac_formats(mac: str) -> list[str]:
    compact = "".join(c for c in mac.lower() if c in "0123456789abcdef")
    if len(compact) != 12:
        return [mac.lower()]
    return [
        compact,
        ":".join(compact[i:i + 2] for i in range(0, 12, 2)),
        "-".join(compact[i:i + 2] for i in range(0, 12, 2)),
        f"{compact[0:4]}-{compact[4:8]}-{compact[8:12]}",
        f"{compact[0:4]}.{compact[4:8]}.{compact[8:12]}",
    ]


def _parse_mac_address_output(raw: str, mac: str) -> dict:
    import re

    compact = "".join(c for c in mac.lower() if c in "0123456789abcdef")
    candidates = []
    for line in raw.splitlines():
        line_s = line.strip()
        if not line_s or "display mac-address" in line_s.lower():
            continue
        normalized_line = "".join(c for c in line.lower() if c in "0123456789abcdef")
        if compact and compact not in normalized_line:
            continue
        candidates.append(line_s)

    if not candidates:
        return {"found": False, "interface": None, "vlan": None}

    line = candidates[0]
    vlan = None
    vlan_match = re.search(r"(?<![/\w-])(\d{1,4})(?![/\w-])", line)
    if vlan_match:
        vlan = vlan_match.group(1)

    iface = None
    iface_patterns = [
        r"(?:X?GigabitEthernet|Ten-GigabitEthernet|FortyGigE|HundredGigE|Ethernet|GE|XGE|Eth-Trunk|Bridge-Aggregation)[\w/.-]+",
        r"\b(?:Eth|Gi|Te|Twe|Fo|Hu)\d+(?:/\d+)+(?:\.\d+)?\b",
    ]
    for pattern in iface_patterns:
        match = re.search(pattern, line, re.IGNORECASE)
        if match:
            iface = match.group(0)
            break

    return {"found": True, "interface": iface, "vlan": vlan, "line": line}


def _parse_mac_table_line(line: str) -> Optional[dict]:
    """
    Parse a single line from 'display mac-address' output.
    Returns {mac, interface, vlan} or None if the line doesn't contain a valid MAC entry.
    """
    import re

    line_s = line.strip()
    if not line_s:
        return None
    if "display mac-address" in line_s.lower():
        return None
    if line_s.startswith("---"):
        return None

    # Minimal heuristics to avoid junk lines
    # A valid MAC line should contain at least 10 hex-like chars
    hex_chars = sum(1 for c in line_s.lower() if c in "0123456789abcdef")
    if hex_chars < 10:
        return None

    compact = "".join(c for c in line_s if c in "0123456789abcdefABCDEF").lower()
    if len(compact) < 10:
        return None

    # Extract MAC (first contiguous hex group that looks like a MAC)
    mac = None
    mac_pattern = re.compile(
        r'(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}'
        r'|[0-9A-Fa-f]{4}\.[0-9A-Fa-f]{4}\.[0-9A-Fa-f]{4}'
        r'|[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}'
        r'|[0-9A-Fa-f]{12}'
    )
    mac_match = mac_pattern.search(line_s)
    if mac_match:
        raw_mac = mac_match.group(0)
        # Normalize to xx:xx:xx:xx:xx:xx
        clean = "".join(c for c in raw_mac.lower() if c in "0123456789abcdef")
        mac = ":".join(clean[i:i+2] for i in range(0, 12, 2))

    if not mac:
        return None

    # Extract VLAN (first number that looks reasonable)
    vlan = None
    vlan_match = re.search(r"(?<![\w./-])(\d{1,4})(?![\w./-])", line_s)
    if vlan_match:
        v = int(vlan_match.group(1))
        if 1 <= v <= 4094:
            vlan = str(v)

    # Extract interface name
    iface = None
    iface_patterns = [
        r"(?:X?GigabitEthernet|Ten-GigabitEthernet|FortyGigE|HundredGigE|Ethernet|GE|XGE|Eth-Trunk|Bridge-Aggregation)[\w/.-]+",
        r"\b(?:Eth|Gi|Te|Twe|Fo|Hu)\d+(?:/\d+)+",
    ]
    for pattern in iface_patterns:
        match = re.search(pattern, line_s, re.IGNORECASE)
        if match:
            iface = match.group(0)
            break

    if not iface:
        return None

    return {"mac": mac, "interface": iface, "vlan": vlan}


def fetch_all_macs_from_switch_via_ssh(
    ip: str,
    username: str,
    password: Optional[str] = None,
    port: int = 22,
) -> dict:
    """
    Connect to an H3C/Huawei switch once and dump the full MAC address table.
    Returns a dict: {
        "mac_map": { "xx:xx:xx:xx:xx:xx": {"interface": ..., "vlan": ...}, ... },
        "raw_output": ...,
        "error": ...
    }
    """
    import paramiko

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            ip,
            port=port,
            username=username,
            password=password,
            timeout=10,
            look_for_keys=False,
            allow_agent=False,
        )
        raw = _interact_exec(client, "display mac-address | no-more", timeout=30)
        mac_map = {}
        for line in raw.splitlines():
            parsed = _parse_mac_table_line(line)
            if parsed and parsed["mac"] not in mac_map:
                mac_map[parsed["mac"]] = {
                    "interface": parsed["interface"],
                    "vlan": parsed["vlan"],
                }
        return {
            "mac_map": mac_map,
            "raw_output": raw,
            "error": None,
        }
    except Exception as e:
        return {
            "mac_map": {},
            "raw_output": None,
            "error": str(e),
        }
    finally:
        client.close()


def find_mac_on_switch_via_ssh(
    ip: str,
    username: str,
    mac: str,
    password: Optional[str] = None,
    port: int = 22,
) -> dict:
    """Query H3C/Huawei-style MAC address table and parse the learned interface."""
    import paramiko

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            ip,
            port=port,
            username=username,
            password=password,
            timeout=10,
            look_for_keys=False,
            allow_agent=False,
        )
        outputs = []
        try:
            _interact_exec(client, "screen-length 0 temporary", timeout=5)
        except Exception:
            pass
        for mac_format in _mac_formats(mac):
            raw = _interact_exec(client, f"display mac-address | include {mac_format}", timeout=12)
            outputs.append(raw)
            parsed = _parse_mac_address_output(raw, mac_format)
            if parsed.get("found"):
                parsed["raw_output"] = raw
                parsed["queried_mac"] = mac_format
                return parsed
        return {
            "found": False,
            "interface": None,
            "vlan": None,
            "raw_output": "\n".join(outputs),
        }
    except Exception as e:
        return {
            "found": False,
            "interface": None,
            "vlan": None,
            "raw_output": None,
            "error": str(e),
        }
    finally:
        client.close()


def _parse_display_version(raw: str) -> dict:
    """
    Parse 'display version' output from H3C / Huawei / Cisco CLI.
    Extracts: hostname, os_type, os_version, board_type, uptime, patch_version.
    Vendor is auto-detected by keywords in the output.
    """
    import re
    lines = raw.split('\n')
    result = {
        "hostname": None,
        "os_type": None,
        "os_version": None,
        "board_type": None,
        "uptime": None,
        "patch_version": None,
    }

    # Strip control chars from each line
    clean_lines = [re.sub(r'[\r\x00-\x1f]', '', l).strip() for l in lines]
    full_text = ' '.join(clean_lines)

    # ── Huawei VRP ───────────────────────────────────────────────────────────
    if 'VRP (R) software' in full_text or 'Huawei Versatile Routing Platform' in full_text:
        result["os_type"] = "Huawei VRP"

        # "VRP (R) software, Version 8.150 (CE6860EI V200R002C50SPC800)"
        version_match = re.search(r'Version\s+([\d.]+)\s*\(([^)]+)\)', full_text)
        if version_match:
            result["os_version"] = f"VRP {version_match.group(1)} ({version_match.group(2)})"

        # "Patch Version: V200R002SPH016" — use raw line, not full_text
        for l in lines:
            if 'Patch' in l and 'Version' in l:
                pm = re.search(r'Patch\s+Version:\s*(.+)', l)
                if pm:
                    result["patch_version"] = pm.group(1).strip()
                break

        # "Board Type : CE6860-48S8CQ-EI" — use raw line
        for l in lines:
            if re.search(r'Board\s+Type', l, re.IGNORECASE):
                bm = re.search(r'Board\s+Type\s*:\s*(.+)', l, re.IGNORECASE)
                if bm:
                    result["board_type"] = bm.group(1).strip()
                break

        # "HUAWEI CE6860-48S8CQ-EI uptime is 193 days, 1 hour, 45 minutes"
        uptime_match = re.search(r'uptime\s+is\s+([^,\n]+(?:,\s*\d+\s*hours?)?(?:,\s*\d+\s*minutes?)?)', full_text, re.IGNORECASE)
        if uptime_match:
            result["uptime"] = uptime_match.group(1).strip()

        # Hostname: from hostname line or uptime line
        for l in lines:
            if re.match(r'\S+\s*\(Master\)', l) or re.match(r'[A-Z][A-Z0-9]+-[A-Z0-9-]+\s*\(Master\)', l):
                hm = re.search(r'([A-Z][A-Z0-9]+-[A-Z0-9-]+)', l)
                if hm:
                    result["hostname"] = hm.group(1).split('(')[0].strip()
                break

    # ── H3C Comware ─────────────────────────────────────────────────────────
    elif any(k in full_text for k in ('H3C', 'Comware')):
        result["os_type"] = "H3C Comware"
        version_match = re.search(r'Comware\s+Software.*?Version\s+([\d.]+)', full_text, re.IGNORECASE)
        if version_match:
            result["os_version"] = f"Comware Version {version_match.group(1)}"
        board_match = re.search(r'H3C\s+([A-Z][\w-]+)', full_text)
        if board_match:
            result["board_type"] = board_match.group(1)
        uptime_match = re.search(r'uptime\s+is\s+([^,\n]+)', full_text, re.IGNORECASE)
        if uptime_match:
            result["uptime"] = uptime_match.group(1).strip()

    # ── Cisco IOS ────────────────────────────────────────────────────────────
    elif 'Cisco' in full_text:
        result["os_type"] = "Cisco IOS"
        version_match = re.search(r'Cisco\s+IOS.*?Version\s+([\d.]+)', full_text, re.IGNORECASE)
        if version_match:
            result["os_version"] = f"IOS Version {version_match.group(1)}"
        uptime_match = re.search(r'uptime\s+is\s+([^,\n]+)', full_text, re.IGNORECASE)
        if uptime_match:
            result["uptime"] = uptime_match.group(1).strip()

    return result


def get_switch_info_via_ssh(
    ip: str,
    username: str,
    password: Optional[str] = None,
    port: int = 22,
) -> SwitchInfo:
    """
    Connect to a network switch via SSH (interactive CLI session) and fetch
    device info using 'display version'.
    Supports: H3C Comware, Huawei VRP, Cisco IOS (auto-detected).
    """
    import paramiko
    import re

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        client.connect(
            ip,
            port=port,
            username=username,
            password=password,
            timeout=10,
            look_for_keys=False,
            allow_agent=False,
        )

        output = _interact_exec(client, "display version")
        parsed = _parse_display_version(output)

        return SwitchInfo(
            hostname=parsed.get("hostname"),
            os_type=parsed.get("os_type", "unknown"),
            os_version=parsed.get("os_version"),
            board_type=parsed.get("board_type"),
            uptime=parsed.get("uptime"),
            patch_version=parsed.get("patch_version"),
        )

    except Exception as e:
        return SwitchInfo(error=str(e))

    finally:
        client.close()
