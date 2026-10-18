"""Where the mock hospital keeps its data (SYNTHETIC only): data/his_mock/ in the repo, or $TB_HIS_MOCK_DATA.

The directory is gitignored and rebuilt from a seed (python -m his_mock.build). Never point it at data/tumour_board/.
"""
import os
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("TB_HIS_MOCK_DATA") or REPO / "data" / "his_mock")

STORE_NAME = "store.json"
DOCUMENTS_NAME = "documents"
DICOM_NAME = "dicom"
EVENTS_NAME = "events.jsonl"
HL7_NAME = "events.hl7"
TOKEN_NAME = "token"              # the FHIR / document read token (Vaidyx-TB reads with it)
WRITE_TOKEN_NAME = "write_token"  # the JSON write APIs (/his/api, /desk/api) for machine callers: the demo and e2e scripts
FIXTURE_INDEX_NAME = "fixture_index.json"

STORE_PATH = DATA_DIR / STORE_NAME
DOCUMENTS_DIR = DATA_DIR / DOCUMENTS_NAME
DICOM_DIR = DATA_DIR / DICOM_NAME
EVENTS_PATH = DATA_DIR / EVENTS_NAME
HL7_PATH = DATA_DIR / HL7_NAME
TOKEN_PATH = DATA_DIR / TOKEN_NAME
FIXTURE_INDEX_PATH = DATA_DIR / FIXTURE_INDEX_NAME


def layout(data_dir=None):
    """The same file names under another data directory (tests build into a temporary one)."""
    d = Path(data_dir) if data_dir else DATA_DIR
    return {
        "data_dir": d,
        "store": d / STORE_NAME,
        "documents": d / DOCUMENTS_NAME,
        "dicom": d / DICOM_NAME,
        "events": d / EVENTS_NAME,
        "hl7": d / HL7_NAME,
        "token": d / TOKEN_NAME,
        "write_token": d / WRITE_TOKEN_NAME,
        "fixture_index": d / FIXTURE_INDEX_NAME,
    }
