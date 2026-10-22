"""Relabel public TCIA series with the synthetic identities of the mock hospital (his_mock), and plan which public series
goes with which HIMS imaging study. Library: importing this module has no side effects.

    from pacs_public import relabel
    rows = relabel.plan_assignment(store_json_path, manifest_path)          # also writes pacs_public/assignment.json
    res = relabel.relabel_series(src_dir, out_dir, identity, study_uid, series_uid_fn, instance_uid_fn, accession,
                                 study_date, study_time, institution, referring, description)
    problems = relabel.verify_relabelled(out_dir, expected)                  # [] when clean

    python -I pacs_public/relabel.py --plan [--store data/his_mock/store.json] [--manifest .../MANIFEST.json]
    python -I pacs_public/relabel.py --check SLOT_OR_SERIES_UID [--out DIR]  # relabel one library series to DIR and verify

UIDs follow his_mock (ids.py, dicom_studies.py): 2.25.<uuid5 as integer> in the namespace
uuid5(NAMESPACE_DNS, "his-mock.vaidyx-demo.invalid"); Study UID = uuid5(accession); series "<acc>|series|<n>"; instance
"<acc>|series|<n>|instance|<m>"; frame of reference "<acc>|frame-of-reference". They are re-implemented here (his_mock is
read only for this package) and a test checks they match.

Scope: the images are for humans to view in the PACS. Nothing here reads pixels for meaning: pixels and geometry are
copied unchanged; only header elements are rewritten. Downloaded files are untrusted data: parsed with pydicom only.
"""
import argparse
import hashlib
import json
import re
import sys
import uuid
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ASSIGNMENT = HERE / "assignment.json"
DEFAULT_STORE = HERE.parent / "data" / "his_mock" / "store.json"
DEFAULT_MANIFEST = Path("/data/vaidyx/tb_resources/dicom_public/MANIFEST.json")
SCENARIOS = HERE.parent / "his_mock" / "scenarios.json"

UID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "his-mock.vaidyx-demo.invalid")   # = his_mock.ids.STUDY_UID_NAMESPACE
IMAGE_COMMENTS = ("Public de-identified research image from TCIA, relabelled for demonstration; "
                  "see PACS about page")
DEID_NOTE = "Vaidyx demo relabel: identity, dates, UIDs replaced"     # LO, at most 64 characters
EXPLICIT_VR_LE = "1.2.840.10008.1.2.1"
STANDARD_UID_ROOT = "1.2.840.10008."


class RelabelError(Exception):
    """A series that cannot be relabelled (for example compressed pixels with no decoder): keep it synthetic."""


# ------------------------------------------------------------------------ identifiers (his_mock conventions)
def uid_for(*parts):
    """2.25.<uuid5 as integer> of "|"-joined parts (his_mock.dicom_studies.uid_for)."""
    return "2.25." + str(uuid.uuid5(UID_NAMESPACE, "|".join(str(p) for p in parts)).int)


def study_uid(accession):
    """his_mock.ids.study_uid: the Study UID of an accession."""
    return "2.25." + str(uuid.uuid5(UID_NAMESPACE, str(accession)).int)


def series_uid(accession, series_no):
    return uid_for(accession, "series", series_no)


def instance_uid(accession, series_no, instance_no):
    return uid_for(accession, "series", series_no, "instance", instance_no)


def frame_of_reference_uid(accession):
    return uid_for(accession, "frame-of-reference")


def series_uid_fn_for(accession):
    """series_uid_fn for relabel_series: series number -> UID."""
    return lambda series_no: series_uid(accession, series_no)


def instance_uid_fn_for(accession):
    """instance_uid_fn for relabel_series: (series number, instance number) -> UID."""
    return lambda series_no, instance_no: instance_uid(accession, series_no, instance_no)


def slug(value):
    """his_mock.ids.slug: RAD/26/00981 -> rad-26-00981 (the dicom/<accession slug>/ folder)."""
    return re.sub(r"[/\s]+", "-", str(value).strip()).lower()


def person_name(name, prefix=None):
    """his_mock.dicom_studies._person_name: 'Venkatesh Rao (SYNTHETIC)' -> 'Rao (SYNTHETIC)^Venkatesh';
    'Dr Arvind Menon' with prefix 'Dr' -> 'Menon^Arvind^^Dr'. A value that already holds '^' is kept."""
    if name and "^" in str(name):
        return str(name)
    text = str(name or "").replace("(SYNTHETIC)", " ").strip()
    if prefix and text.startswith(prefix + " "):
        text = text[len(prefix) + 1:]
    words = text.split()
    family = words[-1] if words else ""
    given = " ".join(words[:-1])
    if "(SYNTHETIC)" in str(name or ""):
        family = (family + " (SYNTHETIC)").strip()
    pn = f"{family}^{given}" if given else family
    if prefix:
        pn = f"{family}^{given}^^{prefix}"
    return pn


# ------------------------------------------------------------------------ dates and times
def _as_date(v):
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip().replace("-", "")
    return date(int(s[:4]), int(s[4:6]), int(s[6:8]))


def _as_time(v):
    if isinstance(v, datetime):
        return v.time()
    if isinstance(v, time):
        return v
    s = str(v or "").strip().replace(":", "")
    if not s:
        return time(0, 0)
    whole, _, frac = s.partition(".")
    whole = (whole + "000000")[:6]
    us = int((frac + "000000")[:6]) if frac else 0
    return time(int(whole[:2]), int(whole[2:4]), int(whole[4:6]), us)


def _parse_da(s):
    s = str(s or "").strip().replace(".", "").replace("-", "")
    if len(s) < 8 or not s[:8].isdigit():
        return None
    try:
        return date(int(s[:4]), int(s[4:6]), int(s[6:8]))
    except ValueError:
        return None


def _parse_tm(s):
    s = str(s or "").strip().replace(":", "")
    if not s or not s.split(".")[0].isdigit():
        return None
    try:
        return _as_time(s)
    except ValueError:
        return None


def _fmt_tm(t, like):
    s = t.strftime("%H%M%S")
    if "." in str(like):
        digits = len(str(like).split(".", 1)[1]) or 6
        s += "." + f"{t.microsecond:06d}"[:min(6, digits)]
    return s


def _shift_dt_string(s, delta):
    """DT 'YYYYMMDDHHMMSS.FFFFFF&ZZXX' (any precision) shifted by delta, same precision, offset kept."""
    s = str(s or "").strip()
    m = re.match(r"^(\d{4,14})(\.\d{1,6})?([+-]\d{4})?$", s)
    if not m:
        return None
    digits, frac, off = m.group(1), m.group(2) or "", m.group(3) or ""
    full = (digits + "0101000000"[len(digits) - 4:])[:14] if len(digits) < 14 else digits
    try:
        dt = datetime.strptime(full, "%Y%m%d%H%M%S")
    except ValueError:
        return None
    if frac:
        dt = dt.replace(microsecond=int((frac[1:] + "000000")[:6]))
    dt = dt + delta
    out = dt.strftime("%Y%m%d%H%M%S")[:len(digits)]
    if frac:
        out += "." + f"{dt.microsecond:06d}"[:len(frac) - 1]
    return out + off


def _source_datetime(ds):
    for dk, tk in (("StudyDate", "StudyTime"), ("SeriesDate", "SeriesTime"), ("AcquisitionDate", "AcquisitionTime"),
                   ("ContentDate", "ContentTime")):
        d = _parse_da(ds.get(dk, ""))
        if d:
            return datetime.combine(d, _parse_tm(ds.get(tk, "")) or time(0, 0))
    return None


def _shift_dates(ds, delta, base_date, skip=("PatientBirthDate", "PatientBirthTime")):
    """Shift every DA, TM and DT element (sequences included) by delta. A ...Date / ...Time pair moves together; a lone
    time is read on base_date; a lone date is read at noon."""
    tags = list(ds.keys())
    paired = set()
    for tag in tags:
        el = ds[tag]
        kw = el.keyword or ""
        if el.VR != "DA" or kw in skip or not kw.endswith("Date"):
            continue
        tkw = kw[:-4] + "Time"
        if tkw in ds and ds[tkw].VR == "TM":
            d, t = _parse_da(el.value), _parse_tm(ds[tkw].value)
            if d is None:
                continue
            new = datetime.combine(d, t or time(12, 0)) + delta
            el.value = new.strftime("%Y%m%d")
            if t is not None:
                ds[tkw].value = _fmt_tm(new.time(), ds[tkw].value)
            paired.update({kw, tkw})
    for tag in tags:
        if tag not in ds:
            continue
        el = ds[tag]
        kw = el.keyword or ""
        if el.VR == "SQ":
            for item in el.value:
                _shift_dates(item, delta, base_date, skip)
            continue
        if kw in skip or kw in paired or el.value in (None, ""):
            continue
        values = list(el.value) if el.VM > 1 else [el.value]
        out = []
        for v in values:
            if el.VR == "DA":
                d = _parse_da(v)
                out.append((datetime.combine(d, time(12, 0)) + delta).strftime("%Y%m%d") if d else "")
            elif el.VR == "TM":
                t = _parse_tm(v)
                out.append(_fmt_tm((datetime.combine(base_date, t) + delta).time(), v) if t else "")
            elif el.VR == "DT":
                out.append(_shift_dt_string(v, delta) or "")
            else:
                out = None
                break
        if out is not None:
            el.value = out if el.VM > 1 else out[0]


# ------------------------------------------------------------------------ what is removed or blanked
PATIENT_KEEP = {0x00100010, 0x00100020, 0x00100021, 0x00100030, 0x00100040, 0x00101010, 0x00101020, 0x00101030}
TRIAL_KEEP = {0x00120062, 0x00120063, 0x00120064}          # PatientIdentityRemoved, DeidentificationMethod (+ codes)
REMOVE_KEYWORDS = {
    "RequestAttributesSequence", "ReferencedPatientSequence", "ReferencedStudySequence",
    "ReferencedPerformedProcedureStepSequence", "IssuerOfAccessionNumberSequence", "RequestedProcedureID",
    "ScheduledProcedureStepID", "PerformedProcedureStepID", "StudyComments", "RequestingService",
    "ImplementationVersionName", "InstitutionCodeSequence", "InstitutionalDepartmentTypeCodeSequence",
    "ReferringPhysicianIdentificationSequence", "PerformingPhysicianIdentificationSequence",
    "OperatorIdentificationSequence", "PhysiciansOfRecordIdentificationSequence",
    "PhysiciansReadingStudyIdentificationSequence", "ConsultingPhysicianIdentificationSequence",
    "ReferringPhysicianAddress", "ReferringPhysicianTelephoneNumbers", "PersonAddress", "PersonTelephoneNumbers",
    "StorageMediaFileSetUID", "StorageMediaFileSetID", "PerformedLocation", "TimezoneOffsetFromUTC",
}
# The source site's request, reason and procedure texts and codes: clinical history of another person (for example
# "79 yr old f recently diagnosed rectal mass") or the source hospital's own order codes. They never appear under a
# HIMS patient; the HIMS study carries its own test label as StudyDescription.
CLINICAL_TEXT_KEYWORDS = {
    "ReasonForStudy", "RequestedProcedureDescription", "RequestedProcedureCodeSequence",
    "PerformedProcedureStepDescription", "ReasonForTheRequestedProcedure", "ReasonForRequestedProcedureCodeSequence",
    "RequestedProcedureComments", "CommentsOnThePerformedProcedureStep", "AdmittingDiagnosesDescription",
    "AdmittingDiagnosesCodeSequence", "ImagingServiceRequestComments", "ProcedureCodeSequence",
    "PerformedProcedureCodeSequence", "ReasonForPerformedProcedureCodeSequence", "RequestingPhysician",
}
REMOVE_KEYWORDS |= CLINICAL_TEXT_KEYWORDS
BLANK_KEYWORDS = {"InstitutionName", "InstitutionAddress", "InstitutionalDepartmentName", "StationName",
                  "DeviceSerialNumber", "PerformedStationName", "ScheduledStationName", "ScheduledStationAETitle",
                  "PerformedStationAETitle", "SourceApplicationEntityTitle"}
TEXT_VRS = {"AE", "AS", "CS", "DA", "DS", "DT", "IS", "LO", "LT", "PN", "SH", "ST", "TM", "UC", "UI", "UR", "UT"}


def _tag_label(el):
    return f"({el.tag.group:04X},{el.tag.element:04X}) {el.keyword or 'private'}"


def _strip(ds, removed, top=True):
    """Remove private, overlay / curve, patient (0010 not kept), clinical trial (0012), visit (0038) and request
    elements, recursively; blank institution and station names in nested items. Returns nothing; fills `removed`."""
    for tag in list(ds.keys()):
        el = ds[tag]
        g = el.tag.group
        drop = (el.tag.is_private or 0x5000 <= g <= 0x50FF or (0x6000 <= g <= 0x60FF and g % 2 == 0)
                or (g == 0x0010 and (not top or int(el.tag) not in PATIENT_KEEP))
                or (g == 0x0012 and int(el.tag) not in TRIAL_KEEP) or g == 0x0038
                or (el.keyword in REMOVE_KEYWORDS))
        if drop:
            removed.add(_tag_label(el))
            del ds[tag]
            continue
        if el.VR == "SQ":
            for item in el.value:
                _strip(item, removed, top=False)
        elif el.keyword in BLANK_KEYWORDS and el.value not in (None, ""):
            el.value = ""
        elif el.VR == "PN" and not (top and el.keyword in ("PatientName", "ReferringPhysicianName")):
            if el.value not in (None, ""):
                el.value = ""


def _map_uids(ds, uid_map, study_uid_value, keep):
    """Replace every non-standard UID (sequences included) by its mapped value, or by a deterministic new UID derived
    from the study UID. Standard DICOM UIDs (1.2.840.10008.*) and the new UIDs in `keep` stay."""
    for tag in list(ds.keys()):
        el = ds[tag]
        if el.VR == "SQ":
            for item in el.value:
                _map_uids(item, uid_map, study_uid_value, keep)
            continue
        if el.VR != "UI" or el.value in (None, ""):
            continue
        values = list(el.value) if el.VM > 1 else [el.value]
        new = []
        for v in values:
            v = str(v)
            if v.startswith(STANDARD_UID_ROOT) or v in keep:
                new.append(v)
            else:
                if v not in uid_map:
                    uid_map[v] = uid_for(study_uid_value, "uid", v)
                    keep.add(uid_map[v])
                new.append(uid_map[v])
        el.value = new if el.VM > 1 else new[0]


def _birth_date(identity, on):
    if identity.get("dob_iso"):
        return _as_date(identity["dob_iso"])
    if identity.get("age") is not None:     # born the day after `on`, age + 1 years earlier: exactly `age` on `on`
        age = int(identity["age"])
        try:
            return date(on.year - age - 1, on.month, on.day) + timedelta(days=1)
        except ValueError:                      # 29 February
            return date(on.year - age - 1, 3, 1)
    return None


def _age_string(birth, on):
    if not birth:
        return ""
    years = on.year - birth.year - ((on.month, on.day) < (birth.month, birth.day))
    return f"{years:03d}Y"


def _pixel_sha(ds):
    data = ds.get("PixelData")          # keyword access gives the bytes
    return hashlib.sha256(bytes(data)).hexdigest() if data is not None else ""


# ------------------------------------------------------------------------ relabel one series
def relabel_series(src_dir, out_dir, identity, study_uid, series_uid_fn, instance_uid_fn, accession, study_date,
                   study_time, institution, referring, description, *, series_number=1, institution_address="",
                   frame_of_reference_uid=None, uid_map=None):
    """Copy one public series (src_dir/*.dcm) to out_dir/<series_number>-<instance>.dcm with the HIMS identity.

    identity: {"name": "Venkatesh Rao (SYNTHETIC)" or a DICOM PN, "uhid": PatientID, "sex": "M"/"F",
               "dob_iso" or "age", optional "issuer" (default: institution), optional "weight_kg"}.
    series_uid_fn(series_number) and instance_uid_fn(series_number, instance_number) give the new UIDs (his_mock:
    series_uid_fn_for(accession), instance_uid_fn_for(accession)). Instance numbers are the source ones (cropped series
    keep their gaps; they are renumbered 1..n only when the source numbers repeat). Dates and times move by one offset
    so the earliest StudyDate / StudyTime become study_date / study_time and intervals inside the series stay true
    (PET decay times included). The frame of reference is frame_of_reference_uid or the accession's (his_mock rule).
    uid_map (shared across the series of one study, optional) maps source UIDs to new ones.

    Returns {files, instances, series_uid, removed_tags, instance_numbers, sop_uids, sop_classes, modality,
    frame_of_reference_uid, source_series_uid, source_uids, pixel_sha256, renumbered}. Raises RelabelError when the pixels cannot be written uncompressed."""
    import pydicom
    from pydicom.uid import PYDICOM_IMPLEMENTATION_UID, UID, ExplicitVRLittleEndian

    src_dir, out_dir = Path(src_dir), Path(out_dir)
    paths = sorted(p for p in src_dir.glob("*.dcm") if p.is_file())
    if not paths:
        raise RelabelError(f"no DICOM files in {src_dir}")
    heads = []
    for p in paths:
        h = pydicom.dcmread(str(p), stop_before_pixels=True, force=True)
        heads.append((p, h))
    nums = [int(h.get("InstanceNumber", 0) or 0) for _, h in heads]
    renumber = len(set(nums)) != len(nums) or 0 in nums
    if renumber:   # position order, then the source number
        def _pos(h):
            try:
                return -float(h.ImagePositionPatient[2])
            except (AttributeError, TypeError, ValueError, IndexError):
                return 0.0
        heads.sort(key=lambda t: (_pos(t[1]), int(t[1].get("InstanceNumber", 0) or 0), t[0].name))
    first = heads[0][1]
    src_series = str(first.get("SeriesInstanceUID", ""))
    src_study = str(first.get("StudyInstanceUID", ""))
    src_for = str(first.get("FrameOfReferenceUID", ""))
    new_series = series_uid_fn(series_number)
    new_for = frame_of_reference_uid or frame_of_reference_uid_for(accession)
    uid_map = {} if uid_map is None else uid_map
    uid_map.update({src_series: new_series})
    if src_study:
        uid_map[src_study] = study_uid
    for _, h in heads:
        f = str(h.get("FrameOfReferenceUID", ""))
        if f:
            uid_map.setdefault(f, new_for if f == src_for else uid_for(study_uid, "frame-of-reference", f))
    plan = []
    for k, (p, h) in enumerate(heads, start=1):
        n = k if renumber else int(h.InstanceNumber)
        new_sop = instance_uid_fn(series_number, n)
        uid_map[str(h.SOPInstanceUID)] = new_sop
        plan.append((p, n, new_sop))

    new_date = _as_date(study_date)
    new_time = _as_time(study_time)
    src_dt = _source_datetime(first)
    new_dt = datetime.combine(new_date, new_time)
    delta = (new_dt - src_dt) if src_dt else None
    base_date = src_dt.date() if src_dt else new_date
    birth = _birth_date(identity, new_date)
    keep = set(uid_map.values()) | {study_uid, new_series, new_for}
    out_dir.mkdir(parents=True, exist_ok=True)
    removed, files, sops, numbers, hashes, source_uids, classes = set(), [], [], [], {}, set(), []

    for p, n, new_sop in plan:
        ds = pydicom.dcmread(str(p), force=True)
        source_uids.update(str(v) for v in (ds.get("SOPInstanceUID"), ds.get("SeriesInstanceUID"),
                                            ds.get("StudyInstanceUID"), ds.get("FrameOfReferenceUID")) if v)
        ts = getattr(ds.file_meta, "TransferSyntaxUID", None)
        if ts is not None and UID(ts).is_compressed:
            try:
                ds.decompress()
            except Exception as exc:  # no decoder installed, or a broken stream
                raise RelabelError(f"{p.name}: compressed pixels ({ts}) cannot be decoded: {exc}") from exc
        sha = _pixel_sha(ds)
        _strip(ds, removed)
        if delta is not None:
            _shift_dates(ds, delta, base_date)

        # patient
        ds.PatientName = person_name(identity.get("name"))
        ds.PatientID = identity["uhid"]
        ds.IssuerOfPatientID = identity.get("issuer") or institution
        ds.PatientBirthDate = birth.strftime("%Y%m%d") if birth else ""
        ds.PatientSex = identity.get("sex") or ""
        ds.PatientAge = _age_string(birth, new_date)
        if identity.get("weight_kg"):
            ds.PatientWeight = str(round(float(identity["weight_kg"]), 1))
        elif "PatientWeight" in ds:
            if str(ds.get("Modality", "")) == "PT" and ds.PatientWeight not in (None, ""):
                ds.PatientWeight = str(round(float(ds.PatientWeight)))      # kept (rounded) for SUV display
            else:
                removed.add("(0010,1030) PatientWeight")
                del ds.PatientWeight
        if "PatientSize" in ds and not identity.get("height_m"):
            removed.add("(0010,1020) PatientSize")
            del ds.PatientSize
        elif identity.get("height_m"):
            ds.PatientSize = str(round(float(identity["height_m"]), 2))
        ds.PatientIdentityRemoved = "YES"
        old = ds.get("DeidentificationMethod")
        values = [str(v) for v in (list(old) if old is not None and not isinstance(old, str) else [old]) if v]
        if DEID_NOTE not in values:
            values.append(DEID_NOTE)
        ds.DeidentificationMethod = values if len(values) > 1 else values[0]

        # study, series, instance
        ds.StudyInstanceUID = study_uid
        ds.StudyDate, ds.StudyTime = new_date.strftime("%Y%m%d"), new_time.strftime("%H%M%S")
        if delta is None:
            for dk, tk in (("SeriesDate", "SeriesTime"), ("ContentDate", "ContentTime"),
                           ("AcquisitionDate", "AcquisitionTime")):
                setattr(ds, dk, ds.StudyDate)
                setattr(ds, tk, ds.StudyTime)
        ds.AccessionNumber = accession or ""
        ds.StudyID = "".join(c for c in str(accession or "") if c.isdigit())[-16:]
        ds.StudyDescription = description or ""
        ds.ReferringPhysicianName = person_name(referring, prefix="Dr" if str(referring or "").startswith("Dr ")
                                                else None) if referring else ""
        ds.InstitutionName = institution or ""
        ds.InstitutionAddress = institution_address or ""
        for kw in ("PerformingPhysicianName", "OperatorsName", "StationName", "DeviceSerialNumber"):
            setattr(ds, kw, "")
        ds.SeriesInstanceUID = new_series
        ds.SeriesNumber = series_number
        ds.SOPInstanceUID = new_sop
        ds.InstanceNumber = n
        if "FrameOfReferenceUID" in ds or str(ds.get("Modality", "")) in ("CT", "MR", "PT"):
            ds.FrameOfReferenceUID = uid_map.get(str(ds.get("FrameOfReferenceUID", "")), new_for)
        ds.ImageComments = IMAGE_COMMENTS
        _map_uids(ds, uid_map, study_uid, keep)

        # file meta: Explicit VR Little Endian, our implementation class
        ds.file_meta.MediaStorageSOPClassUID = ds.SOPClassUID
        ds.file_meta.MediaStorageSOPInstanceUID = new_sop
        ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
        ds.file_meta.ImplementationClassUID = PYDICOM_IMPLEMENTATION_UID
        if "ImplementationVersionName" in ds.file_meta:
            del ds.file_meta.ImplementationVersionName
        if "SourceApplicationEntityTitle" in ds.file_meta:
            del ds.file_meta.SourceApplicationEntityTitle
        out = out_dir / f"{series_number}-{n}.dcm"
        ds.save_as(out, implicit_vr=False, little_endian=True, enforce_file_format=True)
        files.append(str(out))
        sops.append(new_sop)
        classes.append(str(ds.SOPClassUID))
        numbers.append(n)
        hashes[new_sop] = sha
    return {"files": files, "instances": len(files), "series_uid": new_series, "removed_tags": sorted(removed),
            "instance_numbers": numbers, "sop_uids": sops, "sop_classes": classes,
            "modality": str(first.get("Modality", "")),
            "frame_of_reference_uid": new_for, "source_series_uid": src_series, "source_uids": sorted(source_uids),
            "pixel_sha256": hashes, "renumbered": renumber}


def frame_of_reference_uid_for(accession):
    return frame_of_reference_uid(accession)


# ------------------------------------------------------------------------ verify
def _walk_strings(ds, path=""):
    """Yield (path, keyword, VR, text) for every text-like element, sequences and file meta included."""
    meta = getattr(ds, "file_meta", None)
    if meta is not None and path == "":
        for el in meta:
            if el.VR in TEXT_VRS and el.value not in (None, ""):
                yield "meta>" + (el.keyword or str(el.tag)), el.keyword, el.VR, str(el.value)
    for el in ds:
        if el.VR == "SQ":
            for i, item in enumerate(el.value):
                yield from _walk_strings(item, f"{path}{el.keyword or el.tag}[{i}]>")
        elif el.VR in TEXT_VRS and el.value not in (None, ""):
            values = list(el.value) if el.VM > 1 else [el.value]
            for v in values:
                yield path + (el.keyword or str(el.tag)), el.keyword, el.VR, str(v)


def verify_relabelled(out_dir, expected):
    """Problems (empty list when clean) of a relabelled series folder.

    expected: {"source_patient_id", "collection", "source_uids": [original Study / Series / SOP / frame UIDs],
               optional "patient_id", "accession", "study_uid", "instances", "pixel_sha256": {new SOP UID: sha256},
               optional "forbidden": [other strings that must not appear]}.
    Checks every string element (sequences and file meta included): no source PatientID, no collection name, no
    original UID; no private tag; no patient element beyond the rewritten ones; no element the relabeller removes (the
    source's request and reason texts among them); no date before 2020 except the birth date; Explicit VR Little Endian;
    the expected identity, accession and Study UID; the provenance comment; pixel data unchanged when hashes are given."""
    import pydicom
    problems = []
    files = sorted(Path(out_dir).glob("*.dcm"))
    if expected.get("instances") is not None and len(files) != int(expected["instances"]):
        problems.append(f"{len(files)} files, expected {expected['instances']}")
    src_pid = str(expected.get("source_patient_id") or "")
    collection = str(expected.get("collection") or "")
    names = {collection.lower(), collection.lower().replace(" ", "_"), collection.lower().replace(" ", "-"),
             collection.lower().replace("_", " ")} - {""}
    src_uids = {str(u) for u in expected.get("source_uids") or [] if u}
    forbidden = [str(f) for f in expected.get("forbidden") or [] if f]
    hashes = expected.get("pixel_sha256") or {}
    for f in files:
        ds = pydicom.dcmread(str(f), force=True)
        where = f.name
        if str(ds.file_meta.get("TransferSyntaxUID", "")) != EXPLICIT_VR_LE:
            problems.append(f"{where}: transfer syntax {ds.file_meta.get('TransferSyntaxUID')}")
        for el in ds.iterall():
            if el.tag.is_private:
                problems.append(f"{where}: private tag {el.tag}")
            elif el.tag.group == 0x0010 and int(el.tag) not in PATIENT_KEEP:
                problems.append(f"{where}: patient element {_tag_label(el)} left")
            elif el.keyword in REMOVE_KEYWORDS:
                problems.append(f"{where}: {_tag_label(el)} should have been removed")
        for path, kw, vr, text in _walk_strings(ds):
            low = text.lower()
            if src_pid and src_pid in text:
                problems.append(f"{where}: {path} holds the source PatientID")
            if any(n in low for n in names):
                problems.append(f"{where}: {path} holds the collection name")
            if vr == "UI" and text in src_uids:
                problems.append(f"{where}: {path} keeps an original UID")
            elif src_uids and vr != "UI" and any(u in text for u in src_uids):
                problems.append(f"{where}: {path} holds an original UID in text")
            for s in forbidden:
                if s in text:
                    problems.append(f"{where}: {path} holds {s!r}")
            if vr == "DA" and kw != "PatientBirthDate":
                d = _parse_da(text)
                if d and d.year < 2020:
                    problems.append(f"{where}: {path} date {text} is before 2020")
        for key, kw in (("patient_id", "PatientID"), ("accession", "AccessionNumber"), ("study_uid", "StudyInstanceUID")):
            if expected.get(key) is not None and str(ds.get(kw, "")) != str(expected[key]):
                problems.append(f"{where}: {kw} {ds.get(kw)!r} != {expected[key]!r}")
        if str(ds.get("ImageComments", "")) != IMAGE_COMMENTS:
            problems.append(f"{where}: ImageComments is not the provenance note")
        sop = str(ds.get("SOPInstanceUID", ""))
        if hashes and sop in hashes and _pixel_sha(ds) != hashes[sop]:
            problems.append(f"{where}: pixel data changed")
    return problems


# ------------------------------------------------------------------------ assignment planner
# Need of each HIMS test key: (label, alternatives). An alternative is a list of roles that must all come from one
# source study (score, roles). Every series of the chosen roles in that study goes into the HIMS study.
CAP = [(10, ["ct_cap_contrast"]), (9, ["ct_cap"]), (9, ["ct_chest", "ct_ap"]), (6, ["ct_chest"]),
       (5, ["ct_cap_petct"])]
NEEDS = {
    "mammogram": ("mammogram", [(10, ["mg"])]),
    "cect_chest_abdomen_pelvis": ("CT chest to pelvis", CAP),
    "cect_tap": ("CT thorax to pelvis", CAP),
    "cect_abdomen_pelvis": ("CT abdomen and pelvis", [(10, ["ct_ap"]), (6, ["ct_cap_contrast"]), (6, ["ct_cap"]),
                                                       (4, ["ct_cap_petct"])]),
    "cect_face_neck": ("CT face and neck", [(10, ["ct_neck"]), (7, ["ct_neck_lower"])]),
    "chest_xray": ("chest radiograph", [(10, ["cr_chest"])]),
    "mri_pelvis": ("MRI pelvis", [(10, ["mr_pelvis"])]),
    "mri_pelvis_rectum": ("MRI pelvis, rectal protocol", [(10, ["mr_rectum"])]),
    "pet_ct": ("whole-body PET-CT", [(12, ["pt_wb", "ct_cap_petct"]), (11, ["pt_wb", "ct_cap_contrast"]),
                                     (11, ["pt_wb", "ct_cap"]), (6, ["pt_wb"])]),
}
COMPANIONS = {"ct_ap": ["ct_ap_coronal"], "ct_neck": ["ct_neck_coronal"]}
NO_FIT = {
    "US": "no ultrasound series in the public library",
    "NM": "no nuclear medicine (bone scan) series in the public library",
    "mri_brain": "no brain MRI in the public library",
    "mri_oral_cavity_neck": "no head and neck MRI in the public library (TCIA head and neck images are under "
                            "controlled access)",
}
# Order inside one HIMS patient: the needs with the fewest sources first.
NEED_ORDER = ["pet_ct", "mammogram", "mri_pelvis_rectum", "mri_pelvis", "cect_face_neck", "chest_xray",
              "cect_abdomen_pelvis", "cect_chest_abdomen_pelvis", "cect_tap"]
GROUP_OF_LETTER = {"A": "breast", "B": "lung", "C": "cervix", "D": "colorectal", "E": "head_neck", "F": "cup",
                   "G": None}
PROTOCOL_GROUP = {"breast": "breast", "oral_cavity": "head_neck", "head_neck": "head_neck", "cervix": "cervix",
                  "lung_nsclc": "lung", "lung": "lung", "colorectal_rectum": "colorectal", "colorectal": "colorectal",
                  "cup": "cup"}
FEMALE_COLLECTIONS = {"CMMD", "TCGA-BRCA", "CMB-BRCA", "TCGA-CESC", "CC-Tumor-Heterogeneity"}
GROUP_BONUS = 4


def load_manifest_rows(path):
    """MANIFEST.json -> its series rows (manifest.load_manifest without importing it)."""
    data = json.loads(Path(path).read_text())
    return data["series"] if isinstance(data, dict) else data


def need_key(test, modality):
    if test in NEEDS:
        return test
    if str(test).startswith("cect_chest"):
        return "cect_chest_abdomen_pelvis"
    if str(test).startswith("mri_pelvis"):
        return "mri_pelvis"
    return None


def _no_fit_reason(test, modality):
    return NO_FIT.get(test) or NO_FIT.get(modality) or f"no public series fits {test} ({modality})"


def _source_sex(row):
    s = (row.get("source_sex") or "").strip().upper()
    if s in ("F", "M"):
        return s
    if row.get("collection") in FEMALE_COLLECTIONS:
        return "F"
    return None


def _age(text):
    m = re.match(r"^(\d{1,3})Y$", str(text or "").strip())
    return int(m.group(1)) if m and int(m.group(1)) > 0 else None     # CMB series carry 000Y: not recorded


def eligible(row):
    """A manifest row the planner may use: downloaded, face check done, text check passed, no burned-in text."""
    deface = str(row.get("deface_check") or "")
    return (row.get("status") == "downloaded" and int(row.get("instances") or 0) > 0
            and (deface == "clear" or deface.startswith("cropped:")) and row.get("text_check") == "pass"
            and row.get("burned_in") != "yes" and row.get("role") not in (None, "", "unclassified"))


def _sources(manifest_rows):
    """{source patient id: {"sex", "age", "group", "slot", "collection", "studies": {study uid: [rows]}}}."""
    out = {}
    for r in manifest_rows:
        if not eligible(r):
            continue
        s = out.setdefault(r["source_patient_id"], {
            "sex": _source_sex(r), "age": _age(r.get("source_age")), "slot": r.get("slot"),
            "collection": r["collection"], "group": GROUP_OF_LETTER.get(str(r.get("group") or " ")[0]),
            "stand_in": bool(r.get("stand_in")), "studies": {}})
        s["studies"].setdefault(r["source_study_uid"], []).append(r)
    return out


def _protocols():
    try:
        data = json.loads(SCENARIOS.read_text())
        return {p["uhid"]: p.get("protocol") for p in data.get("patients", []) if p.get("uhid")}
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def _infer_group(tests, departments):
    t, d = set(tests), set(departments)
    if "mri_pelvis_rectum" in t or d & {"Colorectal Surgery", "Gastrointestinal Surgery"}:
        return "colorectal"
    if t & {"mammogram", "usg_breast_axilla"} or "Breast Surgery" in d:
        return "breast"
    if t & {"cect_face_neck", "mri_oral_cavity_neck"} or "ENT / Head and Neck Surgery" in d:
        return "head_neck"
    if "mri_pelvis" in t or "Gynaecologic Oncology" in d:
        return "cervix"
    if "pet_ct" in t or d & {"Pulmonology", "Medical Oncology"}:
        return "lung"
    return None


def _best_option(need, source, used):
    """(score, study uid, [rows]) of the best alternative a source patient still offers for a need, or None."""
    best = None
    for score, roles in NEEDS[need][1]:
        for study, rows in sorted(source["studies"].items()):
            free = [r for r in rows if r["source_series_uid"] not in used]
            if all(any(r["role"] == role for r in free) for role in roles):
                take = [r for r in free if r["role"] in roles]
                for role in roles:
                    take += [r for r in free if r["role"] in COMPANIONS.get(role, [])]
                cand = (score, study, sorted(take, key=lambda r: (roles.index(r["role"]) if r["role"] in roles
                                                                    else 99, r.get("series_description") or "")))
                if best is None or cand[0] > best[0]:
                    best = cand
        if best:
            return best
    return best


def _compatible(person, source, need):
    psex, ssex = person["sex"], source["sex"]
    if need == "mammogram" and (psex != "F" or ssex == "M"):
        return False
    return not (psex in ("F", "M") and ssex in ("F", "M") and psex != ssex)


COVER = 100.0          # a study with public images is worth more than any quality difference
EXTRA_SOURCE = 3.0     # each extra source patient for one person (different bodies) costs a little


def _source_penalty(person, source):
    pen = 0.0 if source["sex"] else 1.0
    if person["age"] is not None and source["age"] is not None:
        pen += abs(person["age"] - source["age"]) / 20.0
    else:
        pen += 0.5
    return pen


def _person_value(person, sids, sources):
    """(value, picks, used source ids) of the best use of the source patients `sids` for one person's open studies:
    every need takes the best alternative any of its sources still offers (series never reused); needs are tried in
    every order (a person has a handful)."""
    from itertools import permutations
    needs = person["need_idx"]
    if not sids or not needs:
        return 0.0, {}, set()
    sids = sorted(sids, key=lambda s: sources[s]["slot"] or s)
    orders = permutations(needs) if len(needs) <= 5 else [tuple(needs)]
    best = (0.0, {}, set())
    for order in orders:
        used, picks, total, taken = set(), {}, 0.0, set()
        for idx in order:
            need = person["studies"][idx]["need"]
            cand = None
            for sid in sids:
                s = sources[sid]
                if not _compatible(person, s, need):
                    continue
                opt = _best_option(need, s, used)
                if not opt:
                    continue
                sc = opt[0] + (GROUP_BONUS if s["group"] and s["group"] == person["group"] else 0) \
                    + (0.5 if sid in taken else 0.0)
                if cand is None or sc > cand[0]:
                    cand = (sc, opt, sid)
            if cand:
                sc, opt, sid = cand
                picks[idx] = (opt[0], opt[1], opt[2], sid)
                used.update(r["source_series_uid"] for r in opt[2])
                taken.add(sid)
                total += COVER + sc
        if taken:
            total -= EXTRA_SOURCE * (len(taken) - 1) + sum(_source_penalty(person, sources[s]) for s in taken)
        if total > best[0] + 1e-9:
            best = (total, picks, taken)
    return best


def _person_key(rec):
    """One person across duplicate registrations (a permanent and a temporary UHID with the same name, birth date
    and sex): the same body may serve both."""
    name = str(rec.get("name") or "").strip().lower()
    if name and rec.get("dob_iso"):
        return f"{name}|{rec.get('dob_iso')}|{rec.get('sex') or ''}"
    return "uhid|" + str(rec.get("uhid") or rec.get("id"))


def _optimise(persons, sources):
    """owner {source id: person key}: start empty, then move single source patients (and swap pairs) while the total
    value grows. Deterministic (sorted iteration, strict improvement)."""
    owner, cache = {}, {}

    def owned(pk):
        return frozenset(s for s, o in owner.items() if o == pk)

    def val(pk, sids):
        key = (pk, sids)
        if key not in cache:
            cache[key] = _person_value(persons[pk], sids, sources)[0]
        return cache[key]

    pks = sorted(persons)
    for _ in range(60):
        improved = False
        for sid in sorted(sources, key=lambda s: sources[s]["slot"] or s):
            cur = owner.get(sid)
            loss = (val(cur, owned(cur) - {sid}) - val(cur, owned(cur))) if cur else 0.0   # <= 0 while it helps
            best_delta, best_pk = 0.0, None   # only moves that raise the total
            for pk in pks:
                if pk == cur:
                    continue
                gain = val(pk, owned(pk) | {sid}) - val(pk, owned(pk))
                if gain + loss > best_delta + 1e-9:
                    best_delta, best_pk = gain + loss, pk
            if best_pk is not None:
                owner[sid] = best_pk
                improved = True
            elif cur is not None and loss > 1e-9:
                del owner[sid]               # the person is better off without it
                improved = True
        if not improved:                     # pair swaps between two persons
            items = sorted(owner.items())
            for i, (s1, a) in enumerate(items):
                for s2, b in items[i + 1:]:
                    if a == b or owner.get(s1) != a or owner.get(s2) != b:
                        continue
                    before = val(a, owned(a)) + val(b, owned(b))
                    oa, ob = owned(a) - {s1} | {s2}, owned(b) - {s2} | {s1}
                    if val(a, oa) + val(b, ob) > before + 1e-9:
                        owner[s1], owner[s2] = b, a
                        improved = True
        if not improved:
            break
    return owner


def plan_assignment(store_json_path, manifest_path, out_path=ASSIGNMENT, groups=None):
    """Pick a public series for every HIMS imaging study (accession) and write out_path (assignment.json):
    {accession: {collection, source_series_uid, source_patient_id, reason, slot, source_study_uid, series: [...]}};
    a study with no fit keeps synthetic pixels: source_series_uid null and the reason.

    Rules: modality and body part from the test (NEEDS), sex (mammograms only for women; a known source sex must equal
    the patient's), the patient's cancer group preferred, every source series used once, and one source patient never
    serves two HIMS patients (duplicate registrations of one person count as one patient; one patient may get several
    source patients when one cannot cover all its studies). Coverage first, then fit: a local search over which source
    patient goes to which person. groups: optional {UHID: protocol or group}; default from his_mock/scenarios.json
    (read only), else inferred from the tests and ordering departments. Returns one row per HIMS study."""
    store = json.loads(Path(store_json_path).read_text())
    rows = load_manifest_rows(manifest_path)
    sources = _sources(rows)
    protocols = _protocols() if groups is None else dict(groups)
    orders = store.get("orders", {})
    people = store.get("patients", {})
    persons = {}
    for st in sorted(store.get("imaging_studies", {}).values(),
                     key=lambda s: (s.get("patient_id") or "", s.get("started") or "", s.get("accession") or "")):
        if st.get("status") == "cancelled":
            continue
        order = orders.get(st.get("order_id")) or {}
        prec = people.get(st.get("patient_id")) or {"id": st.get("patient_id")}
        pk = _person_key(prec)
        p = persons.setdefault(pk, {"uhids": [], "sex": prec.get("sex"), "age": prec.get("age"), "studies": [],
                                    "tests": [], "departments": [], "explicit": None})
        if prec.get("uhid") and prec["uhid"] not in p["uhids"]:
            p["uhids"].append(prec["uhid"])
        test = order.get("test") or ""
        p["tests"].append(test)
        if order.get("ordering_department"):
            p["departments"].append(order["ordering_department"])
        p["explicit"] = p["explicit"] or protocols.get(prec.get("uhid")) or prec.get("protocol")
        p["studies"].append({"accession": st.get("accession") or st.get("order_id"), "uhid": prec.get("uhid"),
                             "test": test, "label": order.get("label") or st.get("description") or test,
                             "modality": st.get("modality"), "study_date": st.get("started"),
                             "need": need_key(test, st.get("modality"))})
    order_idx = {n: i for i, n in enumerate(NEED_ORDER)}
    for p in persons.values():
        p["group"] = PROTOCOL_GROUP.get(str(p["explicit"] or "").lower()) or _infer_group(p["tests"], p["departments"])
        p["need_idx"] = sorted((i for i, s in enumerate(p["studies"]) if s["need"]),
                               key=lambda i: (order_idx.get(p["studies"][i]["need"], 99), p["studies"][i]["accession"]))

    owner = _optimise(persons, sources)
    result, out = [], {}
    for pk in sorted(persons, key=lambda k: persons[k]["uhids"][0] if persons[k]["uhids"] else k):
        p = persons[pk]
        _, picks, taken = _person_value(p, frozenset(s for s, o in owner.items() if o == pk), sources)
        for idx, st in enumerate(p["studies"]):
            row = {"accession": st["accession"], "uhid": st["uhid"], "person": pk, "patient_sex": p["sex"],
                   "test": st["test"], "modality": st["modality"], "study_date": st["study_date"], "group": p["group"]}
            if idx in picks:
                score, study, take_rows, sid = picks[idx]
                s = sources[sid]
                prim = take_rows[0]
                desc = ", ".join(f"{r['modality']} {r.get('series_description') or r['role']}" for r in take_rows)
                bits = [f"{st['label']}: {desc}", f"from {s['slot']} {s['collection']}",
                        f"source {s['sex'] or 'sex not recorded'}" + (f" {s['age']}" if s["age"] is not None else "")]
                if s["group"] and s["group"] == p["group"]:
                    bits.append(f"same cancer group ({p['group']})")
                elif s["stand_in"]:
                    bits.append("head and neck stand-in (not a head and neck cancer patient)")
                else:
                    bits.append(f"source group {s['group'] or 'general'}, patient group {p['group'] or 'unknown'}")
                if st["need"] == "pet_ct" and all(r["role"] == "pt_wb" for r in take_rows):
                    bits.append("PET only: the CT of this source PET-CT serves another study of this patient")
                if len(taken) > 1:
                    bits.append(f"this patient's studies use {len(taken)} source patients")
                if len(p["uhids"]) > 1:
                    bits.append("same body for both registrations of this person (" + ", ".join(p["uhids"]) + ")")
                entry = {"collection": prim["collection"], "source_series_uid": prim["source_series_uid"],
                         "source_patient_id": sid, "reason": "; ".join(bits), "slot": s["slot"],
                         "source_study_uid": prim["source_study_uid"],
                         "series": [{"source_series_uid": r["source_series_uid"], "role": r["role"],
                                     "modality": r["modality"], "series_description": r.get("series_description"),
                                     "instances": r.get("instances"), "deface_check": r.get("deface_check")}
                                    for r in take_rows]}
                row.update(entry, status="public")
            else:
                if st["need"] is None:
                    reason = _no_fit_reason(st["test"], st["modality"])
                elif st["need"] == "mammogram" and p["sex"] != "F":
                    reason = "mammograms are assigned to women only"
                else:
                    reason = (f"every public series that fits {st['label']} for a {p['sex'] or 'patient'} is "
                              f"assigned to another study or patient (one source patient never serves two HIMS "
                              f"patients)")
                entry = {"collection": None, "source_series_uid": None, "source_patient_id": None,
                         "reason": "stays synthetic: " + reason}
                row.update(entry, status="synthetic")
            out[st["accession"]] = entry
            result.append(row)
    if out_path:
        Path(out_path).write_text(json.dumps(out, indent=1) + "\n")
    return result


def check_assignment(rows):
    """Problems of a plan: a source patient serving two persons, a source series used twice, a mammogram for a man."""
    problems, owner, seen = [], {}, {}
    for r in rows:
        if r.get("status") != "public":
            continue
        sid, who = r["source_patient_id"], r.get("person") or r["uhid"]
        if owner.setdefault(sid, who) != who:
            problems.append(f"source patient {sid} serves {owner[sid]} and {who}")
        for s in r["series"]:
            if s["source_series_uid"] in seen:
                problems.append(f"series {s['source_series_uid']} used by {seen[s['source_series_uid']]} and "
                                f"{r['accession']}")
            seen[s["source_series_uid"]] = r["accession"]
        if r["test"] == "mammogram" and r["patient_sex"] != "F":
            problems.append(f"{r['accession']}: mammogram for a {r['patient_sex']} patient")
    return problems


# ------------------------------------------------------------------------ CLI
def _check_one(key, out_dir, manifest_path):
    """Relabel one library series to out_dir with a made-up identity and verify it (a dry run of phase 2)."""
    rows = load_manifest_rows(manifest_path)
    row = next(r for r in rows if key in (r["source_series_uid"], r["slot"], r["slot"].replace(" ", "_")))
    acc = "RAD/26/99999"
    ident = {"name": "Test Patient (SYNTHETIC)", "uhid": "VXH/26/999999", "sex": "F", "age": 50}
    res = relabel_series(row["raw_dir"], out_dir, ident, study_uid(acc), series_uid_fn_for(acc),
                         instance_uid_fn_for(acc), acc, "2026-09-01", "093000", "Vaidyx Demo Hospital (SYNTHETIC)",
                         "Dr Test Consultant", "CHECK")
    problems = verify_relabelled(out_dir, {"source_patient_id": row["source_patient_id"],
                                           "collection": row["collection"], "source_uids": res["source_uids"],
                                           "patient_id": ident["uhid"], "accession": acc, "study_uid": study_uid(acc),
                                           "instances": row["instances"], "pixel_sha256": res["pixel_sha256"]})
    return row, res, problems


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--plan", action="store_true", help="write pacs_public/assignment.json")
    ap.add_argument("--check", nargs="*", default=None, help="relabel library series (slots or UIDs) and verify")
    ap.add_argument("--store", default=str(DEFAULT_STORE))
    ap.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    ap.add_argument("--out", default=None, help="--plan: assignment path; --check: scratch folder")
    args = ap.parse_args(argv)
    if args.plan:
        rows = plan_assignment(args.store, args.manifest, args.out or ASSIGNMENT)
        for r in rows:
            src = f"{r.get('slot')} {r.get('collection')} [{', '.join(s['modality'] + ' ' + str(s['series_description'])[:24] for s in r['series'])}]" \
                if r["status"] == "public" else r["reason"]
            print(f"{r['accession']:13s} {r['uhid']:15s} {r['patient_sex'] or '-'} {r['test']:26s} {src}")
        problems = check_assignment(rows)
        print(f"{sum(r['status'] == 'public' for r in rows)} of {len(rows)} studies get public images; "
              f"problems: {problems or 'none'}")
        return 1 if problems else 0
    if args.check is not None:
        base = Path(args.out or "relabel_check")
        bad = 0
        for key in args.check:
            row, res, problems = _check_one(key, base / slug(key), args.manifest)
            bad += bool(problems)
            print(f"{row['slot']:14s} {row['modality']} {res['instances']:4d} files, removed {len(res['removed_tags'])} "
                  f"tag kinds: {'OK' if not problems else problems[:5]}")
        return 1 if bad else 0
    ap.error("give --plan or --check")


if __name__ == "__main__":
    if __package__ in (None, ""):   # python -I pacs_public/relabel.py: import as the package (repo root, our code)
        sys.path.insert(0, str(HERE.parent))
        from pacs_public import relabel as _self
        sys.exit(_self.main())
    sys.exit(main())
