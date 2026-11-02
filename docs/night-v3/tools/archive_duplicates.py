"""Archive duplicate test Case Files (night-v3 item 1.2). Archives, never deletes.

Run from the repo root with the app venv, against the live TB data root (the app may keep running: case.json is written
atomically and the audit line is hash-chained like any user action):

    /data/vaidyx/venv/app/bin/python docs/night-v3/tools/archive_duplicates.py --by night-v3-run \
        --reason "duplicate test file" TB-2026-0004 E2E-20261018-135112-B

Refuses protected Case Files (the real case), files that are already archived, and files that do not exist. Prints only
ids, protocol, owner department and the archive status: no patient data.
"""
from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from tumour_board import access, config, store, team  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("case_ids", nargs="+")
    ap.add_argument("--by", required=True, help="who archives (written in the audit)")
    ap.add_argument("--reason", required=True)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    rc = 0
    for cid in a.case_ids:
        if cid in config.PROTECTED_CASES:
            print(f"{cid}: protected, refused")
            rc = 2
            continue
        try:
            c = store.get_case(cid)
            if not c:
                raise FileNotFoundError(cid)
        except Exception as e:  # noqa: BLE001
            print(f"{cid}: not found ({type(e).__name__})")
            rc = 2
            continue
        print(f"{cid}: protocol={c.get('protocol')} owner={c.get('department')} archived={bool(access.is_archived(c))}")
        if access.is_archived(c):
            print(f"{cid}: already archived, left as it is")
            continue
        if a.dry_run:
            print(f"{cid}: would archive (dry run)")
            continue
        try:
            team.archive(cid, a.by, a.reason)
        except team.TeamError as e:
            print(f"{cid}: refused: {e}")
            rc = 2
            continue
        c2 = store.get_case(cid)
        last = (store.read_audit(cid, limit=5) or [])[-1]
        print(f"{cid}: archived at {c2['archived']['at']} by {c2['archived']['by']}; audit kind={last.get('kind')} reason={last.get('reason')!r}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
