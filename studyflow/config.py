from __future__ import annotations

import os
from pathlib import Path
from typing import Dict


DEFAULT_OBSIDIAN_VAULT = Path("/Users/rh/Documents/Obsidian Vault")
DEFAULT_DATA_DIR = Path(".studyflow")
DEFAULT_PLANS_DIR = DEFAULT_DATA_DIR / "plans"


def load_dotenv(path: str = ".env", override: bool = True) -> Dict[str, str]:
    env_path = Path(path)
    loaded: Dict[str, str] = {}
    if not env_path.exists():
        return loaded

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and (override or key not in os.environ):
            os.environ[key] = value
        loaded[key] = value
    return loaded


def env_path(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    return Path(value).expanduser() if value else default
