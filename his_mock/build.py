"""Build the mock hospital's store from the fixtures (SYNTHETIC only).

    python -m his_mock.build [--out DIR] [--seed N] [--no-pdf] [--no-hl7] [--no-dicom] [--images public|synthetic] [--upload]

Writes DIR (default data/his_mock/ or $TB_HIS_MOCK_DATA): store.json, fixture_index.json, events.jsonl, the report PDFs
in documents/ (1.2, pdf venv subprocess), events.hl7 (1.4), DICOM in dicom/ (1.7) and a token (kept on rebuild).
`--images public` (the default, or $TB_HIS_MOCK_IMAGES): the studies pacs_public/assignment.json maps get the relabelled
public library images, the rest synthetic test patterns; without the library every study is synthetic (no error).
`--images synthetic`: test patterns only. The choice is kept in the store for the studies the desk builds later.
`--upload` then pushes the DICOM studies to Orthanc (127.0.0.1:8042) when it answers. The 9 demo logins of the HIMS
screens are ensured (accounts.json, logins.tsv mode 600; existing passwords kept). Prints a one-line summary.
"""
import argparse
import os
import sys

from . import generator
from .paths import DATA_DIR, layout


def summary(store, out_dir):
    docs = sum(1 for r in store.reports.values() for v in r["versions"] if (v.get("document") or {}).get("path"))
    studies = sum(1 for s in store.imaging_studies.values() if s.get("series"))
    return (f"his_mock built into {out_dir} (seed {store.meta['seed']}, fixtures {store.meta['fixture_version']}): "
            f"{len(store.patients)} patients, {len(store.encounters)} encounters, {len(store.orders)} orders, "
            f"{len(store.reports)} reports, {len(store.events)} events, {docs} report PDFs, {studies} DICOM studies")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m his_mock.build", description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(DATA_DIR), help="data directory (default %(default)s)")
    ap.add_argument("--seed", type=int, default=generator.DEFAULT_SEED, help="generator seed (default %(default)s)")
    ap.add_argument("--no-pdf", action="store_true", help="skip the report PDFs (1.2)")
    ap.add_argument("--no-hl7", action="store_true", help="skip the HL7 event feed (1.4)")
    ap.add_argument("--no-dicom", action="store_true", help="skip the DICOM studies (1.7)")
    ap.add_argument("--images", choices=("public", "synthetic"), default=os.environ.get("TB_HIS_MOCK_IMAGES") or "public",
                    help="image source of the DICOM studies (default %(default)s; public falls back to synthetic per "
                         "study, and everywhere when the library is not installed)")
    ap.add_argument("--upload", action="store_true", help="upload the DICOM studies to Orthanc after the build")
    args = ap.parse_args(argv)
    if "tumour_board" in args.out.replace("\\", "/").split("/"):
        ap.error("the mock hospital never writes under data/tumour_board/")
    store = generator.build(args.out, seed=args.seed, documents=not args.no_pdf, hl7=not args.no_hl7, dicom=False)
    images = ""
    if not args.no_dicom:          # the image source switch (pacs_public phase 2); generator.build keeps synthetic
        from . import dicom_studies

        files = layout(args.out)
        dicom_studies.build_all(store, files["dicom"], source=args.images)
        store.save(files["store"], files["events"])
        c = dicom_studies.image_counts(store)
        images = f" ({c['public']} with public library images, {c['synthetic']} synthetic)"
        for acc, reason in c["fallback"]:
            print(f"{acc}: {reason}")
    from . import auth   # the 9 demo logins (bcrypt), kept across rebuilds like the token

    accounts = auth.Accounts(layout(args.out)["data_dir"])
    created = accounts.ensure(store)
    print(summary(store, args.out) + images + f"; accounts: {len(created)} created, {len(accounts.accounts)} total, passwords in "
          f"{accounts.logins_path} (mode 600, never printed; python -m his_mock.auth --reset recreates them)")
    if args.upload:
        from . import dicom_studies

        if not dicom_studies.orthanc_alive():
            print("orthanc not answering on 127.0.0.1:8042; DICOM not uploaded (his_mock/orthanc.sh start, then "
                  "python -m his_mock.dicom_studies --upload)")
            return 1
        files = layout(args.out)
        result = dicom_studies.upload_all(store, files["dicom"])
        store.save(files["store"], files["events"])   # the studies are now available (uploaded)
        problems = dicom_studies.verify(store)
        print(f"orthanc: {result.get('stored', 0)} instances stored, {result.get('already_stored', 0)} already there, "
              f"{result.get('failed', 0)} failed, {len(result.get('studies', []))} studies, "
              f"{result.get('replaced', 0)} older copies replaced; "
              f"verify: {'OK' if not problems else '; '.join(problems[:3])}")
        return 0 if not problems else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
