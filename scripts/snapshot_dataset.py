from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OBSERVABLE_FILES = ("companies.csv", "employees.csv", "title_taxonomy.csv", "dataset_metadata.csv")


def main() -> None:
    parser = argparse.ArgumentParser(description="Save an observable dataset snapshot for later comparison.")
    parser.add_argument("name", nargs="?", help="Snapshot label; defaults to the current UTC timestamp.")
    args = parser.parse_args()
    name = args.name or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", name):
        parser.error("Snapshot name must use 1-64 letters, numbers, dots, underscores, or hyphens.")
    destination = DATA / "snapshots" / name
    if destination.exists():
        parser.error(f"Snapshot already exists: {destination}")
    missing = [filename for filename in OBSERVABLE_FILES if not (DATA / filename).is_file()]
    if missing:
        parser.error(f"Missing observable dataset files: {', '.join(missing)}")
    destination.mkdir(parents=True)
    for filename in OBSERVABLE_FILES:
        shutil.copy2(DATA / filename, destination / filename)
    manifest = {"name": name, "created_at_utc": datetime.now(timezone.utc).isoformat(), "files": list(OBSERVABLE_FILES)}
    (destination / "snapshot.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Snapshot saved: {destination.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
