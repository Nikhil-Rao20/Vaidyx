"""identity: rule reading of the patient header and matching to Case Files (V1 item 2.4). Synthetic headers only."""
import pytest

from tumour_board import grounding
from tumour_board import identity as I

LFT = """Sahyadri Cancer Institute (SYNTHETIC)
Department of Laboratory Medicine
LIVER FUNCTION TESTS
Patient name Hospital No. Age / Sex
Md. Irfan Shaikh SYN-600744 61 Y / M
Reg. date Collected on Reported on
23/09/2026 07:50 23/09/2026 08:05 23/09/2026 13:00
Ref. by Sample ID
Dr. Imtiaz Ahmed LAB/26/120555"""
RBS = """BLOOD SUGAR REPORT
Name Age / Sex Collected on Reported on
Ramesh Kumar 60 Y / M 16/09/2026 09:00 16/09/2026 11:30
...
Sd/-
Dr. R. Pillai, MD (Biochemistry), KMC Reg. No. 70418"""
PAP = """CERVICAL CYTOLOGY (PAP SMEAR)
Patient name Sunita Devi
W/o Late Ram Prakash
UHID SYN-500911
Age / Sex 67 Y / F
Collected on 13/09/2026"""
REVIEW = """Patient name Smt. S. Devi
UHID SYN-500263
Age / Sex 52 Y / F"""
MAMMO = """Patient name Smt. Laxmi Iyer
UHID SYN-200417
Age / Sex 48 Y / F"""
USG = """ULTRASOUND ABDOMEN AND PELVIS
Name CR No. Age / Sex Study date
RAMESH KUMAR CR/2026/04118 58 Y / M 10/09/2026
Reported on
10/09/2026"""
XRAY = """Patient name R. Kumar
UHID SYN-100231
Age / Sex 62 Y / M"""
CECT = """CECT THORAX
Patient name CR No. Age / Sex
R. Kumar CR/2026/04118 58Y/M
Study date Reported on Ref. by
02/09/2026 03/09/2026 Dr. Harish Gowda (Kaveri Multispeciality Hospital, Mandya)"""
OPD = """MEDICAL ONCOLOGY OPD NOTE
Patient name Shri Ramesh Kumar
UHID SYN-400118
ABHA No. 91-4021-7788-3105
Age / Sex 58 Y / M
DOB 14/03/1968
Relation S/o Mohan Lal
Visit date 05/09/2026
Next review 19/09/2026"""
CBC = """HAEMATOLOGY REPORT
Name UHID Age / Sex
Smt. Sunita Devi SYN-500911 67 Y / F
Aadhaar No. Reg. date Collected on
7395 8406 1180 15/09/2026 08:20 15/09/2026 08:30
Reported on Ref. by Sample ID
15/09/2026 12:10 OPD (Gynaecology) LAB/26/119870"""
PIPE = "Patient: SYNTHETIC, Ramesh Kumar | MRN: SYN-100231 | 62 Y / M"
REFERRAL = """REFERRAL LETTER
Patient name Ramesh Kumar S/o Mohan Lal
Age / Sex 58 Y / M
Aadhaar No. 6043 1187 2200
OP No. KMH/OP/26/55120"""
OUTSIDE = "Patient: Md. Irfan Shaikh S/o Abdul Kareem Shaikh. Age / Sex: 61 Y / M."

PATIENTS = [
    {"case_id": "TB-001", "listed": True, "patient": {"name": "Ramesh Kumar", "mrn": "SYN-100231", "agesex": "62 Y / M"}},
    {"case_id": "TB-002", "listed": True, "patient": {"name": "Lakshmi Iyer", "mrn": "SYN-200417", "agesex": "48 Y / F"}},
    {"case_id": "TB-003", "listed": True, "patient": {"name": "Abdul Rahman", "mrn": "SYN-300582", "agesex": "57 Y / M"}},
    {"case_id": "TB-004", "listed": True, "patient": {"name": "Ramesh Kumar", "mrn": "SYN-400118", "ids": [{"kind": "cr_no", "value": "CR/2026/04118"}],
                                                      "abha": "91402177883105", "agesex": "58 Y / M", "dob": "1968-03-14"}},
    {"case_id": "TB-005", "listed": True, "patient": {"name": "Sunita Devi", "mrn": "SYN-500263", "abha": "91673022459018", "agesex": "52 Y / F"}},
    {"case_id": "TB-006", "listed": True, "patient": {"name": "Mohammed Irfan Shaikh", "mrn": "SYN-600744", "agesex": "61 Y / M"}},
]
TODAY = "2026-10-11"


def read(text):
    return I.read_identity([text])


def located(quote, text):
    return grounding.locate(quote, [text]) is not None


def kinds(r):
    return [(i["kind"], i["value"]) for i in r["ids"]]


def idt(name=None, ids=(), age=None, sex=None, dob=None, relation=None, abha=None):
    return {"name": {"value": name} if name else None, "ids": [{"kind": k, "value": v} for k, v in ids], "age": age, "sex": sex,
            "dob": dob, "relation": relation, "abha": abha, "aadhaar_seen": False}


# ---- Aadhaar ----------------------------------------------------------------------------------------------------------
def test_mask_aadhaar_cbc_header_keeps_last_four_only():
    masked, n = I.mask_aadhaar(CBC)
    assert n == 1 and "XXXX XXXX 1180 15/09/2026 08:20" in masked
    assert "7395" not in masked and "8406" not in masked
    assert masked.replace("XXXX XXXX 1180", "7395 8406 1180") == CBC  # nothing else touched


def test_mask_aadhaar_leaves_abha_and_lab_numbers():
    for text in ("ABHA No. 91-4021-7788-3105", "ABHA No. 91 4021 7788 3105", "ABHA 91402177883105", OPD,
                 "Lab No. 202609150042", "Sample 202609150042 received", "UHID SYN-500911", "Collected on 15/09/2026 08:20"):
        assert I.mask_aadhaar(text) == (text, 0), text


@pytest.mark.parametrize("text,want", [
    ("Aadhaar No. 604311872200", "Aadhaar No. XXXX XXXX 2200"),
    ("Aadhaar No. 6043 1187 2200", "Aadhaar No. XXXX XXXX 2200"),
    ("Adhar: 6043-1187-2200", "Adhar: XXXX XXXX 2200"),
    ("UID 604311872200", "UID XXXX XXXX 2200"),
    ("ID proof 6043 1187 2200 seen", "ID proof XXXX XXXX 2200 seen"),  # grouped 4-4-4, no label needed
])
def test_mask_aadhaar_forms(text, want):
    assert I.mask_aadhaar(text) == (want, 1)


def test_mask_aadhaar_under_grid_label_unseparated():
    masked, n = I.mask_aadhaar("Aadhaar No. Reg. date\n604311872200 15/09/2026")
    assert n == 1 and masked.endswith("XXXX XXXX 2200 15/09/2026")


# ---- ids, age / sex ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("raw,want", [("SYN-600744", "SYN600744"), ("CR/2026/04118", "CR202604118"), ("91-4021-7788-3105", "91402177883105"),
                                      (" syn 100231 ", "SYN100231"), ("KMH/OP/26/55120", "KMHOP2655120"), ("", "")])
def test_normalise_id(raw, want):
    assert I.normalise_id(raw) == want


@pytest.mark.parametrize("s,want", [
    ("62 Y / M", (62, "M")), ("58 yrs / Male", (58, "M")), ("58Y/M", (58, "M")), ("67 Y / F", (67, "F")),
    ("Age: 62 Years Sex: F", (62, "F")), ("Age: 62 Years Sex: M", (62, "M")), ("Age / Gender 45 Years / Female", (45, "F")),
    ("62Y/M", (62, "M")), ("Age / Sex: 61 Y / M.", (61, "M")), ("30 Y / Transgender", (30, "O")), ("Age: 40", (40, None)),
    ("Sex: Female", (None, "F")), ("Collected on 16/09/2026", (None, None)), ("", (None, None)),
])
def test_parse_agesex(s, want):
    assert I.parse_agesex(s) == want


# ---- names ------------------------------------------------------------------------------------------------------------
def test_normalise_name_forms():
    n = I.normalise_name("Smt. S. Devi")
    assert n["tokens"] == ["s", "devi"] and n["initials"] == ["s"] and n["keys"] == ["dewi"] and n["sex_hint"] == "F"
    n = I.normalise_name("KUMAR, RAMESH (Mr.)")
    assert n["tokens"] == ["ramesh", "kumar"] and n["sex_hint"] == "M"
    n = I.normalise_name("Ramesh Kumar S/o Mohan Lal")
    assert n["tokens"] == ["ramesh", "kumar"] and n["relation"] == {"kind": "S/o", "name": "Mohan Lal"}
    n = I.normalise_name("Md. Irfan Shaikh")
    assert n["tokens"] == ["md", "irfan", "shaikh"] and n["keys"][0] == I.phonetic_key("Mohammed")
    assert I.normalise_name("Shri Ramesh Kumar")["tokens"] == ["ramesh", "kumar"]
    assert I.normalise_name("SYNTHETIC, Ramesh Kumar")["tokens"] == ["ramesh", "kumar", "synthetic"]  # comma: the part before goes last
    assert I.normalise_name("Sunita Devi W/o Late Ram Prakash")["relation"] == {"kind": "W/o", "name": "Late Ram Prakash"}
    assert I.normalise_name("Kumari Sunita Kumari")["tokens"] == ["sunita", "kumari"]  # only the leading Kumari is a title


def test_phonetic_keys():
    k = I.phonetic_key
    assert k("Lakshmi") == k("Laxmi") == k("Lakshmy") and k("Sunitha") == k("Suneeta") == k("Sunita")
    assert k("Prathap") == k("Pratap") and k("Sreenivas") == k("Srinivas") and k("Gouda") == k("Gowda")
    assert k("Mohd") == k("Muhammad") == k("Md") and k("Sk") == k("Sheikh") and k("Aiyar") == k("Iyer")
    assert k("Kumar") != k("Kumari")
    assert k("Vijay") == k("Wijai")


@pytest.mark.parametrize("a,b,level", [
    ("Ramesh Kumar", "R. Kumar", "initials"),
    ("Ramesh Kumar", "KUMAR RAMESH", "exact"),
    ("Lakshmi Iyer", "Smt. Laxmi Iyer", "variant"),
    ("Sunita Devi", "Smt. S. Devi", "initials"),
    ("Mohammed Irfan Shaikh", "Md. Irfan Shaikh", "variant"),
    ("Ramesh Kumar", "Suresh Kumar", "incompatible"),
    ("Sunita Devi", "Sunita Kumari", "incompatible"),
    ("Ramesh Kumar", "Ramesh Kumari", "incompatible"),
    ("Lakshmi", "Lakshmi Iyer", "variant"),
    ("Devi", "Sunita Devi", "incompatible"),
    ("Kumar", "Kumar", "incompatible"),
    ("SYNTHETIC, Ramesh Kumar", "R. Kumar", "initials"),
    ("SYNTHETIC, Ramesh Kumar", "Ramesh Kumar", "variant"),
    ("KUMAR, RAMESH (Mr.)", "Shri Ramesh Kumar", "exact"),
    ("Ramesh Gowda", "Ramesh Patil", "partial"),
    ("R. Kumar", "Suresh Kumar", "incompatible"),
    ("Venkata Ramana", "Venkataramana", "variant"),
    ("Rarnesh Kumar", "Ramesh Kumar", "variant"),  # OCR rn / m
    ("Md. Ali Khan", "Mohammed Ali Khan", "variant"),  # all generic, but every part agrees
    ("R.", "Ramesh", "incompatible"),
])
def test_names_compatible(a, b, level):
    assert I.names_compatible(a, b)["level"] == level
    assert I.names_compatible(b, a)["level"] == level  # symmetric


def test_names_compatible_flags():
    assert I.names_compatible("Ramesh Kumar", "Ramesh Kumari")["sex_conflict"] is True
    assert I.names_compatible("Mr. Ramesh", "Smt. Ramesh")["sex_conflict"] is True
    assert I.names_compatible("Sunita Devi", "Sunita Kumari")["sex_conflict"] is False
    assert I.names_compatible("Ramesh Kumar", "R. Kumar")["distinctive"] is False  # an initial and a common surname only
    assert I.names_compatible("Smt. S. Devi", "Sunita Devi")["distinctive"] is False
    assert I.names_compatible("Lakshmi Iyer", "Laxmi Iyer")["distinctive"] is True
    assert I.names_compatible("Lakshmi Iyer", "Laxmi Iyer")["detail"].startswith("spelling variant")


# ---- read_identity ----------------------------------------------------------------------------------------------------
def assert_quotes(r, text):
    quotes = [i["quote"] for i in r["ids"]] + [r["agesex_quote"]] + ([r["name"]["quote"]] if r["name"] else [])
    quotes += [r["dob_quote"]] if r["dob"] else []
    quotes += [r["relation"]["quote"]] if r["relation"] else []
    for q in quotes:
        if q:
            assert located(q, text), q


@pytest.mark.parametrize("text,name,ids,age,sex", [
    (LFT, "Md. Irfan Shaikh", [("hospital_no", "SYN-600744")], 61, "M"),
    (RBS, "Ramesh Kumar", [], 60, "M"),
    (PAP, "Sunita Devi", [("uhid", "SYN-500911")], 67, "F"),
    (REVIEW, "Smt. S. Devi", [("uhid", "SYN-500263")], 52, "F"),
    (MAMMO, "Smt. Laxmi Iyer", [("uhid", "SYN-200417")], 48, "F"),
    (USG, "RAMESH KUMAR", [("cr_no", "CR/2026/04118")], 58, "M"),
    (XRAY, "R. Kumar", [("uhid", "SYN-100231")], 62, "M"),
    (CECT, "R. Kumar", [("cr_no", "CR/2026/04118")], 58, "M"),
    (OPD, "Shri Ramesh Kumar", [("uhid", "SYN-400118"), ("abha", "91-4021-7788-3105")], 58, "M"),
    (CBC, "Smt. Sunita Devi", [("uhid", "SYN-500911")], 67, "F"),
    (PIPE, "SYNTHETIC, Ramesh Kumar", [("mrn", "SYN-100231")], 62, "M"),
    (REFERRAL, "Ramesh Kumar", [("op_no", "KMH/OP/26/55120")], 58, "M"),
    (OUTSIDE, "Md. Irfan Shaikh", [], 61, "M"),
])
def test_read_identity_headers(text, name, ids, age, sex):
    r = read(text)
    assert r["name"]["value"] == name and r["name"]["page"] == 0
    assert kinds(r) == ids and (r["age"], r["sex"]) == (age, sex)
    assert_quotes(r, text)
    assert not any(v in ("70418", "LAB/26/120555", "LAB/26/119870") for _, v in kinds(r))


def test_read_identity_details():
    r = read(LFT)
    assert r["ids"][0]["label"] == "Hospital No." and r["hospital_header"] == "Sahyadri Cancer Institute (SYNTHETIC)" and not r["aadhaar_seen"]
    r = read(OPD)
    assert r["dob"] == "1968-03-14" and r["dob_quote"] == "DOB 14/03/1968" and r["abha"] == "91402177883105"
    assert r["relation"] == {"kind": "S/o", "name": "Mohan Lal", "quote": "Relation S/o Mohan Lal"}
    r = read(PAP)
    assert r["relation"]["kind"] == "W/o" and r["relation"]["name"] == "Late Ram Prakash" and r["relation"]["quote"] == "W/o Late Ram Prakash"
    r = read(CBC)
    assert r["aadhaar_seen"] is True and "7395" not in str(r) and any("Aadhaar" in n for n in r["notes"])
    r = read(REFERRAL)
    assert r["aadhaar_seen"] is True and r["relation"]["name"] == "Mohan Lal" and "6043" not in str(r)
    r = read(OUTSIDE)
    assert r["relation"] == {"kind": "S/o", "name": "Abdul Kareem Shaikh", "quote": OUTSIDE}
    assert read(CECT)["agesex_quote"] == "R. Kumar CR/2026/04118 58Y/M"


def test_read_identity_other_forms():
    t = "Name KUMAR RAMESH\n58 yrs / Male"
    r = read(t)
    assert r["name"]["value"] == "KUMAR RAMESH" and (r["age"], r["sex"]) == (58, "M") and located(r["agesex_quote"], t)
    t = "Name KUMAR, RAMESH (Mr.)\nAge: 62 Years Sex: M\nFather / Guardian Mohan Lal\nD.O.B. 14/03/1968"
    r = read(t)
    assert (r["age"], r["sex"], r["dob"]) == (62, "M", "1968-03-14") and r["relation"]["kind"] == "S/o" and r["relation"]["name"] == "Mohan Lal"
    r = read("Patient name Sunita Devi\nAge / Gender 67 Y / F\nHusband's Name Ram Prakash\nDate of Birth 11/07/1959")
    assert r["relation"]["kind"] == "W/o" and r["dob"] == "1959-07-11" and r["sex"] == "F"
    r = read("Name Asha Rani\nAge: 44 Years\nSex: Female")
    assert (r["age"], r["sex"]) == (44, "F") and located(r["agesex_quote"], "Name Asha Rani\nAge: 44 Years\nSex: Female")


@pytest.mark.parametrize("label,kind", [("UHID No.", "uhid"), ("MRD No.", "mrn"), ("MRN", "mrn"), ("Hosp. No.", "hospital_no"),
                                        ("Hospital No.", "hospital_no"), ("Patient ID", "hospital_no"), ("CR No.", "cr_no"),
                                        ("IP No.", "ip_no"), ("IPD No.", "ip_no"), ("OP No.", "op_no"), ("Reg. No.", "reg_no"),
                                        ("Registration No.", "reg_no"), ("PM-JAY ID", "pmjay")])
def test_id_label_variants(label, kind):
    r = read(f"Patient name Asha Rani\n{label} AB-77120\nAge / Sex 44 Y / F")
    assert kinds(r) == [(kind, "AB-77120")]


def test_never_patient_ids():
    t = "Patient name Asha Rani\nLab No. 260915004\nSample ID LAB/26/1\nAccession No. ACC-7781\nAge / Sex 44 Y / F"
    assert read(t)["ids"] == []
    # the doctor's council number after the signature, and a council number inside the header
    t = "Patient name Asha Rani\nUHID SYN-1\nAge / Sex 44 Y / F\nSd/-\nUHID SYN-2\nDr. A. Rao, MD, KMC Reg. No. 70418"
    assert kinds(read(t)) == [("uhid", "SYN-1")]
    t = "Patient name Asha Rani\nAge / Sex 44 Y / F\nRef. by Dr. A. Rao, MMC Reg. No. 2009/03/1187"
    assert read(t)["ids"] == []
    t = "Patient name Asha Rani\nAge / Sex 44 Y / F\nReg. No. 55120\nReported by: Dr. A. Rao (electronically signed)"
    assert read(t)["ids"] == []  # a Reg. No. right above the signer is the doctor's
    t = "Patient name Asha Rani\nReg. No. 55120\nAge / Sex 44 Y / F\nVisit date 01/09/2026\nClinical notes"
    assert kinds(read(t)) == [("reg_no", "55120")]


def test_header_only_and_other_pages():
    body = "\n".join(f"Finding line {i}" for i in range(30))
    r = I.read_identity([body + "\nUHID SYN-9"])
    assert r["ids"] == [] and r["name"] is None
    r = I.read_identity(["DISCHARGE SUMMARY\nCourse in hospital", "Patient name Asha Rani\nUHID SYN-9\nAge / Sex 44 Y / F"])
    assert r["name"]["page"] == 1 and r["ids"][0]["page"] == 1 and r["age"] == 44


def test_read_identity_drops_unlocated_and_empty():
    assert I.read_identity([]) ["name"] is None
    r = read("Patient name\nUHID SYN-9")  # a label with its value missing
    assert r["name"] is None and kinds(r) == [("uhid", "SYN-9")]


# ---- patient_record ---------------------------------------------------------------------------------------------------
def test_patient_record():
    r = I.patient_record(PATIENTS[3]["patient"])
    assert ("uhid", "SYN400118") in r["ids"] and ("mrn", "SYN400118") in r["ids"] and ("cr_no", "CR202604118") in r["ids"]
    assert ("abha", "91402177883105") in r["ids"] and r["abha"] == "91402177883105"
    assert (r["age"], r["sex"], r["dob"]) == (58, "M", "1968-03-14")
    r = I.patient_record({"name": "SYNTHETIC, Ramesh Kumar", "mrn": "SYN-100231", "agesex": "62 Y / M", "relation": "S/o Mohan Lal", "aliases": ["R. Kumar"]})
    assert r["relation"] == {"kind": "S/o", "name": "Mohan Lal"} and r["aliases"] == ["R. Kumar"] and r["age"] == 62
    assert I.patient_record({})["ids"] == set()


# ---- match: the eight intake headers ----------------------------------------------------------------------------------
def m(text, patients=PATIENTS):
    return I.match(read(text), patients, today=TODAY)


@pytest.mark.parametrize("text,case_id,kind", [
    (XRAY, "TB-001", "uhid"),        # same common name as TB-004, the UHID decides
    (USG, "TB-004", "cr_no"),
    (CECT, "TB-004", "cr_no"),
    (MAMMO, "TB-002", "uhid"),       # Laxmi / Lakshmi
    (REVIEW, "TB-005", "uhid"),      # S. Devi
    (LFT, "TB-006", "hospital_no"),  # Hospital No. against the MRN, Md. / Mohammed
    (OPD, "TB-004", "uhid"),
    (PIPE, "TB-001", "mrn"),
])
def test_match_auto_link(text, case_id, kind):
    r = m(text)
    assert (r["decision"], r["case_id"], r["matched_on"]["kind"]) == ("auto_link", case_id, kind)
    assert r["candidates"][0]["id_match"] is True


def test_same_name_different_patient_never_links():
    for text in (PAP, CBC):
        r = m(text)
        assert r["decision"] == "new_case" and r["case_id"] is None and r["matched_on"] == {"kind": "uhid", "value": "SYN-500911"}
        assert "TB-005" in [c["case_id"] for c in r["candidates"]] and "TB-005" in r["reason"]
    new = {"case_id": "TB-2026-0007", "listed": False, "patient": {"name": "Sunita Devi", "mrn": "SYN-500911", "agesex": "67 Y / F"}}
    r = m(CBC, PATIENTS + [new])
    assert (r["decision"], r["case_id"]) == ("auto_link", "TB-2026-0007")
    assert (m(PAP, PATIENTS + [new])["case_id"]) == "TB-2026-0007"


def test_no_id_same_name_two_patients_needs_matching():
    r = m(RBS)
    assert r["decision"] == "needs_matching" and r["case_id"] is None
    assert [c["case_id"] for c in r["candidates"]] == ["TB-001", "TB-004"]
    assert all(c["age_fit"] is False and c["sex_fit"] is True for c in r["candidates"])


# ---- match: rules -----------------------------------------------------------------------------------------------------
def test_id_matches_name_differs_is_id_conflict():
    r = I.match(idt("Suresh Patil", [("uhid", "SYN-100231")], 62, "M"), PATIENTS, TODAY)
    assert r["decision"] == "id_conflict" and r["case_id"] is None and r["candidates"][0]["case_id"] == "TB-001" and "wrong ID" in r["reason"]
    for bad in (idt("Ramesh Kumar", [("uhid", "SYN-100231")], 62, "F"), idt("Ramesh Kumar", [("uhid", "SYN-100231")], 70, "M"),
                idt("Ramesh Kumari", [("uhid", "SYN-100231")], 62, "M"),
                idt("Ramesh Kumar", [("cr_no", "CR/2026/04118")], 58, "M", dob="1970-01-01")):
        assert I.match(bad, PATIENTS, TODAY)["decision"] == "id_conflict"
    # the CR No. is TB-004's but the UHID printed beside it is another one
    r = I.match(idt("Ramesh Kumar", [("cr_no", "CR/2026/04118"), ("uhid", "SYN-999999")], 58, "M"), PATIENTS, TODAY)
    assert r["decision"] == "id_conflict"


def test_two_case_files_with_one_id_is_id_conflict():
    dup = {"case_id": "TB-009", "patient": {"name": "Lakshmi Iyer", "mrn": "SYN-200417", "agesex": "48 Y / F"}}
    r = I.match(read(MAMMO), PATIENTS + [dup], TODAY)
    assert r["decision"] == "id_conflict" and {c["case_id"] for c in r["candidates"]} == {"TB-002", "TB-009"}
    r = I.match(idt("Ramesh Kumar", [("uhid", "SYN-100231"), ("cr_no", "CR/2026/04118")], 60, "M"), PATIENTS, TODAY)
    assert r["decision"] == "id_conflict"


def test_name_only_suggest_and_ambiguity():
    li = idt("Lakshmi Iyer", age=48, sex="F")
    r = I.match(li, PATIENTS, TODAY)
    assert (r["decision"], r["case_id"]) == ("suggest", "TB-002") and r["candidates"][0]["id_match"] is False
    assert I.match(idt("Laxmi Iyer", age=49, sex="F"), PATIENTS, TODAY)["decision"] == "suggest"  # variant, age +1: still only a suggestion
    twin = {"case_id": "TB-010", "patient": {"name": "Lakshmi Iyer", "mrn": "SYN-201111", "agesex": "48 Y / F"}}
    r = I.match(li, PATIENTS + [twin], TODAY)
    assert r["decision"] == "needs_matching" and {c["case_id"] for c in r["candidates"]} == {"TB-002", "TB-010"}
    r = I.match(idt("Lakshmi", age=48, sex="F"), PATIENTS, TODAY)
    assert r["decision"] == "needs_matching" and r["case_id"] is None and "single name" in r["reason"]
    assert I.match(idt("Lakshmi Iyer", age=48, sex="M"), PATIENTS, TODAY)["decision"] == "needs_matching"
    assert I.match(idt("Lakshmi Iyer", age=55, sex="F"), PATIENTS, TODAY)["decision"] == "needs_matching"
    # an initial with only a common surname never suggests on its own
    assert I.match(idt("R. Kumar", age=62, sex="M"), PATIENTS, TODAY)["decision"] == "needs_matching"


def test_dob_and_relation_in_suggestions():
    # DOB equal: suggests even when the printed age is off (TB-004 is 58 today)
    r = I.match(idt("Ramesh Kumar", age=60, sex="M", dob="1968-03-14"), PATIENTS, TODAY)
    assert (r["decision"], r["case_id"]) == ("suggest", "TB-004") and "DOB matches" in r["reason"]
    assert I.match(idt("Ramesh Kumar", age=58, sex="M", dob="1969-01-01"), PATIENTS[3:4], TODAY)["decision"] == "needs_matching"
    pts = [{"case_id": "TB-004", "patient": dict(PATIENTS[3]["patient"], relation="S/o Mohan Lal")}]
    rel_ok = {"kind": "S/o", "name": "Mohan Lal"}
    rel_bad = {"kind": "S/o", "name": "Suresh"}
    assert I.match(idt("Ramesh Kumar", age=58, sex="M", relation=rel_ok), pts, TODAY)["decision"] == "suggest"
    assert I.match(idt("Ramesh Kumar", age=58, sex="M", relation=rel_bad), pts, TODAY)["decision"] == "needs_matching"
    # with the exact ID the link stands; the relation mismatch is only a note
    r = I.match(idt("Ramesh Kumar", [("uhid", "SYN-400118")], 58, "M", relation=rel_bad), pts, TODAY)
    assert r["decision"] == "auto_link" and "relation differs" in r["reason"]


def test_abha_ip_op_only():
    abha = idt("Ramesh Kumar", [("abha", "91-4021-7788-3105")], 58, "M", abha="91402177883105")
    r = I.match(abha, PATIENTS, TODAY)
    assert (r["decision"], r["case_id"], r["matched_on"]["kind"]) == ("auto_link", "TB-004", "abha")
    r = I.match(idt("Ramesh Kumar", [("abha", "91-1111-2222-3333")], 58, "M", abha="91111122223333"), PATIENTS, TODAY)
    assert r["decision"] == "needs_matching" and "ABHA" in r["reason"]
    r = I.match(idt("Ramesh Kumar", [("ip_no", "IP/26/77777")], 58, "M"), PATIENTS, TODAY)
    assert r["decision"] == "needs_matching" and r["case_id"] is None
    assert m(REFERRAL)["decision"] == "needs_matching"  # another hospital's OP No.: never a new Case File
    ip = {"case_id": "TB-006", "patient": dict(PATIENTS[5]["patient"], ids=[{"kind": "ip_no", "value": "IP/26/18832"}])}
    assert I.match(idt("Md. Irfan Shaikh", [("ip_no", "IP/26/18832")], 61, "M"), [ip], TODAY)["decision"] == "auto_link"


def test_match_without_name_or_patients():
    r = I.match(idt(None, [("uhid", "SYN-100231")]), PATIENTS, TODAY)
    assert r["decision"] == "needs_matching" and r["candidates"][0]["case_id"] == "TB-001"
    assert I.match(idt(None), PATIENTS, TODAY)["decision"] == "needs_matching"
    assert I.match(read(XRAY), [], TODAY)["decision"] == "new_case"
    assert I.match(read(OUTSIDE), PATIENTS, TODAY)["decision"] == "suggest"  # no ID, Md. Irfan Shaikh 61 M fits TB-006 only
    assert I.match(read(OUTSIDE), PATIENTS, TODAY)["case_id"] == "TB-006"


def test_aadhaar_never_matches():
    pts = [{"case_id": "TB-001", "patient": {"name": "Ramesh Kumar", "mrn": "SYN-100231", "agesex": "62 Y / M", "ids": [{"kind": "aadhaar", "value": "604311872200"}]}}]
    assert I.patient_record(pts[0]["patient"])["ids"] == {("uhid", "SYN100231"), ("mrn", "SYN100231")}
    r = I.match(idt("Ramesh Kumar", [("aadhaar", "604311872200")], 70, "M"), pts, TODAY)
    assert r["decision"] == "needs_matching"


def test_describe():
    r = read(PAP)
    r["name"]["value"] = "Sunita Devi"
    r["aadhaar_seen"] = True
    assert I.describe(r) == "Sunita Devi, 67 Y / F, UHID SYN-500911 (Aadhaar seen, masked)"
    assert I.describe(read(OPD)) == "Shri Ramesh Kumar, 58 Y / M, DOB 14/03/1968, UHID SYN-400118, ABHA 91-4021-7788-3105"
    assert I.describe({}) == "name not read"
    assert "\u2014" not in I.describe(read(CBC))


# ---- review fixes: when an unknown identifier may open a Case File (M5), masked Aadhaar vs real IDs (minor 6) ---------
def test_unknown_uhid_without_name_needs_matching():
    r = I.match(idt(None, [("uhid", "SYN-777001")], 52, "F"), PATIENTS, TODAY)
    assert r["decision"] == "needs_matching" and r["case_id"] is None and r["matched_on"] is None
    assert "an identifier was read but no patient name: a person must decide" in r["reason"]
    assert I.match(idt(None, [("uhid", "SYN-777001")]), [], TODAY)["decision"] == "needs_matching"  # even with no Case Files at all


def test_unknown_uhid_with_name_age_sex_fitting_a_patient_needs_matching():
    r = I.match(idt("Sunita Devi", [("uhid", "SYN-500911")], 52, "F"), PATIENTS, TODAY)
    assert r["decision"] == "needs_matching" and r["case_id"] is None and r["matched_on"] is None
    assert r["candidates"][0]["case_id"] == "TB-005" and r["candidates"][0]["id_match"] is False
    assert r["reason"] == ("UHID SYN-500911 is on no Case File, but the name, age and sex fit TB-005 (UHID SYN-500263): the same patient "
                           "registered twice, or a different person; a person must decide")
    # a variant name, age +1, an unknown Hospital No.: still a person's decision
    r = I.match(idt("Laxmi Iyer", [("hospital_no", "SYN-299999")], 49, "F"), PATIENTS, TODAY)
    assert r["decision"] == "needs_matching" and "TB-002 (MRN SYN-200417)" in r["reason"]
    # the same DOB fits even when the printed age is off; a CR No. names the Case File's own CR No.
    r = I.match(idt("Ramesh Kumar", [("cr_no", "CR/2026/09999")], 60, "M", dob="1968-03-14"), PATIENTS, TODAY)
    assert r["decision"] == "needs_matching" and "TB-004 (CR No. CR/2026/04118)" in r["reason"]
    # two exact fits: both listed, never a new Case File
    twin = {"case_id": "TB-010", "patient": {"name": "Lakshmi Iyer", "mrn": "SYN-201111", "agesex": "48 Y / F"}}
    r = I.match(idt("Lakshmi Iyer", [("uhid", "SYN-299999")], 48, "F"), PATIENTS + [twin], TODAY)
    assert r["decision"] == "needs_matching" and [c["case_id"] for c in r["candidates"][:2]] == ["TB-002", "TB-010"]


def test_unknown_uhid_opens_a_case_only_when_nobody_fits():
    for text in (PAP, CBC):  # the second Sunita Devi is 67, TB-005 is 52: a different patient
        r = m(text)
        assert r["decision"] == "new_case" and r["matched_on"] == {"kind": "uhid", "value": "SYN-500911"} and "TB-005" in r["reason"]
    for bad in (idt("Sunita Devi", [("uhid", "SYN-500911")], 52, None),     # sex not read
                idt("Sunita Devi", [("uhid", "SYN-500911")], 52, "M"),      # sex differs
                idt("Sunita Kumari", [("uhid", "SYN-500911")], 52, "F")):   # Devi / Kumari: another name
        assert I.match(bad, PATIENTS, TODAY)["decision"] == "new_case", bad
    # an initial with only a common surname is not a fit: R. Kumar 62 M with an unknown UHID opens a Case File
    assert I.match(idt("R. Kumar", [("uhid", "SYN-100999")], 62, "M"), PATIENTS, TODAY)["decision"] == "new_case"


def test_unknown_reg_no_never_opens_a_case_but_links():
    r = I.match(idt("Asha Rani", [("reg_no", "55120")], 44, "F"), PATIENTS, TODAY)
    assert r["decision"] == "needs_matching" and r["case_id"] is None and "Reg. No. 55120" in r["reason"]
    assert I.match(idt("Asha Rani", [("reg_no", "55120")], 44, "F"), [], TODAY)["decision"] == "needs_matching"
    # a patient who has that Reg. No. (or the same number as UHID / MRN) is linked
    reg = {"case_id": "TB-011", "patient": {"name": "Asha Rani", "mrn": "SYN-700001", "agesex": "44 Y / F", "ids": [{"kind": "reg_no", "value": "55120"}]}}
    r = I.match(idt("Asha Rani", [("reg_no", "55120")], 44, "F"), PATIENTS + [reg], TODAY)
    assert (r["decision"], r["case_id"], r["matched_on"]["kind"]) == ("auto_link", "TB-011", "reg_no")
    plain = {"case_id": "TB-012", "patient": {"name": "Asha Rani", "mrn": "SYN-700001", "agesex": "44 Y / F"}}
    r = I.match(idt("Asha Rani", [("reg_no", "SYN-700001")], 44, "F"), PATIENTS + [plain], TODAY)
    assert (r["decision"], r["case_id"]) == ("auto_link", "TB-012")
    # a Reg. No. beside an unknown UHID: the UHID decides
    r = I.match(idt("Asha Rani", [("reg_no", "55120"), ("uhid", "SYN-700002")], 44, "F"), PATIENTS, TODAY)
    assert r["decision"] == "new_case" and r["matched_on"]["kind"] == "uhid"


@pytest.mark.parametrize("value", ["X100", "XR-2210", "KMH/OP/26/55120", "XX-1234"])
def test_identifiers_that_start_with_x_are_read(value):
    r = read(f"Patient name Asha Rani\nUHID {value}\nAge / Sex 44 Y / F")
    assert kinds(r) == [("uhid", value)]
    r = read(f"Name UHID Age / Sex\nAsha Rani {value} 44 Y / F")  # boxed grid
    assert kinds(r) == [("uhid", value)] and (r["age"], r["sex"]) == (44, "F")


def test_masked_aadhaar_is_never_an_identifier():
    for t in ("Patient name Asha Rani\nUHID XXXX XXXX 1180\nAge / Sex 44 Y / F",
              "Patient name Asha Rani\nUHID xxxx xxxx 1180\nAge / Sex 44 Y / F",
              "Patient name Asha Rani\nUHID 7395 8406 1180\nAge / Sex 44 Y / F",  # masked on reading, then refused
              "Patient name Asha Rani\nReg. No. XXXX XXXX 1180\nAge / Sex 44 Y / F"):
        r = read(t)
        assert r["ids"] == [] and "7395" not in str(r), t
    assert I._id_token("XXXX XXXX 1180") == "" and I._id_token(": XXXX XXXX 1180 15/09/2026") == ""
    assert I._id_token("X100") == "X100"


def test_transcribed_table_with_label_and_value_in_alternate_cells():
    """The vision reader transcribes a boxed lab header as one pipe-separated line: label | value | label | value."""
    text = ("Sahyadri Cancer Institute (SYNTHETIC)\nDepartment of Laboratory Medicine\nHAEMATOLOGY REPORT\n"
            "Name | Smt. Sunita Devi | UHID | SYN-500911 | Age / Sex | 67 Y / F\n"
            "Aadhaar No. | 7395 8406 1180 | Reg. date | 15/09/2026 08:20 | Collected on | 15/09/2026 08:30\n"
            "Reported on | 15/09/2026 12:10 | Ref. by | OPD (Gynaecology) | Sample ID | LAB/26/119870\n"
            "Haemoglobin | 10.8 | gm% | 12.0 - 15.0\n*** End of report ***\nSd/-\nDr. Suresh Babu, MD (Pathology), KMC Reg. No. 69021")
    r = I.read_identity([text])
    assert r["name"]["value"] == "Smt. Sunita Devi" and [(i["kind"], i["value"]) for i in r["ids"]] == [("uhid", "SYN-500911")]
    assert (r["age"], r["sex"], r["aadhaar_seen"]) == (67, "F", True) and "LAB/26/119870" not in str(r["ids"])
    assert grounding.locate(r["name"]["quote"], [text]) and grounding.locate(r["ids"][0]["quote"], [text])
    # the same line with the value in the label's own cell still reads
    r2 = I.read_identity(["HAEMATOLOGY REPORT\nName: Smt. Sunita Devi | UHID: SYN-500911 | Age / Sex: 67 Y / F"])
    assert r2["name"]["value"] == "Smt. Sunita Devi" and r2["ids"][0]["value"] == "SYN-500911" and r2["age"] == 67
