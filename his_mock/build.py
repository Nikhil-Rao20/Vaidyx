"""Build the mock hospital's store from the fixtures (SYNTHETIC only).

    python -m his_mock.build [--out DIR] [--seed N]

Writes DIR (default data/his_mock/ or $TB_HIS_MOCK_DATA): store.json, fixture_index.json, events.jsonl, documents/,
dicom/ and a token (kept on rebuild). Prints a one-line summary.
"""
import argparse
import sys

from . import generator
from .paths import DATA_DIR


def summary(store, out_dir):
    return (f"his_mock built into {out_dir} (seed {store.meta['seed']}, fixtures {store.meta['fixture_version']}): "
            f"{len(store.patients)} patients, {len(store.encounters)} encounters, {len(store.orders)} orders, "
            f"{len(store.reports)} reports, {len(store.events)} events")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m his_mock.build", description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(DATA_DIR), help="data directory (default %(default)s)")
    ap.add_argument("--seed", type=int, default=generator.DEFAULT_SEED, help="generator seed (default %(default)s)")
    args = ap.parse_args(argv)
    if "tumour_board" in args.out.replace("\\", "/").split("/"):
        ap.error("the mock hospital never writes under data/tumour_board/")
    store = generator.build(args.out, seed=args.seed)
    print(summary(store, args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
