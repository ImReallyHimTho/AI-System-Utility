# ai_system_utility/core/system_info.py

import platform
import shutil
import time
from dataclasses import dataclass, asdict
from typing import Dict, Any, List

try:
    import psutil  # type: ignore
except ImportError:
    psutil = None  # We'll gracefully degrade without it.


@dataclass
class DiskInfo:
    device: str
    mountpoint: str
    total_gb: float
    used_gb: float
    free_gb: float
    percent_used: float


@dataclass
class SystemInfo:
    os: str
    os_version: str
    hostname: str
    machine: str
    processor: str
    uptime_seconds: int
    cpu_percent: float
    total_ram_gb: float
    used_ram_gb: float
    ram_percent: float
    disks: List[DiskInfo]


def _get_uptime_seconds() -> int:
    if psutil is not None:
        try:
            boot_time = psutil.boot_time()
            return int(time.time() - boot_time)
        except Exception:
            pass
    # Fallback: we don't know real uptime, but don't crash.
    return 0


def _get_cpu_percent(interval: float = 0.1) -> float:
    if psutil is not None:
        try:
            return float(psutil.cpu_percent(interval=interval))
        except Exception:
            pass
    return 0.0


def _get_memory_info() -> Dict[str, float]:
    if psutil is not None:
        try:
            mem = psutil.virtual_memory()
            total_gb = mem.total / (1024 ** 3)
            used_gb = (mem.total - mem.available) / (1024 ** 3)
            return {
                "total_gb": total_gb,
                "used_gb": used_gb,
                "percent": float(mem.percent),
            }
        except Exception:
            pass

    # Fallback when psutil is unavailable or fails
    return {"total_gb": 0.0, "used_gb": 0.0, "percent": 0.0}


def _get_disks() -> List[DiskInfo]:
    disks: List[DiskInfo] = []

    if psutil is not None:
        try:
            for part in psutil.disk_partitions(all=False):
                try:
                    usage = psutil.disk_usage(part.mountpoint)
                except PermissionError:
                    continue
                disks.append(
                    DiskInfo(
                        device=part.device,
                        mountpoint=part.mountpoint,
                        total_gb=usage.total / (1024 ** 3),
                        used_gb=usage.used / (1024 ** 3),
                        free_gb=usage.free / (1024 ** 3),
                        percent_used=float(usage.percent),
                    )
                )
            return disks
        except Exception:
            # fall through to minimal fallback
            pass

    # Minimal fallback: try system drive only (Windows C:\)
    try:
        total, used, free = shutil.disk_usage("C:\\")
        disks.append(
            DiskInfo(
                device="C:",
                mountpoint="C:\\",
                total_gb=total / (1024 ** 3),
                used_gb=used / (1024 ** 3),
                free_gb=free / (1024 ** 3),
                percent_used=round(used / total * 100.0, 2),
            )
        )
    except Exception:
        # If even that fails, return empty list
        pass

    return disks


def get_system_info() -> SystemInfo:
    """
    Collects a snapshot of system info suitable for GUI/CLI display.
    """
    os_name = platform.system()
    os_version = platform.version()
    hostname = platform.node()
    machine = platform.machine()
    processor = platform.processor() or "Unknown"

    uptime_seconds = _get_uptime_seconds()
    cpu_percent = _get_cpu_percent()
    mem = _get_memory_info()
    disks = _get_disks()

    return SystemInfo(
        os=os_name,
        os_version=os_version,
        hostname=hostname,
        machine=machine,
        processor=processor,
        uptime_seconds=uptime_seconds,
        cpu_percent=cpu_percent,
        total_ram_gb=mem["total_gb"],
        used_ram_gb=mem["used_gb"],
        ram_percent=mem["percent"],
        disks=disks,
    )


def get_system_info_dict() -> Dict[str, Any]:
    """
    Helper if you ever want a serializable dict instead of dataclasses.
    """
    info = get_system_info()
    return asdict(info)
