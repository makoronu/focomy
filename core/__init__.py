"""Focomy - The Most Beautiful CMS"""

try:
    from importlib.metadata import version
    __version__ = version("focomy")
except Exception:
    __version__ = "0.0.0"  # Development fallback
