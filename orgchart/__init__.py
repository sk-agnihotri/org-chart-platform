"""Org chart inference platform package."""

from pathlib import Path

_src_package = Path(__file__).resolve().parent.parent / "src" / "orgchart"
if _src_package.is_dir():
    __path__.append(str(_src_package))
