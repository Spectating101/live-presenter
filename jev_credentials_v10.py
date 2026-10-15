"""Read only Jev credential assignments; never execute an env file as shell code."""
import os
from pathlib import Path
import shlex


def load_jev_env(path: str | Path | None = None) -> bool:
    """Explicit path / JEV_ENV_FILE / optional .env; existing environment wins."""
    if os.getenv("JEV_API_KEY") or os.getenv("TYPESAFE_API_KEY"):
        return True
    source = path or os.getenv("JEV_ENV_FILE")
    file = Path(source).expanduser() if source else Path(".env")
    if not file.exists():
        if source:
            raise ValueError("Jev env file does not exist")
        return False
    for line in file.read_text(encoding="utf-8").splitlines():
        parts = shlex.split(line, comments=True)
        if parts and parts[0] == "export":
            parts = parts[1:]
        if len(parts) == 1 and "=" in parts[0]:
            name, value = parts[0].split("=", 1)
            if name in {"JEV_API_KEY", "TYPESAFE_API_KEY"} and value and not os.environ.get(name):
                os.environ[name] = value
    return bool(os.getenv("JEV_API_KEY") or os.getenv("TYPESAFE_API_KEY"))
