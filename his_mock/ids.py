"""Identifier and time helpers for the mock hospital (SYNTHETIC only). Pure stdlib.

Store ids are deterministic slugs of the hospital identifiers, so tests and later items can name them:
UHID VXH/26/004201 -> patient vxh-26-004201, OP/26/118701 -> encounter op-26-118701, RAD/26/00981 -> order rad-26-00981.
"""
import re
import uuid
from datetime import date, datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
# Fixed namespace for DICOM Study UIDs (2.25.<uuid as integer>): the same accession always gives the same Study UID.
STUDY_UID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "his-mock.vaidyx-demo.invalid")

PATTERNS = {
    "uhid": re.compile(r"^VXH/\d{2}/\d{6}$"),
    "temporary_uhid": re.compile(r"^VXH/T/\d{2}/\d{5}$"),
    "ip_no": re.compile(r"^IP/\d{2}/\d{5}$"),
    "op_no": re.compile(r"^OP/\d{2}/\d{6}$"),
    "accession": re.compile(r"^[A-Z]{2,5}/\d{2}/\d{5}$"),
    "sample_barcode": re.compile(r"^VXS\d{8}$"),
    "reg_no": re.compile(r"^VXREG-\d{5}$"),
    "certificate_serial": re.compile(r"^VXDCA-[0-9A-F]{8}$"),
}


def slug(value):
    """Lowercase, '/' and spaces -> '-': VXH/T/26/00412 -> vxh-t-26-00412."""
    return re.sub(r"[/\s]+", "-", str(value).strip()).lower()


def patient_id(uhid):
    return slug(uhid)


def encounter_id(number):
    return slug(number)


def order_id(accession=None, record_id=None):
    """Order id: the accession slug, or ord-<record id> for an order without one (OPD notes, discharge summaries)."""
    if accession:
        return slug(accession)
    return "ord-" + slug(record_id)


def specimen_id(barcode):
    return "spec-" + slug(barcode)


def imaging_study_id(accession):
    return "img-" + slug(accession)


def practitioner_id(reg_no):
    return "prac-" + slug(reg_no)


def department_id(code):
    return "dept-" + slug(code)


def signature_id(report_id, version):
    return f"sig-{report_id}-v{version}"


def study_uid(accession):
    """Deterministic DICOM Study UID for an accession: 2.25.<uuid5 as integer> (at most 44 characters)."""
    return "2.25." + str(uuid.uuid5(STUDY_UID_NAMESPACE, str(accession)).int)


def parse_time(value):
    """ISO date or date-time (string, date or datetime) -> aware datetime in IST. A bare date means 00:00 IST."""
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, date):
        dt = datetime(value.year, value.month, value.day)
    else:
        s = str(value).strip()
        dt = datetime.fromisoformat(s[:-1] + "+00:00" if s.endswith("Z") else s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    return dt.astimezone(IST)


def iso(value):
    """Aware ISO date-time with the IST offset, to the second: 2026-09-01T13:30:00+05:30."""
    return parse_time(value).replace(microsecond=0).isoformat()


def iso_date(value):
    """ISO date (YYYY-MM-DD) of a date or date-time; a date-only string is kept as it is."""
    if isinstance(value, str) and len(value.strip()) == 10:
        return value.strip()
    return parse_time(value).date().isoformat()


def display_date(value):
    """DD/MM/YYYY."""
    return parse_time(value).strftime("%d/%m/%Y")


def display_time(value):
    """DD/MM/YYYY HH:MM (the signature block format)."""
    return parse_time(value).strftime("%d/%m/%Y %H:%M")
