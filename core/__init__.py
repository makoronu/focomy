"""Focomy - The Most Beautiful CMS"""

from pathlib import Path


def _get_version() -> str:
    """Get version from pyproject.toml (preferred) or importlib.metadata."""
    # 1. Try pyproject.toml first (development / Docker / local)
    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib
        except ImportError:
            tomllib = None

    if tomllib:
        for base in [Path(__file__).parent.parent, Path.cwd()]:
            pyproject = base / "pyproject.toml"
            if pyproject.exists():
                try:
                    with open(pyproject, "rb") as f:
                        data = tomllib.load(f)
                    ver = data.get("project", {}).get("version")
                    if ver:
                        return ver
                except Exception:
                    pass

    # 2. Fallback to importlib.metadata (pip installed)
    try:
        from importlib.metadata import version
        return version("focomy")
    except Exception:
        pass

    # 3. Final fallback
    return "0.0.0"


__version__ = _get_version()
