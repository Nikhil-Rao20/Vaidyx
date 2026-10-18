"""The mock PACS images (plan item V2-1.7): one DICOM study per imaging study of the store.

    from his_mock import dicom_studies
    dicom_studies.build_all(store, dicom_dir)        # write the files, mark the studies available (generator.build calls it)
    dicom_studies.build_all(store, dicom_dir, source="public")   # public library images where pacs_public maps them
    dicom_studies.upload_all(store, dicom_dir)       # POST every file to Orthanc (127.0.0.1:8042)
    dicom_studies.verify(store)                      # QIDO finds every study by Study UID with its accession and counts

    python -m his_mock.dicom_studies --build [--images public|synthetic] | --upload | --verify   [--data DIR] [--orthanc URL]

Two image sources (the switch, pacs_public/README.md "Phase 2"):

- synthetic (the default of build_all, so tests and fresh clones never read a downloaded file): abstract test patterns
  (a gradient, concentric rings, a rectangle, seeded noise and the burned-in word SYNTHETIC) drawn from the accession
  number. Nothing in them looks like anatomy or implies a finding.
- public (`python -m his_mock.build` asks for it; build_all(source="public") records it in store.meta.image_source so the
  reporting desk keeps it for studies reported live): when pacs_public/assignment.json maps the study's accession to a
  series of the public library (/data/vaidyx/tb_resources/dicom_public, de-identified CC BY images from TCIA), that
  series is copied and relabelled with the HIMS identity (pacs_public.relabel.relabel_series: UHID, name, birth date,
  sex, the study UID of ids.study_uid(accession), series / instance UIDs of this module, accession, the HIMS study date
  and time, institution, referring consultant, the test label as StudyDescription) and checked with
  relabel.verify_relabelled. An accession the plan does not know (a study scheduled live at the HIMS desk) gets an
  unused source series of the right modality and body part from the manifest, recorded in pacs_public/
  assignment_live.json (for data/his_mock; another data directory keeps its own beside its store). Everything else
  stays synthetic: a missing library (quietly), a test with no public series
  (ultrasound, bone scan, brain MRI), or a series that fails to relabel or verify (logged, reason recorded).
  Every study records "image_source": {"kind": "public", collection, licence, doi, source_series_uid, ...} or
  {"kind": "synthetic", optional reason}. The env TB_HIS_MOCK_IMAGES=public|synthetic overrides the store's choice.

Scope: humans view PACS images, no model reads them; nothing here interprets pixels (the relabeller rewrites headers only).

Deterministic: the same store gives byte-identical files. Every UID is 2.25.<uuid5 as integer> in ids.STUDY_UID_NAMESPACE:
the Study UID is ids.study_uid(accession) (the store's study_uid), a series is uuid5("<accession>|series|<n>"), an
instance uuid5("<accession>|series|<n>|instance|<m>"), the frame of reference uuid5("<accession>|frame-of-reference").
Dates and times come from the store (the study's day, kept after the order and before the first report), never from now.
"""
import argparse
import hashlib
import json
import logging
import os
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
from pydicom.dataset import Dataset, FileDataset, FileMetaDataset
from pydicom.sequence import Sequence
from pydicom.uid import PYDICOM_IMPLEMENTATION_UID, ExplicitVRLittleEndian

from . import ids, ui
from .ids import IST, parse_time
from .model import _bump

LOG = logging.getLogger("his_mock.dicom_studies")
ORTHANC_URL = "http://127.0.0.1:8042"
REPO = Path(__file__).resolve().parent.parent
PUBLIC_ASSIGNMENT = REPO / "pacs_public" / "assignment.json"          # the plan (python -I pacs_public/relabel.py --plan)
LIVE_ASSIGNMENT = REPO / "pacs_public" / "assignment_live.json"       # picks for accessions the plan does not know
LIVE_NAME = "assignment_live.json"           # another HIMS data directory (a throw-away copy) keeps its picks beside its store
SOURCES = ("public", "synthetic")
IMAGES_ENV = "TB_HIS_MOCK_IMAGES"
INSTITUTION = "Vaidyx Demo Hospital (SYNTHETIC)"
MANUFACTURER = "Vaidyx Synthetic"
IMAGE_COMMENTS = "SYNTHETIC image, no clinical content"
SECONDARY_CAPTURE = "1.2.840.10008.5.1.4.1.1.7"

# modality -> SOP class, instances, rows / columns, bits allocated / stored, stored value range, window centre / width
SPECS = {
    "CT": dict(sop="1.2.840.10008.5.1.4.1.1.2", n=8, size=256, bits=16, stored=12, lo=824, hi=1324, wc=40, ww=400,
               spacing=0.8, thickness=5.0),
    "MR": dict(sop="1.2.840.10008.5.1.4.1.1.4", n=8, size=256, bits=16, stored=16, lo=100, hi=1100, wc=600, ww=1000,
               spacing=0.9, thickness=5.0),
    "CR": dict(sop="1.2.840.10008.5.1.4.1.1.1", n=1, size=512, bits=16, stored=12, lo=600, hi=3400, wc=2000, ww=2800,
               spacing=0.35),
    "MG": dict(sop="1.2.840.10008.5.1.4.1.1.1.2", n=2, size=512, bits=16, stored=12, lo=600, hi=3400, wc=2000, ww=2800,
               spacing=0.1),
    "US": dict(sop="1.2.840.10008.5.1.4.1.1.6.1", n=4, size=256, bits=8, stored=8, lo=20, hi=220, wc=128, ww=256,
               spacing=0.2),
    "PT": dict(sop="1.2.840.10008.5.1.4.1.1.128", n=6, size=128, bits=16, stored=16, lo=500, hi=16000, wc=8000,
               ww=16000, spacing=4.0, thickness=4.0),
    "NM": dict(sop="1.2.840.10008.5.1.4.1.1.20", n=2, size=256, bits=16, stored=16, lo=20, hi=900, wc=460, ww=900,
               spacing=2.4),
}
VOLUME = ("CT", "MR", "PT")       # slices with an image plane and a frame of reference

# mammography view and region (DICOM CID 4014 / 4013 codes): metadata the MG IOD requires, not a finding
_MG_VIEWS = (("R", ["P", "L"]), ("L", ["A", "R"]))
_CC_VIEW = ("399162004", "SCT", "cranio-caudal")
_BREAST = ("76752008", "SCT", "Breast")

# 5 x 7 bitmap letters for the burned-in marker
_FONT = {
    "S": (" ####", "#    ", "#    ", " ### ", "    #", "    #", "#### "),
    "Y": ("#   #", "#   #", " # # ", "  #  ", "  #  ", "  #  ", "  #  "),
    "N": ("#   #", "##  #", "# # #", "#  ##", "#   #", "#   #", "#   #"),
    "T": ("#####", "  #  ", "  #  ", "  #  ", "  #  ", "  #  ", "  #  "),
    "H": ("#   #", "#   #", "#   #", "#####", "#   #", "#   #", "#   #"),
    "E": ("#####", "#    ", "#    ", "#### ", "#    ", "#    ", "#####"),
    "I": (" ### ", "  #  ", "  #  ", "  #  ", "  #  ", "  #  ", " ### "),
    "C": (" ####", "#    ", "#    ", "#    ", "#    ", "#    ", " ####"),
}
MARK = "SYNTHETIC"


# ------------------------------------------------------------------------ identifiers
def uid_for(*parts):
    """2.25.<uuid5 as integer> of "|"-joined parts in the mock's namespace (at most 44 characters)."""
    return "2.25." + str(uuid.uuid5(ids.STUDY_UID_NAMESPACE, "|".join(str(p) for p in parts)).int)


def series_uid(accession, series_no):
    return uid_for(accession, "series", series_no)


def instance_uid(accession, series_no, instance_no):
    return uid_for(accession, "series", series_no, "instance", instance_no)


def frame_of_reference_uid(accession):
    return uid_for(accession, "frame-of-reference")


def orthanc_study_id(patient_id_tag, study_uid):
    """Orthanc's study id: SHA-1 of "PatientID|StudyInstanceUID", lowercase hex in five dash-separated groups of 8."""
    h = hashlib.sha1(f"{patient_id_tag}|{study_uid}".encode("utf-8")).hexdigest()
    return "-".join(h[i:i + 8] for i in range(0, 40, 8))


def viewer_url(study_uid, base="/ohif/"):
    """OHIF viewer path for a study (relative to Orthanc, or to the Vaidyx-TB proxy when `base` says so)."""
    return base.rstrip("/") + "/viewer?StudyInstanceUIDs=" + urllib.parse.quote(study_uid, safe=".")


def study_key(study):
    return study.get("accession") or study["order_id"]


def study_dirname(study):
    return ids.slug(study_key(study))


def _person_name(name, prefix=None):
    """'Venkatesh Rao (SYNTHETIC)' -> 'Rao (SYNTHETIC)^Venkatesh' (DICOM PN: family^given^middle^prefix); the marker stays
    on the family name. 'Dr Arvind Menon' with prefix -> 'Menon^Arvind^^Dr'."""
    text = str(name or "").replace("(SYNTHETIC)", " ").strip()
    if prefix and text.startswith(prefix + " "):
        text = text[len(prefix) + 1:]
    words = text.split()
    family = words[-1] if words else ""
    given = " ".join(words[:-1])
    if "(SYNTHETIC)" in str(name):
        family = (family + " (SYNTHETIC)").strip()
    pn = f"{family}^{given}" if given else family
    if prefix:
        pn = f"{family}^{given}^^{prefix}"
    return pn


def _seed(*parts):
    return int.from_bytes(hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).digest()[:8], "big")


# ------------------------------------------------------------------------ times
def _da(dt):
    return dt.strftime("%Y%m%d")


def _tm(dt):
    return dt.strftime("%H%M%S")


def study_time(store, study):
    """When the images were acquired: on the study's day, after the order, at least 30 minutes before the first report
    version, at a time fixed by the accession number (09:00 to 09:50 by default)."""
    started = parse_time(study["started"])
    day = datetime(started.year, started.month, started.day, tzinfo=IST)
    if len(str(study["started"]).strip()) > 10:
        return started
    order = store.orders.get(study["order_id"]) or {}
    digits = "".join(c for c in study_key(study) if c.isdigit()) or "0"
    t = day + timedelta(hours=9, minutes=10 * (int(digits) % 6))
    lower, upper = day + timedelta(hours=7), day + timedelta(hours=21)
    if order.get("ordered_on"):
        placed = parse_time(order["ordered_on"])
        if placed.date() == day.date():
            lower = max(lower, placed + timedelta(minutes=15))
    report = store.reports.get(order.get("report_id")) if order.get("report_id") else None
    if report and report.get("versions"):
        first = parse_time(report["versions"][0]["reported_on"])
        if first.date() == day.date():
            upper = min(upper, first - timedelta(minutes=30))
    t = min(max(t, lower), upper) if lower <= upper else lower + (upper - lower) / 2
    return t.replace(second=0, microsecond=0)


def _age(dob_iso, on):
    if not dob_iso:
        return None
    b = date.fromisoformat(dob_iso)
    years = on.year - b.year - ((on.month, on.day) < (b.month, b.day))
    return f"{years:03d}Y"


# ------------------------------------------------------------------------ pixels
def pattern(accession, modality, instance_no, n_instances):
    """An abstract test pattern (uint16 / uint8 array): gradient + concentric rings + a rectangle + seeded noise, with the
    word SYNTHETIC burned in at the top left. Parameters come from the accession; the rings and rectangle shift with the
    instance number so a stack scrolls visibly. No anatomy, no finding."""
    s = SPECS[modality]
    size = s["size"]
    rng = np.random.default_rng(_seed(accession, modality))
    theta = rng.uniform(0, 2 * np.pi)
    cx, cy = rng.uniform(-0.3, 0.3, size=2)
    freq = rng.uniform(3.0, 6.0)
    noise_rng = np.random.default_rng(_seed(accession, modality, instance_no))
    frac = (instance_no - 1) / max(1, n_instances - 1)

    ax = np.linspace(-1.0, 1.0, size)
    xx, yy = np.meshgrid(ax, ax)
    gradient = 0.5 + 0.5 * (np.cos(theta) * xx + np.sin(theta) * yy) / np.sqrt(2)
    r = np.hypot(xx - cx, yy - cy)
    rings = 0.5 + 0.5 * np.cos(2 * np.pi * freq * r - np.pi * frac)
    half = 0.2 + 0.4 * frac
    rect = ((np.abs(xx) < half) & (np.abs(yy) < half * 0.6)).astype(float)
    v = 0.45 * gradient + 0.35 * rings + 0.2 * rect + noise_rng.normal(0.0, 0.03, size=(size, size))
    v = np.clip(v, 0.0, 1.0)
    out = s["lo"] + v * (s["hi"] - s["lo"])
    _burn(out, MARK, value=s["hi"])
    dtype = np.uint8 if s["bits"] == 8 else np.uint16
    return np.rint(np.clip(out, 0, (1 << s["stored"]) - 1)).astype(dtype)


def _burn(arr, text, value):
    size = arr.shape[0]
    scale = max(1, size // 128)
    x0 = y0 = max(2, size // 32)
    for i, ch in enumerate(text):
        glyph = _FONT[ch]
        for gy, row in enumerate(glyph):
            for gx, cell in enumerate(row):
                if cell == "#":
                    y = y0 + gy * scale
                    x = x0 + (i * 6 + gx) * scale
                    arr[y:y + scale, x:x + scale] = value


# ------------------------------------------------------------------------ datasets
def _code(value, scheme, meaning):
    c = Dataset()
    c.CodeValue, c.CodingSchemeDesignator, c.CodeMeaning = value, scheme, meaning
    return c


def instance_dataset(store, study, series_no, instance_no, n_instances, sop_class=None):
    """The FileDataset of one synthetic instance (not written)."""
    modality = study["modality"]
    s = SPECS[modality]
    sop_class = sop_class or s["sop"]
    acc = study_key(study)
    patient = store.patients[study["patient_id"]]
    order = store.orders.get(study["order_id"]) or {}
    encounter = store.encounters.get(order.get("encounter_id")) or {}
    consultant = store.practitioners.get(encounter.get("consultant_id")) if encounter.get("consultant_id") else None
    t0 = study_time(store, study)
    t_series = t0 + timedelta(minutes=2 * (series_no - 1))
    t_inst = t_series + timedelta(seconds=15 * instance_no)
    sop_uid = instance_uid(acc, series_no, instance_no)

    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = sop_class
    meta.MediaStorageSOPInstanceUID = sop_uid
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    meta.ImplementationClassUID = PYDICOM_IMPLEMENTATION_UID
    ds = FileDataset(None, {}, file_meta=meta, preamble=b"\0" * 128)

    ds.SpecificCharacterSet = "ISO_IR 192"
    ds.SOPClassUID, ds.SOPInstanceUID = sop_class, sop_uid
    # patient
    ds.PatientName = _person_name(patient["name"])
    ds.PatientID = patient["uhid"]
    ds.IssuerOfPatientID = INSTITUTION
    ds.PatientBirthDate = (patient.get("dob_iso") or "").replace("-", "")
    ds.PatientSex = patient.get("sex") or ""
    age = _age(patient.get("dob_iso"), t0.date())
    if age:
        ds.PatientAge = age
    # study
    ds.StudyInstanceUID = study["study_uid"]
    ds.StudyDate, ds.StudyTime = _da(t0), _tm(t0)
    ds.AccessionNumber = study.get("accession") or ""
    ds.StudyID = "".join(c for c in acc if c.isdigit())[-16:]
    ds.StudyDescription = study.get("description") or ""
    ds.ReferringPhysicianName = _person_name(consultant["name"], prefix="Dr") if consultant else ""
    # series and equipment
    ds.Modality = modality
    ds.SeriesInstanceUID = series_uid(acc, series_no)
    ds.SeriesNumber = series_no
    ds.SeriesDate, ds.SeriesTime = _da(t_series), _tm(t_series)
    ds.SeriesDescription = f"SYNTHETIC {modality} series {series_no}"
    ds.Manufacturer = MANUFACTURER
    ds.InstitutionName = INSTITUTION
    if order.get("performing_department"):
        ds.InstitutionalDepartmentName = order["performing_department"]
    # instance
    ds.InstanceNumber = instance_no
    ds.ContentDate, ds.ContentTime = _da(t_inst), _tm(t_inst)
    ds.AcquisitionDate, ds.AcquisitionTime = _da(t_inst), _tm(t_inst)
    ds.ImageComments = IMAGE_COMMENTS
    ds.BurnedInAnnotation = "NO"          # the burned-in word SYNTHETIC identifies no one
    ds.LossyImageCompression = "00"

    # image pixel module
    pixels = pattern(acc, modality, instance_no, n_instances)
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.Rows, ds.Columns = pixels.shape
    ds.BitsAllocated, ds.BitsStored, ds.HighBit = s["bits"], s["stored"], s["stored"] - 1
    ds.PixelRepresentation = 0
    ds.WindowCenter, ds.WindowWidth = s["wc"], s["ww"]
    ds.PixelSpacing = [s["spacing"], s["spacing"]]
    ds.PixelData = pixels.tobytes()

    if modality in VOLUME:
        z = -s["thickness"] * (instance_no - 1)
        origin = -s["spacing"] * s["size"] / 2
        ds.ImagePositionPatient = [round(origin, 3), round(origin, 3), round(z, 3)]
        ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
        ds.SliceThickness = s["thickness"]
        ds.SliceLocation = round(z, 3)
        ds.FrameOfReferenceUID = frame_of_reference_uid(acc)
        ds.PositionReferenceIndicator = ""
        ds.PatientPosition = "HFS"
    if sop_class == SECONDARY_CAPTURE:
        ds.ConversionType = "SYN"
        return ds
    if modality == "CT":
        ds.ImageType = ["ORIGINAL", "PRIMARY", "AXIAL"]
        ds.RescaleIntercept, ds.RescaleSlope, ds.RescaleType = -1024, 1, "HU"
        ds.KVP = ""
    elif modality == "MR":
        ds.ImageType = ["ORIGINAL", "PRIMARY", "OTHER"]
        ds.ScanningSequence, ds.SequenceVariant, ds.ScanOptions = "RM", "NONE", ""
        ds.MRAcquisitionType = "2D"
        ds.RepetitionTime = ds.EchoTime = ds.EchoTrainLength = ""
    elif modality == "CR":
        ds.ImageType = ["ORIGINAL", "PRIMARY"]
        ds.BodyPartExamined = ds.ViewPosition = ""
        ds.ImagerPixelSpacing = [s["spacing"], s["spacing"]]
    elif modality == "MG":
        laterality, orientation = _MG_VIEWS[(instance_no - 1) % 2]
        ds.ImageType = ["ORIGINAL", "PRIMARY", ""]
        ds.PresentationIntentType = "FOR PRESENTATION"
        ds.PixelIntensityRelationship, ds.PixelIntensityRelationshipSign = "LOG", 1
        ds.RescaleIntercept, ds.RescaleSlope, ds.RescaleType = 0, 1, "US"
        ds.PresentationLUTShape = "IDENTITY"
        ds.ImagerPixelSpacing = [s["spacing"], s["spacing"]]
        ds.DetectorType = ""
        ds.PositionerType = "MAMMOGRAPHIC"
        ds.ImageLaterality = laterality
        ds.PatientOrientation = orientation
        ds.ViewCodeSequence = Sequence([_code(*_CC_VIEW)])
        ds.AnatomicRegionSequence = Sequence([_code(*_BREAST)])
    elif modality == "US":
        ds.ImageType = ["ORIGINAL", "PRIMARY", ""]
    elif modality == "PT":
        ds.ImageType = ["ORIGINAL", "PRIMARY"]
        ds.SeriesType = ["STATIC", "IMAGE"]
        ds.Units, ds.CountsSource = "CNTS", "EMISSION"
        ds.CorrectedImage, ds.DecayCorrection, ds.DecayFactor = ["DECY"], "START", 1
        ds.NumberOfSlices = n_instances
        ds.ImageIndex = instance_no
        ds.RescaleIntercept, ds.RescaleSlope = 0, 1
        ds.FrameReferenceTime, ds.ActualFrameDuration = 0, 120000
        ds.RadiopharmaceuticalInformationSequence = Sequence([])
    elif modality == "NM":
        ds.ImageType = ["ORIGINAL", "PRIMARY", "STATIC", "EMISSION"]
        ds.NumberOfFrames = 1
        ds.FrameIncrementPointer = [0x00540010, 0x00540020]
        ds.EnergyWindowVector, ds.NumberOfEnergyWindows = [1], 1
        ds.DetectorVector, ds.NumberOfDetectors = [1], 1
        ds.EnergyWindowInformationSequence = Sequence([])
        ds.DetectorInformationSequence = Sequence([])
        ds.RadiopharmaceuticalInformationSequence = Sequence([])
        ds.PatientOrientation = ""
    return ds


# ------------------------------------------------------------------------ build
def series_plan(study):
    """[(series number, instances)] for a synthetic study: one series with the modality's instance count."""
    return [(1, SPECS[study["modality"]]["n"])]


def image_mode(store, source=None):
    """The image source of a build: `source` when given, else $TB_HIS_MOCK_IMAGES, else the store's recorded choice
    (store.meta.image_source, written by build_all(source=...)), else synthetic."""
    mode = source or os.environ.get(IMAGES_ENV) or (store.meta.get("image_source") if hasattr(store, "meta") else None) \
        or "synthetic"
    if mode not in SOURCES:
        raise ValueError(f"image source {mode!r}: choose one of {', '.join(SOURCES)}")
    return mode


def _synthetic_series(store, study, d):
    series = []
    for series_no, n in series_plan(study):
        instances = []
        for k in range(1, n + 1):
            ds = instance_dataset(store, study, series_no, k, n)
            ds.save_as(d / f"{series_no}-{k}.dcm", enforce_file_format=True)
            instances.append({"uid": ds.SOPInstanceUID, "sop_class": ds.SOPClassUID, "number": k})
        series.append({"uid": series_uid(study_key(study), series_no), "number": series_no, "modality": study["modality"],
                       "instances": instances})
    return series


def build_study(store, study, dicom_dir, when=None, source=None, library=None):
    """Write one study's files under dicom_dir/<accession slug>/ (replacing what was there) and update the store study:
    series, counts, path, the Orthanc id and image_source. The study stays `registered` (images exist in the mock, not
    yet in the PACS) until upload_all / upload_study marks it `available`. `when` (ISO) bumps meta.lastUpdated (the desk
    passes its clock; the initial build leaves the clinical time). `source` and `library`: see image_mode and
    PublicLibrary (the desk passes neither: the store's recorded choice and the installed library apply)."""
    d = Path(dicom_dir) / study_dirname(study)
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    series, image_source = None, {"kind": "synthetic"}
    if image_mode(store, source) == "public":
        series, image_source = _public_series(store, study, d, library or PublicLibrary.for_dicom(dicom_dir))
    if series is None:
        series = _synthetic_series(store, study, d)
    patient = store.patients[study["patient_id"]]
    study["status"] = "registered"
    study["uploaded"] = False
    study["number_of_series"] = len(series)
    study["number_of_instances"] = sum(len(s["instances"]) for s in series)
    study["series"] = series
    study["path"] = f"{Path(dicom_dir).name}/{d.name}"
    study["orthanc_id"] = orthanc_study_id(patient["uhid"], study["study_uid"])
    study["image_source"] = image_source
    if when:
        _bump(study, when)
    return study


def performed(store, study):
    """True when the study was acquired: its order is completed (reported). A scheduled study is only booked and has no
    images yet; the reporting desk (1.5) builds them when the report is entered."""
    order = store.orders.get(study["order_id"])
    return bool(order) and order["status"] == "completed" and study.get("status") != "cancelled"


def build_all(store, dicom_dir, source=None, library=None):
    """Build every performed imaging study (order completed); a cancelled or not yet performed study's directory is
    removed. `source` ("public" or "synthetic") is recorded in store.meta.image_source for the studies the desk builds
    later; without it the store's choice applies (synthetic for a fresh store). Returns the number of studies written."""
    if source is not None:
        store.meta["image_source"] = image_mode(store, source)
    dicom_dir = Path(dicom_dir)
    dicom_dir.mkdir(parents=True, exist_ok=True)
    library = library or (PublicLibrary.for_dicom(dicom_dir) if image_mode(store, source) == "public" else None)
    n = 0
    for study in sorted(store.imaging_studies.values(), key=lambda s: s["id"]):
        if not performed(store, study):
            stale = dicom_dir / study_dirname(study)
            if stale.is_dir():
                shutil.rmtree(stale)
            continue
        build_study(store, study, dicom_dir, source=source, library=library)
        n += 1
    return n


def image_counts(store):
    """{"public": n, "synthetic": n, "fallback": [(accession, reason)]} over the studies with images."""
    out = {"public": 0, "synthetic": 0, "fallback": []}
    for s in sorted(store.imaging_studies.values(), key=lambda s: s["id"]):
        if not s.get("series"):
            continue
        src = s.get("image_source") or {"kind": "synthetic"}
        out["public" if src.get("kind") == "public" else "synthetic"] += 1
        if str(src.get("reason") or "").startswith("public series not used"):
            out["fallback"].append((study_key(s), src["reason"]))
    return out


# ------------------------------------------------------------------------ public library images
class PublicLibrary:
    """The public image library of pacs_public: MANIFEST.json (one row per downloaded series, with its raw_dir) under
    `root`, the planned assignment (accession -> source series) and the live picks. Tests pass a tiny synthetic library
    made in a temporary folder; the defaults are the installed library and pacs_public/assignment*.json."""

    def __init__(self, root=None, assignment=None, live=None):
        self.root = Path(root or ui.PUBLIC_LIBRARY)
        self.assignment_path = Path(assignment or PUBLIC_ASSIGNMENT)
        self.live_path = Path(live or LIVE_ASSIGNMENT)
        self._rows = None

    @classmethod
    def for_dicom(cls, dicom_dir):
        """The installed library, with the live picks of the HIMS data directory that holds dicom_dir: the demo HIMS of
        this checkout (data/his_mock) writes pacs_public/assignment_live.json; any other directory (a throw-away copy
        under $TB_HIS_MOCK_DATA, a test build) its own assignment_live.json beside its store."""
        data_dir = Path(dicom_dir).resolve().parent
        demo = (REPO / "data" / "his_mock").resolve()
        return cls(live=LIVE_ASSIGNMENT if data_dir == demo else data_dir / LIVE_NAME)

    @property
    def manifest_path(self):
        return self.root / "MANIFEST.json"

    def available(self):
        return self.manifest_path.is_file()

    def rows(self):
        """{source series UID: manifest row}."""
        if self._rows is None:
            data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            rows = data["series"] if isinstance(data, dict) else data
            self._rows = {r["source_series_uid"]: r for r in rows}
        return self._rows

    @staticmethod
    def _read(path):
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def plan(self):
        return self._read(self.assignment_path)

    def live(self):
        return self._read(self.live_path)

    def save_live(self, data):
        tmp = self.live_path.with_name(self.live_path.name + ".tmp")
        tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(tmp, self.live_path)

    def source_dir(self, row):
        """The extracted (face-checked) series folder of a manifest row: its raw_dir, else root/raw/<collection>/<uid>."""
        d = Path(row.get("raw_dir") or "")
        if row.get("raw_dir") and d.is_dir():
            return d
        return self.root / "raw" / str(row.get("collection")) / str(row["source_series_uid"])


def _relabel_module():
    try:
        from pacs_public import relabel
    except ImportError:          # a checkout without pacs_public: synthetic images
        return None
    return relabel


def _consultant(store, order):
    encounter = store.encounters.get(order.get("encounter_id")) or {}
    cid = encounter.get("consultant_id")
    return store.practitioners.get(cid) if cid else None


def _person(store, patient, relabel):
    """The planner's view of a HIMS patient: sex, age and cancer group (scenarios protocol, else from the orders)."""
    group = relabel.PROTOCOL_GROUP.get(str(relabel._protocols().get(patient.get("uhid")) or "").lower())
    if not group:
        orders = [o for o in store.orders.values() if o.get("patient_id") == patient.get("id")]
        group = relabel._infer_group([o.get("test") or "" for o in orders],
                                     [o["ordering_department"] for o in orders if o.get("ordering_department")])
    return {"sex": patient.get("sex"), "age": patient.get("age"), "group": group}


def _plan_problem(store, study, entry, lib, relabel):
    """Why a planned entry cannot serve this study (the plan was made for another store), or None."""
    order = store.orders.get(study["order_id"]) or {}
    need = relabel.need_key(order.get("test") or "", study.get("modality"))
    roles = {s.get("role") for s in entry.get("series") or []}
    if not need or not any(set(r) <= roles for _, r in relabel.NEEDS[need][1]):
        return "the planned public series do not fit this test (rerun python -I pacs_public/relabel.py --plan)"
    rows = lib.rows()
    missing = [s["source_series_uid"] for s in entry["series"] if s["source_series_uid"] not in rows]
    if missing:
        return f"{len(missing)} planned series are not in the library manifest"
    patient = store.patients[study["patient_id"]]
    person = {"sex": patient.get("sex")}
    source = {"sex": relabel._source_sex(rows[entry["source_series_uid"]])}
    if not relabel._compatible(person, source, need):
        return "the planned source patient's sex does not match this patient"
    return None


def _live_pick(store, study, lib, relabel):
    """An entry for an accession the plan does not know (a study scheduled live at the HIMS desk): an unused source
    series of the right modality and body part (the planner's roles), the same sex rules, never a source patient who
    already serves another HIMS patient (the plan and the live picks of this store), the patient's own source patients
    and cancer group preferred. Deterministic. The choice (public or synthetic) is recorded in assignment_live.json."""
    acc = study_key(study)
    order = store.orders.get(study["order_id"]) or {}
    test = order.get("test") or ""
    patient = store.patients[study["patient_id"]]
    built = store.meta.get("built_at")
    live = lib.live()
    old = live.get(acc)
    if old and old.get("uhid") == patient["uhid"] and old.get("test") == test and old.get("store_built_at") == built:
        return old                                   # the same study again (a rebuild of this store)
    need = relabel.need_key(test, study.get("modality"))
    entry = None
    if need is None:
        reason = "stays synthetic: " + relabel._no_fit_reason(test, study.get("modality"))
    else:
        me = relabel._person_key(patient)
        current = {study_key(s): s for s in store.imaging_studies.values()}

        def holder(a):
            st = current.get(a)
            p = store.patients.get(st["patient_id"]) if st else None
            return relabel._person_key(p) if p else "accession|" + a
        owner, used = {}, set()
        taken = [(a, e) for a, e in lib.plan().items()]
        taken += [(a, e) for a, e in live.items() if a != acc and e.get("store_built_at") == built]
        for a, e in taken:
            if e.get("source_series_uid"):
                owner.setdefault(e.get("source_patient_id"), holder(a))
                used.update(s["source_series_uid"] for s in e.get("series") or [])
        person = _person(store, patient, relabel)
        sources = relabel._sources(list(lib.rows().values()))
        best, fits, fits_sex = None, False, False
        for sid in sorted(sources, key=lambda k: (sources[k]["slot"] or "", k)):
            src = sources[sid]
            if not relabel._best_option(need, src, set()):
                continue
            fits = True
            if not relabel._compatible(person, src, need):
                continue
            fits_sex = True
            if owner.get(sid) not in (None, me):
                continue
            opt = relabel._best_option(need, src, used)
            if not opt:
                continue
            score = (opt[0] + (relabel.GROUP_BONUS if src["group"] and src["group"] == person["group"] else 0)
                     + (1.0 if owner.get(sid) == me else 0.0) - relabel._source_penalty(person, src))
            if best is None or score > best[0] + 1e-9:
                best = (score, sid, opt)
        if best:
            _, sid, (_, src_study, take) = best
            src = sources[sid]
            prim = take[0]
            desc = ", ".join(f"{r['modality']} {r.get('series_description') or r['role']}" for r in take)
            entry = {"collection": prim["collection"], "source_series_uid": prim["source_series_uid"],
                     "source_patient_id": sid, "slot": src["slot"], "source_study_uid": src_study,
                     "reason": f"live pick for {order.get('label') or test}: {desc}; from {src['slot']} "
                               f"{src['collection']}; source {src['sex'] or 'sex not recorded'}",
                     "series": [{"source_series_uid": r["source_series_uid"], "role": r["role"],
                                 "modality": r["modality"], "series_description": r.get("series_description"),
                                 "instances": r.get("instances"), "deface_check": r.get("deface_check")}
                                for r in take]}
        elif not fits:
            reason = f"stays synthetic: no public series in the library fits {order.get('label') or test}"
        elif not fits_sex:
            reason = (f"stays synthetic: no public series that fits {order.get('label') or test} suits a "
                      f"{'female' if patient.get('sex') == 'F' else 'male' if patient.get('sex') == 'M' else ''} "
                      "patient" + (" (mammograms are assigned to women only)" if need == "mammogram" else ""))
        else:
            reason = ("stays synthetic: every public series that fits this test is assigned to another study or "
                      "patient (one source patient never serves two HIMS patients)")
    if entry is None:
        entry = {"collection": None, "source_series_uid": None, "source_patient_id": None, "reason": reason}
    entry.update({"uhid": patient["uhid"], "test": test, "store_built_at": built, "picked_at": store.now()})
    live[acc] = entry
    lib.save_live(live)
    return entry


def _first_frame(src_dir):
    import pydicom
    first = next(iter(sorted(Path(src_dir).glob("*.dcm"))), None)
    if first is None:
        return ""
    return str(pydicom.dcmread(str(first), stop_before_pixels=True, force=True).get("FrameOfReferenceUID", "") or "")


def _public_series(store, study, d, lib):
    """(series, image_source) of a study built from the public library, or (None, {"kind": "synthetic", "reason"}) when it
    stays synthetic. A failure leaves d empty for the synthetic fallback."""
    if not lib.available():
        return None, {"kind": "synthetic", "reason": "public image library not installed"}
    relabel = _relabel_module()
    if relabel is None:
        return None, {"kind": "synthetic", "reason": "pacs_public is not available"}
    acc = study_key(study)
    try:
        plan = lib.plan()
        if acc in plan:
            entry, how = plan[acc], "planned"
            problem = _plan_problem(store, study, entry, lib, relabel) if entry.get("source_series_uid") else None
            if problem:
                LOG.warning("%s: planned public images not used: %s", acc, problem)
                return None, {"kind": "synthetic", "reason": "public series not used: " + problem}
        else:
            entry, how = _live_pick(store, study, lib, relabel), "live"
        if not entry.get("source_series_uid"):
            return None, {"kind": "synthetic", "reason": entry.get("reason") or "no public series assigned"}
        rows = lib.rows()
        patient = store.patients[study["patient_id"]]
        consultant = _consultant(store, store.orders.get(study["order_id"]) or {})
        t0 = study_time(store, study)
        identity = {"name": _person_name(patient["name"]), "uhid": patient["uhid"], "sex": patient.get("sex"),
                    "dob_iso": patient.get("dob_iso"), "age": patient.get("age"), "issuer": INSTITUTION}
        referring = _person_name(consultant["name"], prefix="Dr") if consultant else ""
        uid_map, series, source_uids, hashes = {}, [], [], {}
        for n, s in enumerate(entry["series"], start=1):
            row = rows[s["source_series_uid"]]
            src = lib.source_dir(row)
            frame = _first_frame(src)          # one new frame of reference per source frame (series may differ)
            if frame and frame in uid_map:
                new_frame = uid_map[frame]
            elif frame_of_reference_uid(acc) not in uid_map.values():
                new_frame = frame_of_reference_uid(acc)
            else:
                new_frame = uid_for(acc, "frame-of-reference", n)
            res = relabel.relabel_series(
                src, d, identity, study["study_uid"], lambda k: series_uid(acc, k),
                lambda k, m: instance_uid(acc, k, m), acc, t0.date(), t0.strftime("%H%M%S"), INSTITUTION, referring,
                study.get("description") or "", series_number=n, frame_of_reference_uid=new_frame, uid_map=uid_map)
            source_uids += res["source_uids"]
            hashes.update(res["pixel_sha256"])
            series.append({"uid": res["series_uid"], "number": n, "modality": res["modality"] or study["modality"],
                           "description": s.get("series_description") or "",
                           "instances": [{"uid": u, "sop_class": c, "number": k} for u, c, k in
                                         zip(res["sop_uids"], res["sop_classes"], res["instance_numbers"])]})
        total = sum(len(x["instances"]) for x in series)
        problems = relabel.verify_relabelled(d, {
            "source_patient_id": entry["source_patient_id"], "collection": entry["collection"],
            "source_uids": source_uids, "patient_id": patient["uhid"], "accession": acc,
            "study_uid": study["study_uid"], "instances": total, "pixel_sha256": hashes})
        if problems:
            raise relabel.RelabelError(f"verify found {len(problems)} problems: " + "; ".join(problems[:3]))
    except Exception as exc:   # never fails the build or the desk action: the study keeps synthetic images
        LOG.warning("%s: public images not used, synthetic instead: %s", acc, exc)
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True, exist_ok=True)
        return None, {"kind": "synthetic", "reason": f"public series not used: {type(exc).__name__}: {exc}"[:300]}
    row = rows[entry["source_series_uid"]]
    return series, {"kind": "public", "collection": entry["collection"], "licence": row.get("licence_name"),
                    "licence_url": row.get("licence_url"), "doi": row.get("collection_doi"),
                    "source_series_uid": entry["source_series_uid"],
                    "source_series_uids": [s["source_series_uid"] for s in entry["series"]],
                    "slot": entry.get("slot"), "assignment": how, "verified": True}


# ------------------------------------------------------------------------ Orthanc
def _request(url, data=None, method=None, headers=None, timeout=30):
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
    return json.loads(body) if body.strip() else None


def orthanc_alive(orthanc_url=ORTHANC_URL, timeout=2):
    try:
        return bool(_request(orthanc_url.rstrip("/") + "/system", timeout=timeout))
    except (urllib.error.URLError, OSError, ValueError):
        return False


def study_files(dicom_dir, study=None):
    root = Path(dicom_dir) / study_dirname(study) if study else Path(dicom_dir)
    return sorted(root.rglob("*.dcm"))


def stale_instances(study, orthanc_url=ORTHANC_URL):
    """SOP Instance UIDs Orthanc holds for this study (its Orthanc id) that the store does not list: left by an older
    build of the same accession (synthetic before public, or another source series). Empty when Orthanc has no copy."""
    if not study.get("orthanc_id"):
        return set()
    try:
        held = _request(f"{orthanc_url.rstrip('/')}/studies/{study['orthanc_id']}/instances", timeout=120) or []
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return set()
        raise
    have = {(i.get("MainDicomTags") or {}).get("SOPInstanceUID") for i in held} - {None}
    want = {i["uid"] for se in study.get("series") or [] for i in se.get("instances") or []}
    return have - want


def upload_all(store, dicom_dir, orthanc_url=ORTHANC_URL, studies=None, when=None):
    """POST every .dcm of the built studies (or of `studies`) to <orthanc>/instances. Idempotent: Orthanc keeps one copy
    per SOP Instance UID. A study Orthanc already holds with instances the store does not list (an older build) is
    deleted first, so the PACS shows exactly the built images. A study whose files all went in is marked `available` /
    `uploaded` (meta bumped when `when` is given). Returns {"files", "stored", "already_stored", "failed", "replaced",
    "studies"} (Orthanc study ids)."""
    base = orthanc_url.rstrip("/")
    counts = {"files": 0, "stored": 0, "already_stored": 0, "failed": 0, "replaced": 0, "studies": []}
    seen = set()
    todo = studies if studies is not None else sorted(store.imaging_studies.values(), key=lambda s: s["id"])
    for study in todo:
        if study.get("status") == "cancelled" or not study.get("series"):
            continue
        failed_before = counts["failed"]
        try:
            if stale_instances(study, base):
                delete_study(study["orthanc_id"], base)
                counts["replaced"] += 1
        except (urllib.error.URLError, OSError, ValueError):
            pass                                     # the posts below report an unreachable PACS
        files = study_files(dicom_dir, study)
        for f in files:
            counts["files"] += 1
            try:
                reply = _request(base + "/instances", data=f.read_bytes(), method="POST",
                                 headers={"Content-Type": "application/dicom"})  # urllib sends no Expect
            except (urllib.error.URLError, OSError, ValueError):
                counts["failed"] += 1
                continue
            status = (reply or {}).get("Status")
            if status == "AlreadyStored":
                counts["already_stored"] += 1
            elif status == "Success":
                counts["stored"] += 1
            else:
                counts["failed"] += 1
                continue
            parent = reply.get("ParentStudy")
            if parent and parent not in seen:
                seen.add(parent)
                counts["studies"].append(parent)
        if files and counts["failed"] == failed_before:
            study["status"], study["uploaded"] = "available", True
            if when:
                _bump(study, when)
    return counts


def upload_study(store, dicom_dir, study, orthanc_url=ORTHANC_URL, when=None):
    """Upload one study (the reporting desk, after an imaging report is entered on a scheduled order)."""
    return upload_all(store, dicom_dir, orthanc_url, studies=[study], when=when)


def _qido(params, orthanc_url):
    query = urllib.parse.urlencode(list(params.items()) + [("includefield", "00201208")])
    url = orthanc_url.rstrip("/") + "/dicom-web/studies?" + query
    return _request(url, headers={"Accept": "application/dicom+json"}) or []


def _tag(entry, tag):
    values = (entry.get(tag) or {}).get("Value") or []
    return values[0] if values else None


def find_study(study_uid, orthanc_url=ORTHANC_URL):
    """The QIDO-RS study entry (DICOM JSON) with this Study Instance UID, or None."""
    for e in _qido({"StudyInstanceUID": study_uid}, orthanc_url):
        if _tag(e, "0020000D") == study_uid:
            return e
    return None


def find_by_accession(accession, orthanc_url=ORTHANC_URL):
    """The QIDO-RS study entry with this accession number (0008,0050), or None."""
    for e in _qido({"AccessionNumber": accession}, orthanc_url):
        if _tag(e, "00080050") == accession:
            return e
    return None


def verify(store, orthanc_url=ORTHANC_URL):
    """Problems (empty when fine): every available (uploaded) study is found by Study UID, with the store's accession
    number, the UHID as PatientID and the number of instances."""
    problems = []
    for study in sorted(store.imaging_studies.values(), key=lambda s: s["id"]):
        if study.get("status") != "available":
            continue
        uhid = store.patients[study["patient_id"]]["uhid"]
        try:
            e = find_study(study["study_uid"], orthanc_url)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            problems.append(f"{study['id']}: QIDO failed ({exc})")
            continue
        if not e:
            problems.append(f"{study['id']}: Study UID {study['study_uid']} not found in Orthanc")
            continue
        if _tag(e, "00080050") != study.get("accession"):
            problems.append(f"{study['id']}: accession {_tag(e, '00080050')!r} != {study.get('accession')!r}")
        if _tag(e, "00100020") != uhid:
            problems.append(f"{study['id']}: PatientID {_tag(e, '00100020')!r} != UHID {uhid!r}")
        n = _tag(e, "00201208")
        if n is None or int(n) != study["number_of_instances"]:
            problems.append(f"{study['id']}: {n} instances in Orthanc, {study['number_of_instances']} in the store")
    return problems


def delete_study(orthanc_id, orthanc_url=ORTHANC_URL):
    """DELETE /studies/<id> (tests clean up what they uploaded)."""
    return _request(orthanc_url.rstrip("/") + "/studies/" + orthanc_id, method="DELETE")


# ------------------------------------------------------------------------ CLI
def main(argv=None):
    from .model import Store
    from .paths import layout

    ap = argparse.ArgumentParser(prog="python -m his_mock.dicom_studies", description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--build", action="store_true", help="write the DICOM studies and save the store")
    g.add_argument("--upload", action="store_true", help="upload every available study to Orthanc")
    g.add_argument("--verify", action="store_true", help="check every available study is in Orthanc")
    ap.add_argument("--data", default=None, help="mock data directory (default data/his_mock/ or $TB_HIS_MOCK_DATA)")
    ap.add_argument("--orthanc", default=ORTHANC_URL, help="Orthanc base URL (default %(default)s)")
    ap.add_argument("--images", choices=SOURCES, default=None,
                    help="--build: image source (default: the store's recorded choice, else synthetic)")
    args = ap.parse_args(argv)
    files = layout(args.data)
    if "tumour_board" in str(files["data_dir"]).replace("\\", "/").split("/"):
        ap.error("the mock hospital never touches data/tumour_board/")
    store = Store.load(files["store"])
    if args.build:
        n = build_all(store, files["dicom"], source=args.images)
        store.save(files["store"], files["events"])
        c = image_counts(store)
        print(f"built {n} studies into {files['dicom']}: {c['public']} with public library images, "
              f"{c['synthetic']} synthetic studies")
        for acc, reason in c["fallback"]:
            print(f"  {acc}: {reason}")
        return 0
    if args.upload:
        c = upload_all(store, files["dicom"], args.orthanc)
        store.save(files["store"], files["events"])   # the studies are now available (uploaded)
        print(f"uploaded {c['files']} files: {c['stored']} stored, {c['already_stored']} already stored, "
              f"{c['failed']} failed, {len(c['studies'])} studies ({c['replaced']} older copies replaced)")
        return 1 if c["failed"] else 0
    problems = verify(store, args.orthanc)
    for p in problems:
        print(p)
    n = sum(1 for s in store.imaging_studies.values() if s.get("status") == "available")
    print(f"{n - len({p.split(':')[0] for p in problems})} of {n} studies found in Orthanc with matching accession and counts")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
