from __future__ import annotations

import getpass
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from orgchart.auth import hash_password


if __name__ == "__main__":
    print(hash_password(getpass.getpass("Password (10+ characters): ")))
