"""재현성 기록: 실행 환경, 패키지 버전, git 커밋, 설정 해시, 난수 시드."""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from importlib import metadata
from pathlib import Path

TRACKED_PACKAGES = ("numpy", "scipy", "numba", "pydantic", "PyYAML", "pytest",
                    "xarray", "netCDF4", "h5netcdf", "pyarrow", "pandas",
                    "geopandas", "rasterio", "shapely", "pyproj", "h5py", "matplotlib", "typer")


def package_versions() -> dict[str, str]:
    out = {}
    for name in TRACKED_PACKAGES:
        try:
            out[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            pass
    return out


def git_commit(repo: Path | None = None) -> str | None:
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True,
                           text=True, check=True)
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=repo, capture_output=True,
                               text=True, check=True).stdout.strip()
        return r.stdout.strip() + ("-dirty" if dirty else "")
    except (OSError, subprocess.CalledProcessError):
        return None


def environment_record() -> dict:
    import os
    return {
        "python": sys.version.split()[0],
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu_count": os.cpu_count(),
        "packages": package_versions(),
        "git_commit": git_commit(Path(__file__).resolve().parent.parent),
    }


def config_hash(config_dict: dict) -> str:
    blob = json.dumps(config_dict, sort_keys=True, default=str).encode()
    return hashlib.sha256(blob).hexdigest()
