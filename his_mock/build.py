"""Build the mock hospital's store from the fixtures (SYNTHETIC only).

    python -m his_mock.build [--out DIR] [--seed N] [--no-pdf] [--no-hl7] [--no-dicom] [--upload]

Writes DIR (default data/his_mock/ or $TB_HIS_MOCK_DATA): store.json, fixture_index.json, events.jsonl, the report PDFs
in documents/ (1.2, pdf venv subprocess), events.hl7 (1.4), synthetic DICOM in dicom/ (1.7) and a token (kept on rebuild).
`--upload` then pushes the DICOM studies to Orthanc (127.0.0.1:8042) when it answers. Prints a one-line summary.
"""
import argparse
import sys

from . import generator
from .paths import DATA_DIR, layout


def summary(store, out_dir):
    docs = sum(1 for r in store.reports.values() for v in r["versions"] if (v.get("document") or {}).get("path"))
    studies = sum(1 for s in store.imaging_studies.values() if s.get("status") == "available")
    return (f"his_mock built into {out_dir} (seed {store.meta['seed']}, fixtures {store.meta['fixture_version']}): "
            f"{len(store.patients)} patients, {len(store.encounters)} encounters, {len(store.orders)} orders, "
            f"{len(store.reports)} reports, {len(store.events)} events, {docs} report PDFs, {studies} DICOM studies")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m his_mock.build", description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(DATA_DIR), help="data directory (default %(default)s)")
    ap.add_argument("--seed", type=int, default=generator.DEFAULT_SEED, help="generator seed (default %(default)s)")
    ap.add_argument("--no-pdf", action="store_true", help="skip the report PDFs (1.2)")
    ap.add_argument("--no-hl7", action="store_true", help="skip the HL7 event feed (1.4)")
    ap.add_argument("--no-dicom", action="store_true", help="skip the synthetic DICOM studies (1.7)")
    ap.add_argument("--upload", action="store_true", help="upload the DICOM studies to Orthanc after the build")
    args = ap.parse_args(argv)
    if "tumour_board" in args.out.replace("\\", "/").split("/"):
        ap.error("the mock hospital never writes under data/tumour_board/")
    store = generator.build(args.out, seed=args.seed, documents=not args.no_pdf, hl7=not args.no_hl7,
                            dicom=not args.no_dicom)
    print(summary(store, args.out))
    if args.upload:
        from . import dicom_studies

        if not dicom_studies.orthanc_alive():
            print("orthanc not answering on 127.0.0.1:8042; DICOM not uploaded (his_mock/orthanc.sh start, then "
                  "python -m his_mock.dicom_studies --upload)")
            return 1
        result = dicom_studies.upload_all(store, layout(args.out)["dicom"])
        problems = dicom_studies.verify(store)
        print(f"orthanc: {result.get('stored', 0)} instances stored, {result.get('already_stored', 0)} already there, "
              f"{len(result.get('studies', []))} studies; verify: {'OK' if not problems else '; '.join(problems[:3])}")
        return 0 if not problems else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
