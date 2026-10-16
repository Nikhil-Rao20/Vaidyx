"""Indian-format SYNTHETIC test material for plan item V1-0.5 (imported by make_corpus.py).

Adds Case Files TB-004 (lung), TB-005 (breast), TB-006 (rectum), TB-007 (oral cavity, V1-9.1), TB-008 (cervix, V1-9.2) and a mixed department intake batch.
Every person, hospital, doctor, council registration number and ID here is invented. Every document carries the
"SYNTHETIC - DEMO ONLY" watermark (or the word SYNTHETIC in the header for Word / Excel / text files).
The schema of the answer key is documented in make_corpus.py.
"""
import json, random, shutil, time, zipfile, zlib
from pathlib import Path
from xml.sax.saxutils import escape

HOSP = "Sahyadri Cancer Institute (SYNTHETIC)"
HAND_FONT = Path("/usr/share/fonts/urw-base35/Z003-MediumItalic.otf")       # URW Z003, a chancery script font
DEVA_FONT = Path("/usr/share/fonts/google-droid/DroidSansDevanagari-Regular.ttf")
WM = "SYNTHETIC - DEMO ONLY"


def stable_seed(s):
    """Seed that is the same in every run (Python's hash() of a str changes per process)."""
    return zlib.crc32(s.encode()) % 10000


# ---- invented identifiers ----------------------------------------------------------------------------------------
_VD = [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 2, 3, 4, 0, 6, 7, 8, 9, 5], [2, 3, 4, 0, 1, 7, 8, 9, 5, 6], [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
       [4, 0, 1, 2, 3, 9, 5, 6, 7, 8], [5, 9, 8, 7, 6, 0, 4, 3, 2, 1], [6, 5, 9, 8, 7, 1, 0, 4, 3, 2], [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
       [8, 7, 6, 5, 9, 3, 2, 1, 0, 4], [9, 8, 7, 6, 5, 4, 3, 2, 1, 0]]
_VP = [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 5, 7, 6, 2, 8, 3, 0, 9, 4], [5, 8, 0, 3, 7, 9, 6, 1, 4, 2], [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
       [9, 4, 5, 3, 1, 2, 6, 8, 7, 0], [4, 2, 8, 6, 5, 7, 3, 9, 0, 1], [2, 7, 9, 3, 8, 0, 6, 4, 1, 5], [7, 0, 4, 6, 9, 1, 3, 2, 5, 8]]


def verhoeff_valid(num):
    c = 0
    for i, ch in enumerate(reversed(num)):
        c = _VD[c][_VP[i % 8][int(ch)]]
    return c == 0


def fake_aadhaar(first11):
    """A 12-digit number in Aadhaar layout that FAILS the Verhoeff checksum, so it can never be a real Aadhaar."""
    for last in "0123456789":
        if not verhoeff_valid(first11 + last):
            n = first11 + last
            return f"{n[:4]} {n[4:8]} {n[8:]}"


AADHAAR_RK = fake_aadhaar("60431187220")
AADHAAR_SD2 = fake_aadhaar("73958406118")

# ---- patients (all invented) --------------------------------------------------------------------------------------
P4 = dict(name="Ramesh Kumar", uhid="SYN-400118", cr_no="CR/2026/04118", ip_no="IP/26/09312", abha="91-4021-7788-3105",
          age_sex="58 Y / M", dob="14/03/1968", relation="S/o Mohan Lal", aadhaar=AADHAAR_RK)
P5 = dict(name="Sunita Devi", uhid="SYN-500263", abha="91-6730-2245-9018", age_sex="52 Y / F", dob="02/01/1974", relation="W/o Rajesh Prasad")
P5B = dict(name="Sunita Devi", uhid="SYN-500911", age_sex="67 Y / F", dob="11/07/1959", relation="W/o Late Ram Prakash", aadhaar=AADHAAR_SD2)
P6 = dict(name="Mohammed Irfan Shaikh", mrn="SYN-600744", ip_no="IP/26/18832", age_sex="61 Y / M", outside_id="DGH-26-071134")
P7 = dict(name="Manjunath Gowda", uhid="SYN-700352", abha="91-5512-0846-2271", age_sex="54 Y / M", relation="S/o Late Ningappa Gowda")
P8 = dict(name="Parvathi Naik", uhid="SYN-800415", abha="91-7283-5519-0634", age_sex="46 Y / F", relation="W/o Ramesh Naik")
# patients of the original demo cases, as their records would arrive in an intake batch
P1 = dict(name="Ramesh Kumar", uhid="SYN-100231", age_sex="62 Y / M")
P2 = dict(name="Lakshmi Iyer", uhid="SYN-200417", age_sex="48 Y / F")

LABELS = dict(name="Patient name", uhid="UHID", mrn="MRN", cr_no="CR No.", ip_no="IP No.", abha="ABHA No.", aadhaar="Aadhaar No.",
              age_sex="Age / Sex", dob="DOB", relation="Relation", outside_id="Hosp. No.")


def ident(p, name, keys, labels=None, values=None):
    """Header rows exactly as printed + the matching answer-key identity. `values` overrides how a value is printed."""
    labels, values = labels or {}, values or {}
    rows, truth = [(labels.get("name", LABELS["name"]), name)], {"name": name}
    for k in keys:
        v = values.get(k, p[k])
        rows.append((labels.get(k, LABELS[k]), v))
        truth[k] = v
    return rows, truth


# ---- HTML -------------------------------------------------------------------------------------------------------
CSS2 = """
@page { size: A4; margin: 14mm 14mm; }
body { font-family: 'DejaVu Sans', 'Liberation Sans', Arial, sans-serif; font-size: 10.5pt; color: #111; }
.hdr { border-bottom: 2px solid #1f3b63; padding-bottom: 6px; margin-bottom: 10px; }
.hdr .h { font-size: 15pt; font-weight: bold; color: #1f3b63; }
.hdr .d { font-size: 9.5pt; color: #444; }
.wm { position: fixed; top: 45%; left: 8%; font-size: 54pt; color: rgba(150,150,150,0.16); transform: rotate(-28deg); font-weight: bold; }
h1 { font-size: 13pt; margin: 6px 0 8px; }
h2 { font-size: 11pt; margin: 12px 0 4px; color: #1f3b63; }
table.pt td { padding: 2px 10px 2px 0; font-size: 10pt; }
table.res { border-collapse: collapse; width: 100%; margin-top: 4px; }
table.res th, table.res td { border-bottom: 1px solid #ccc; text-align: left; padding: 3px 6px; font-size: 10pt; }
table.grid { border-collapse: collapse; width: 100%; margin: 4px 0 10px; }
table.grid th { font-size: 8.5pt; font-weight: normal; text-align: left; color: #333; border: 1px solid #999; border-bottom: none; padding: 2px 5px 0; background: #f3f3f3; }
table.grid td { font-size: 10pt; font-weight: bold; border: 1px solid #999; border-top: none; padding: 1px 5px 3px; }
.foot { margin-top: 22px; border-top: 1px solid #999; padding-top: 6px; font-size: 10pt; }
.stamp { display: inline-block; border: 2px solid #333; padding: 3px 10px; font-weight: bold; margin-top: 6px; }
.nabl { font-size: 8.5pt; color: #444; margin-top: 10px; border-top: 1px dotted #999; padding-top: 4px; }
p { margin: 3px 0 6px; line-height: 1.35; }
.hi { font-family: 'TBDeva', 'Droid Sans', sans-serif; font-size: 11pt; }
.hand { font-family: 'TBHand', cursive; font-size: 16pt; color: #1b2a8a; margin: 10px 0 4px 18px; line-height: 1.6; }
.hand span { display: inline-block; }
.pb { page-break-after: always; }
.small { font-size: 9pt; }
"""
FONTS = ""
if HAND_FONT.exists():
    FONTS += f"@font-face {{ font-family: 'TBHand'; src: url('file://{HAND_FONT}'); }}\n"
if DEVA_FONT.exists():
    FONTS += f"@font-face {{ font-family: 'TBDeva'; src: url('file://{DEVA_FONT}'); }}\n"
HANDWRITING_METHOD = (f"script font {HAND_FONT.name} (URW Z003), dark blue ink, every word shifted off the baseline and resized at random, then scanned"
                      if HAND_FONT.exists() else "no script font installed: fallback font with per-word baseline shift, then scanned")


def wobble(text, seed):
    """Handwritten-style line: script font, every word off the baseline and of uneven size."""
    rnd = random.Random(seed)
    return "<div class='hand'>" + " ".join(
        f"<span style='position: relative; top: {rnd.uniform(-4, 4):.1f}px; font-size: {rnd.uniform(14.5, 18.5):.1f}pt'>{escape(w)}</span>"
        for w in text.split()) + "</div>"


def _table(c, cls="res"):
    head, *rows = c
    return (f"<table class='{cls}'><tr>" + "".join(f"<th>{h}</th>" for h in head) + "</tr>"
            + "".join("<tr>" + "".join(f"<td>{x}</td>" for x in r) + "</tr>" for r in rows) + "</table>")


def grid(pairs, per_row=3):
    """Labels ABOVE values (the boxed header of many Indian lab and radiology reports)."""
    out = "<table class='grid'>"
    for i in range(0, len(pairs), per_row):
        chunk = pairs[i:i + per_row]
        out += "<tr>" + "".join(f"<th>{k}</th>" for k, _ in chunk) + "</tr><tr>" + "".join(f"<td>{v}</td>" for _, v in chunk) + "</tr>"
    return out + "</table>"


def body_html(d):
    b = ""
    if d.get("id_rows") or d.get("meta"):
        b += "<table class='pt'>" + "".join(f"<tr><td><b>{k}</b></td><td>{v}</td></tr>" for k, v in d.get("id_rows", []) + d.get("meta", [])) + "</table>"
    if d.get("grid"):
        b += grid(d["grid"], d.get("grid_cols", 3))
    for head, c in d.get("sections", []):
        if head:
            b += f"<h2>{head}</h2>"
        if isinstance(c, list):
            b += _table(c)
        elif isinstance(c, dict):
            b += c["html"]
        else:
            b += "".join(f"<p>{line}</p>" for line in c.split("\n"))
    foot = "".join(f"<div>{line}</div>" for line in d.get("footer", []))
    if d.get("stamp"):
        foot += f"<div class='stamp'>{d['stamp']}</div>"
    if d.get("nabl"):
        foot += f"<div class='nabl'>{d['nabl']}</div>"
    return b + (f"<div class='foot'>{foot}</div>" if foot else "")


def html_page(d):
    sub = d.get("hosp_sub", "")
    return f"""<html><head><meta charset='utf-8'><style>{FONTS}{CSS2}</style></head><body>
<div class='wm'>{WM}</div>
<div class='hdr'><div class='h'>{d.get('hosp', HOSP)}</div>{f"<div class='d'>{sub}</div>" if sub else ""}<div class='d'>{d['dept']}</div></div>
<h1>{d['title']}</h1>{body_html(d)}</body></html>"""


# ---- footers -----------------------------------------------------------------------------------------------------
def signed(status, who, when):
    return [f"Report status: {status}", f"Reported by: {who} (electronically signed)", f"Signed: {when}"]


def sd(who, reg, when=None):
    out = ["*** End of report ***", "Sd/-", f"{who}, {reg}"]
    return out + ([f"Date: {when}"] if when else [])


NABL = "NABL accredited laboratory (ISO 15189:2022), Certificate No. MC-9917 (SYNTHETIC). Results relate only to the sample tested. Not valid for medico-legal purposes."


def lab_grid(idt_rows, reg, collected, reported, refby, sample_id):
    return [(k, v) for k, v in idt_rows] + [("Reg. date", reg), ("Collected on", collected), ("Reported on", reported), ("Ref. by", refby), ("Sample ID", sample_id)]


# ---- long discharge summary (about 24,700 characters) -------------------------------------------------------------
def long_discharge_sections():
    rnd = random.Random(4041)
    days = ["06/09/2026", "07/09/2026", "08/09/2026", "09/09/2026", "10/09/2026", "11/09/2026", "12/09/2026", "13/09/2026", "14/09/2026"]
    tmax = [101.2, 100.8, 100.4] + [98.6] * 6  # maximum temperature of each day (F): the Daily vitals table and the notes agree
    course = [
        "Admitted through the emergency department with haemoptysis (about 2 to 3 tablespoons of fresh blood over 24 hours), fever with chills for 4 days and breathlessness on exertion.",
        "Fever spikes persisted overnight (maximum 100.8 F). Sputum less blood-tinged. Blood cultures drawn before antibiotics, no growth so far.",
        "Last fever spike of 100.4 F in the early morning, afebrile since then. Cough with mucopurulent sputum, no fresh haemoptysis. Chest physiotherapy started. Tolerating oral diet.",
        "Clinically improving. Repeat chest radiograph shows partial resolution of right lower zone consolidation. Pre-procedure work-up for CT-guided biopsy sent.",
        "CT-guided core biopsy of the right lower lobe lesion done under local anaesthesia (3 cores, 18G). Post-procedure chest radiograph: no pneumothorax.",
        "Mild procedure-site pain, settled with paracetamol. No haemoptysis. Ambulating in the ward. Diet and sleep normal.",
        "Afebrile for more than 72 hours. Antibiotics changed to oral route as per sensitivity pattern of sputum culture (no significant growth).",
        "Stable. Counselled with family regarding the preliminary biopsy report, the pending final report and molecular tests, and outpatient review of the staging reports.",
        "Fit for discharge. Vitals stable, saturating well on room air. Discharge medications explained to patient and attendant (son).",
    ]
    secs = [
        ("Diagnosis at discharge", "1. Right lower lobe mass with post-obstructive pneumonia (treated).\n2. Haemoptysis, settled.\n3. Systemic hypertension.\n"
                                   "Biopsy: CT-guided core biopsy of the right lower lobe lesion done on 10/09/2026; preliminary report reads non-small cell carcinoma, favour adenocarcinoma; final report and PD-L1 awaited at the time of discharge."),
        ("Presenting complaints", "Cough for 2 months, haemoptysis for 10 days, fever with chills for 4 days, loss of appetite and loss of weight (about 5 kg in 2 months). "
                                  "No chest pain. No hoarseness of voice. No bone pain. No headache or seizures."),
        ("History of present illness", "The patient was apparently well 2 months ago, when he developed a dry cough, initially attributed to a seasonal infection and treated by a local practitioner "
                                       "with two courses of oral antibiotics and cough syrups without relief. The cough gradually became productive with whitish sputum. Ten days before admission he noticed "
                                       "streaks of blood in the sputum, increasing over the last 2 days to about 2 to 3 tablespoons of fresh blood per day. Four days before admission he developed fever with "
                                       "chills, more in the evenings, relieved by paracetamol. He also reports breathlessness on climbing one flight of stairs (mMRC grade 2), loss of appetite and weight loss "
                                       "of about 5 kg over 2 months. There is no history of chest pain, hoarseness of voice, difficulty in swallowing, swelling of the face or neck, bone pain, headache, "
                                       "vomiting, seizures or weakness of the limbs. He was seen at Kaveri Multispeciality Hospital (SYNTHETIC), Mandya, where a chest X-ray showed a right lower zone opacity, "
                                       "and was referred here. A CECT thorax was done in the Radio-diagnosis department of this hospital on 02/09/2026 at the request of the referring "
                                       "doctor, and he was first seen in the Medical Oncology OPD on 05/09/2026, the day before this admission."),
        ("Outside records reviewed", "Referral letter dated 30/08/2026 from Kaveri Multispeciality Hospital (SYNTHETIC). Chest X-ray PA view (outside, 28/08/2026): right lower zone opacity. "
                                     "Prescriptions of the local practitioner (two courses of oral antibiotics and cough syrups). No chest imaging older than this X-ray is available for comparison."),
        ("Past history", "Known hypertensive for 6 years on Tab. Telmisartan 40 mg once daily. Not a known diabetic. No history of tuberculosis or contact with tuberculosis. "
                         "No previous surgery. No known drug allergy."),
        ("Personal history", "Beedi smoker for 25 years, about 20 beedis per day; stopped 2 months ago. Occasional alcohol, stopped. Mixed diet. Works as a farmer. "
                             "Lives with wife and son in a rural area of Mandya district (fictional address details withheld)."),
        ("Family history", "No family history of malignancy. Father had hypertension."),
        ("General examination at admission", "Conscious, oriented, moderately built and nourished. Pallor present. No icterus, cyanosis, clubbing, lymphadenopathy or pedal oedema. "
                                             "Temperature 101 F, pulse 108 per minute, BP 146/88 mmHg, respiratory rate 24 per minute, SpO2 92% on room air."),
        ("Systemic examination at admission", "Respiratory system: bronchial breath sounds and coarse crepitations in the right infrascapular and infra-axillary areas; dull note on percussion over the right lower zone. "
                                              "Cardiovascular system: S1 S2 heard, no murmur. Abdomen: soft, non-tender, no organomegaly. Central nervous system: no focal neurological deficit."),
    ]
    for i, (day, note) in enumerate(zip(days, course), 1):
        t = min(round(rnd.uniform(98.2, 101.4) if i < 3 else rnd.uniform(97.8, 99.0), 1), tmax[i - 1])
        pr, sbp, dbp = rnd.randint(78, 108), rnd.randint(124, 148), rnd.randint(76, 90)
        spo2 = rnd.randint(92, 95) if i < 3 else rnd.randint(95, 98)
        rr = rnd.randint(16, 24)
        secs.append((f"Course in hospital, day {i} ({day})",
                     f"{note}\n"
                     f"Vitals: temperature {t} F, pulse {pr} per minute, BP {sbp}/{dbp} mmHg, respiratory rate {rr} per minute, SpO2 {spo2}% {'on 2 L/min oxygen by nasal prongs' if i < 3 else 'on room air'}. "
                     f"Intake {rnd.randint(1800, 2600)} mL, output {rnd.randint(1400, 2200)} mL.\n"
                     f"Systemic examination: chest {'coarse crepitations right lower zone' if i < 5 else 'occasional crepitations right lower zone, improving'}; cardiovascular system normal; abdomen soft; no neurological deficit.\n"
                     f"Medications given: Inj. Piperacillin-tazobactam 4.5 g IV 8-hourly {'(continued)' if i < 7 else '(stopped on day 7, changed to oral Tab. Amoxicillin-clavulanate 625 mg 8-hourly)'}; "
                     f"Inj. Tranexamic acid 500 mg IV 8-hourly {'(continued)' if i < 4 else '(stopped)'}; Tab. Telmisartan 40 mg once daily; Inj. Pantoprazole 40 mg IV once daily; "
                     f"Syp. Ascoril 10 mL thrice daily; Nebulisation with Ipratropium and Levosalbutamol 6-hourly; Tab. Paracetamol 650 mg SOS for fever or pain.\n"
                     f"Nursing: chest physiotherapy twice daily, incentive spirometry encouraged, fall-risk precautions, input-output charting maintained, {'oxygen weaned to room air in the morning' if i == 3 else 'no new nursing concern'}.\n"
                     f"Evening round: patient reviewed by the duty resident. {rnd.choice(['No fresh complaints.', 'Complains of mild cough at night, no blood.', 'Slept well, appetite improving.', 'Mild generalised weakness, no breathlessness at rest.'])} "
                     f"Chest auscultation unchanged from the morning. No new neurological symptom. Urine output adequate. Attendant (son) updated about the day's events and plan; questions answered.\n"
                     f"Investigations sent this day: {['CBC, renal and liver function, electrolytes, CRP, blood culture x 2, sputum culture, sputum AFB, HIV / HBsAg / HCV serology, ECG', 'Sputum AFB second sample, CBNAAT', 'CBC, renal and liver function, electrolytes, CRP, 2D echo, MRI brain with contrast', 'PT / INR, aPTT, blood grouping and typing, random blood sugar, HbA1c, whole body FDG PET/CT', 'CBC, renal and liver function, electrolytes, CRP, post-procedure chest radiograph', 'None', 'None', 'CBC, renal and liver function, electrolytes, CRP before discharge', 'None'][i - 1]}.\n"
                     f"Diet: {'soft diet, high protein, as per dietician' if i > 1 else 'nil by mouth for 6 hours, then liquids'}; oral fluid intake encouraged, about 2 litres per day. Bowel and bladder habits normal. Pain score {rnd.randint(0, 3)}/10.\n"
                     f"Plan as recorded by the treating unit: {'continue antibiotics, monitor for fresh haemoptysis, await cultures' if i < 4 else ('pre-procedure work-up for CT-guided biopsy' if i == 4 else ('post-biopsy monitoring' if i < 7 else 'continue oral antibiotics, plan discharge with outpatient review of the biopsy and staging reports'))}."))
    labs = [["Date", "Hb (gm%)", "TLC (cells/cumm)", "Platelets (lakhs/cumm)", "S. Creatinine (mg/dl)", "S. Sodium (mmol/L)", "CRP (mg/L)"],
            ["06/09/2026", "10.9", "16,800", "3.4", "1.2", "133", "96"], ["08/09/2026", "11.1", "13,200", "3.6", "1.0", "135", "54"],
            ["10/09/2026", "11.3", "9,700", "3.2", "0.9", "137", "21"], ["13/09/2026", "11.6", "8,100", "2.9", "0.9", "138", "8"]]
    secs += [
        ("Investigations (serial)", labs),
        ("Other investigations", "Blood culture (06/09/2026): no growth after 5 days. Sputum culture: normal oropharyngeal flora. Sputum for AFB (2 samples) and CBNAAT: negative, MTB not detected.\n"
                                 "Serology (06/09/2026): HIV I and II antibodies: Non-reactive. HBsAg: Non-reactive. Anti-HCV: Non-reactive.\n"
                                 "Coagulation (09/09/2026): PT 13.2 s (control 12.5 s), INR 1.05, aPTT 31 s. Random blood sugar 118 mg/dl. HbA1c 5.6%.\n"
                                 "ECG: sinus tachycardia on admission, normal on day 4. 2D echo: normal biventricular function, LVEF 60%.\n"
                                 "CECT thorax (02/09/2026, done in this hospital before admission): right lower lobe mass with post-obstructive consolidation and ipsilateral hilar and "
                                 "subcarinal nodes; report on file with Radio-diagnosis.\n"
                                 "MRI brain with contrast (08/09/2026) and whole body FDG PET/CT (09/09/2026) were done during this stay; the reports are on file with Radio-diagnosis "
                                 "and Nuclear Medicine and will be reviewed with the final biopsy report."),
        ("Consultations during the stay", "Cardiology (08/09/2026): fit for the planned procedure from the cardiac point of view; continue telmisartan. 2D echo normal.\n"
                                          "Physiotherapy (from 07/09/2026): chest physiotherapy twice daily, incentive spirometry, graded ambulation; exercise sheet given.\n"
                                          "Dietician (07/09/2026): high protein diet, small frequent meals, about 1,800 kcal and 70 g protein per day; diet chart in the local language given.\n"
                                          "Medical Oncology (12/09/2026): seen in the ward; the patient and family were told that the final biopsy report, PD-L1 and molecular tests are pending; outpatient review planned with the reports.\n"
                                          "Medical social worker (13/09/2026): explained the PM-JAY entitlement and documents needed for the pre-authorisation; family has the Ayushman card."),
        ("Counselling", "The diagnosis under evaluation, the biopsy procedure and its risks were explained to the patient and his son in Kannada. Written informed consent was taken before the biopsy. "
                        "The family was informed that the PET/CT and brain MRI done during this stay, the final biopsy report and the molecular tests on the biopsy will be reviewed together, and that the treatment plan "
                        "will be decided at the hospital's Tumour Board. Warning signs (fresh haemoptysis, fever, breathlessness, chest pain) and whom to contact were explained."),
        ("Liver function and other biochemistry", [["Date", "T. bilirubin (mg/dl)", "SGPT (U/L)", "SGOT (U/L)", "ALP (U/L)", "S. Albumin (gm/dl)", "S. Potassium (mmol/L)", "Blood urea (mg/dl)"],
                                                   ["06/09/2026", "0.9", "38", "41", "102", "3.3", "3.9", "36"], ["08/09/2026", "0.8", "35", "33", "98", "3.3", "4.1", "30"],
                                                   ["10/09/2026", "0.8", "31", "30", "95", "3.4", "4.2", "27"], ["13/09/2026", "0.7", "29", "27", "92", "3.6", "4.3", "24"]]),
        ("Daily vitals summary", [["Date", "Max temp (F)", "Pulse (per min)", "BP (mmHg)", "SpO2", "Oxygen"]] + [
            [d, f"{tmax[k]:.1f}", str(104 - 3 * k), f"{144 - 2 * k}/{88 - k}", f"{92 + min(k, 5)}%", "2 L/min" if k < 2 else "room air"] for k, d in enumerate(days)]),
        ("Risk assessments", "Fall risk (Morse scale) on admission: 35, moderate; fall precautions taken. Pressure injury risk (Braden scale): 19, low. "
                             "Venous thromboembolism risk assessed: mechanical prophylaxis with early ambulation; pharmacological prophylaxis withheld because of haemoptysis. "
                             "Nutrition screening (MUST): score 2, high risk; dietician referral done. Pain assessed every shift with the numeric rating scale. "
                             "No hospital-acquired infection. No blood transfusion was required during the stay. No adverse drug reaction was reported."),
        ("Medication administration summary", "Inj. Piperacillin-tazobactam 4.5 g IV 8-hourly from 06/09/2026 to 12/09/2026 (19 doses). Inj. Tranexamic acid 500 mg IV 8-hourly from 06/09/2026 to 09/09/2026. "
                                              "Tab. Amoxicillin-clavulanate 625 mg 8-hourly from 12/09/2026. Tab. Telmisartan 40 mg once daily throughout. Inj. Pantoprazole 40 mg IV once daily from 06/09/2026 to 11/09/2026, "
                                              "then oral. Nebulisation with Ipratropium and Levosalbutamol 6-hourly from 06/09/2026 to 10/09/2026, then as needed. Tab. Paracetamol 650 mg given 7 times in total for fever or pain. "
                                              "Inj. Lignocaine 2% (local) for the biopsy on 10/09/2026. No missed doses recorded in the medication chart."),
        ("Instructions given to the patient", "Take medicines as written in the medication list; do not stop telmisartan. Eat small frequent high-protein meals. Do not smoke beedis or cigarettes, and avoid "
                                              "second-hand smoke. Keep the biopsy site dry for 2 days. Walk inside the house several times a day and continue the breathing exercises taught by the physiotherapist. "
                                              "Bring all reports, including the outside chest X-ray film, the CT, MRI and PET/CT reports and the discharge summary, to the next visit. Keep the PM-JAY (Ayushman) card and identity proof ready for the pre-authorisation."),
        ("Procedure note", "10/09/2026: CT-guided core biopsy of the right lower lobe lesion. Consent taken. Local anaesthesia with 2% lignocaine. Three 18G cores obtained and sent for histopathology "
                           "and immunohistochemistry, with a request to save tissue for molecular testing. No immediate complication. Post-procedure chest radiograph: no pneumothorax."),
        ("Condition at discharge", "Afebrile, haemodynamically stable, no haemoptysis for 7 days, saturating 97% on room air, ambulant with assistance for longer distances.\n"
                                   "ECOG performance status at discharge: 2"),
        ("Medications at discharge", "1. Tab. Amoxicillin-clavulanate 625 mg three times daily for 5 more days.\n2. Tab. Telmisartan 40 mg once daily.\n"
                                     "3. Tab. Pantoprazole 40 mg once daily before breakfast for 2 weeks.\n4. Syp. Ascoril 10 mL three times daily for 5 days.\n5. Tab. Paracetamol 650 mg when required for fever or pain."),
        ("Follow-up", "Review in Medical Oncology OPD on 22/09/2026 with the biopsy report. Return earlier for fresh haemoptysis, fever or breathlessness."),
    ]
    return secs


# ---- 100-page outside records (image-only scan) -----------------------------------------------------------------
BIG_FACTS = {
    37: ("Colonoscopy report", "Date of procedure: 12/05/2026. Ulceroproliferative growth from 8 cm to 13 cm from the anal verge, involving three-quarters of the circumference. Biopsies taken."),
    62: ("Histopathology report", "Received: 13/05/2026. Reported: 15/05/2026. Endoscopic biopsy, rectal growth: Adenocarcinoma, well to moderately differentiated."),
    88: ("Laboratory report", "Collected on: 14/05/2026. CEA: 8.6 ng/mL (reference below 5.0)."),
}


def big_scan_pages():
    rnd = random.Random(6100)
    hosp = "Deccan General Hospital (SYNTHETIC), Hyderabad"
    who = "Md. Irfan Shaikh, 61 Y / M, Hosp. No. DGH-26-071134"
    pages = []
    for n in range(1, 101):
        head = f"<div class='hdr'><div class='h'>{hosp}</div><div class='d'>Case record, scanned copy. {who}. Page {n} of 100</div></div>"
        if n == 1:
            body = ("<h1>CASE RECORD (OUTSIDE HOSPITAL), SCANNED COPY</h1><p>Patient: Md. Irfan Shaikh S/o Abdul Kareem Shaikh. Age / Sex: 61 Y / M.</p>"
                    "<p>Hosp. No.: DGH-26-071134. Admission: 11/05/2026. Discharge: 18/05/2026.</p><p>Records handed over to the patient on request for treatment elsewhere.</p>")
        elif n == 2:
            body = "<h1>INDEX</h1>" + _table([["Section", "Pages"], ["Admission and consent forms", "3 - 12"], ["Progress notes", "13 - 36"], ["Colonoscopy", "37"],
                                               ["Nursing and medication charts", "38 - 61"], ["Histopathology", "62"], ["Nursing and medication charts", "63 - 87"],
                                               ["Laboratory", "88"], ["Discharge paperwork", "89 - 100"]])
        elif n in BIG_FACTS:
            t, txt = BIG_FACTS[n]
            body = f"<h1>{t.upper()}</h1><p>{txt}</p><p>Sd/- Consultant (signature illegible), Deccan General Hospital (SYNTHETIC)</p>"
        elif n <= 12:
            body = f"<h1>CONSENT AND ADMISSION FORM ({n - 2} of 10)</h1>" + "".join(
                f"<p>{i}. I have been explained the nature of the procedure, its risks and alternatives in a language I understand. Signature / thumb impression of patient or attendant: ________</p>" for i in range(1, 9))
        elif n <= 36:
            d = 11 + (n - 13) // 4
            body = f"<h1>PROGRESS NOTE</h1><p>Date: {d:02d}/05/2026, time {rnd.randint(7, 21):02d}:{rnd.choice(['00', '15', '30', '45'])}</p>" + "".join(
                f"<p>{x}</p>" for x in [f"Patient seen on rounds. Complaints: {rnd.choice(['bleeding per rectum reduced', 'tenesmus', 'no fresh complaints', 'mild abdominal discomfort'])}.",
                                        f"Pulse {rnd.randint(70, 96)} per minute, BP {rnd.randint(118, 140)}/{rnd.randint(70, 88)} mmHg, afebrile. Abdomen soft.",
                                        "Plan: continue the same management, review investigations."])
        elif n == 100:
            body = "<h1>END OF SCANNED RECORDS</h1><p>Total pages: 100. Certified true copy of the records issued on request (SYNTHETIC).</p>"
        elif n >= 89:
            body = f"<h1>DISCHARGE PAPERWORK ({n - 88} of 11)</h1><p>Billing and insurance (PM-JAY) paperwork. Package code and claim details on file (SYNTHETIC, no clinical content).</p>" + "".join(
                f"<p>Item {i}: ______________________ Amount: ________</p>" for i in range(1, 12))
        else:
            kind = rnd.choice(["NURSING CHART (VITALS)", "MEDICATION ADMINISTRATION RECORD", "INTAKE OUTPUT CHART"])
            rows = [["Time", "Temp (F)", "Pulse", "BP (mmHg)", "Resp. rate", "Initials"]] + [
                [f"{h:02d}:00", f"{rnd.uniform(97.6, 99.2):.1f}", str(rnd.randint(68, 98)), f"{rnd.randint(110, 142)}/{rnd.randint(68, 90)}", str(rnd.randint(14, 20)), rnd.choice(["SR", "MK", "PJ", "AN"])]
                for h in range(6, 24, 2)]
            body = f"<h1>{kind}</h1>" + _table(rows)
        pages.append(f"{head}{body}")
    return (f"<html><head><meta charset='utf-8'><style>{FONTS}{CSS2}</style></head><body><div class='wm'>{WM}</div>"  # fixed: repeats on every page
            + "".join(f"<div class='pb'>{p}</div>" if i < len(pages) - 1 else f"<div>{p}</div>" for i, p in enumerate(pages)) + "</body></html>")


# ---- Office files written by hand (zipped XML) -------------------------------------------------------------------
def write_docx(path, blocks):
    """blocks: ("p", text) | ("b", bold text) | ("table", rows). Minimal WordprocessingML package."""
    def run(t, bold=False):
        return f"<w:r>{'<w:rPr><w:b/></w:rPr>' if bold else ''}<w:t xml:space='preserve'>{escape(t)}</w:t></w:r>"
    body = ""
    for kind, c in blocks:
        if kind == "table":
            body += "<w:tbl><w:tblPr><w:tblW w:w='0' w:type='auto'/></w:tblPr>" + "".join(
                "<w:tr>" + "".join(f"<w:tc><w:p>{run(str(x))}</w:p></w:tc>" for x in r) + "</w:tr>" for r in c) + "</w:tbl>"
        else:
            body += f"<w:p>{run(c, kind == 'b')}</w:p>"
    doc = ("<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
           "<w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'><w:body>" + body + "<w:sectPr/></w:body></w:document>")
    ct = ("<?xml version='1.0' encoding='UTF-8' standalone='yes'?><Types xmlns='http://schemas.openxmlformats.org/package/2006/content-types'>"
          "<Default Extension='rels' ContentType='application/vnd.openxmlformats-package.relationships+xml'/><Default Extension='xml' ContentType='application/xml'/>"
          "<Override PartName='/word/document.xml' ContentType='application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml'/></Types>")
    rels = ("<?xml version='1.0' encoding='UTF-8' standalone='yes'?><Relationships xmlns='http://schemas.openxmlformats.org/package/2006/relationships'>"
            "<Relationship Id='rId1' Type='http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument' Target='word/document.xml'/></Relationships>")
    _zip(path, {"[Content_Types].xml": ct, "_rels/.rels": rels, "word/document.xml": doc})


def _col(i):
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def write_xlsx(path, rows, sheet="Report"):
    """rows: list of lists (str or number). Minimal SpreadsheetML package with inline strings."""
    def cell(ref, v):
        if isinstance(v, (int, float)):
            return f"<c r='{ref}'><v>{v}</v></c>"
        return f"<c r='{ref}' t='inlineStr'><is><t xml:space='preserve'>{escape(str(v))}</t></is></c>"
    data = "".join(f"<row r='{r + 1}'>" + "".join(cell(f"{_col(c)}{r + 1}", v) for c, v in enumerate(row) if v != "") + "</row>" for r, row in enumerate(rows))
    ws = ("<?xml version='1.0' encoding='UTF-8' standalone='yes'?><worksheet xmlns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'>"
          f"<sheetData>{data}</sheetData></worksheet>")
    wb = ("<?xml version='1.0' encoding='UTF-8' standalone='yes'?><workbook xmlns='http://schemas.openxmlformats.org/spreadsheetml/2006/main' "
          "xmlns:r='http://schemas.openxmlformats.org/officeDocument/2006/relationships'>"
          f"<sheets><sheet name='{escape(sheet)}' sheetId='1' r:id='rId1'/></sheets></workbook>")
    wbrels = ("<?xml version='1.0' encoding='UTF-8' standalone='yes'?><Relationships xmlns='http://schemas.openxmlformats.org/package/2006/relationships'>"
              "<Relationship Id='rId1' Type='http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet' Target='worksheets/sheet1.xml'/></Relationships>")
    ct = ("<?xml version='1.0' encoding='UTF-8' standalone='yes'?><Types xmlns='http://schemas.openxmlformats.org/package/2006/content-types'>"
          "<Default Extension='rels' ContentType='application/vnd.openxmlformats-package.relationships+xml'/><Default Extension='xml' ContentType='application/xml'/>"
          "<Override PartName='/xl/workbook.xml' ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml'/>"
          "<Override PartName='/xl/worksheets/sheet1.xml' ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml'/></Types>")
    rels = ("<?xml version='1.0' encoding='UTF-8' standalone='yes'?><Relationships xmlns='http://schemas.openxmlformats.org/package/2006/relationships'>"
            "<Relationship Id='rId1' Type='http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument' Target='xl/workbook.xml'/></Relationships>")
    _zip(path, {"[Content_Types].xml": ct, "_rels/.rels": rels, "xl/workbook.xml": wb, "xl/_rels/workbook.xml.rels": wbrels, "xl/worksheets/sheet1.xml": ws})


def _zip(path, parts):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, xml in parts.items():
            zi = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))  # fixed timestamp: reproducible bytes
            zi.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(zi, xml)


# ---- image renderers --------------------------------------------------------------------------------------------
def _render(pdf_path, page, scale, mode="L"):
    import pypdfium2 as pdfium
    return pdfium.PdfDocument(str(pdf_path))[page].render(scale=scale).to_pil().convert(mode)


def pdf_text(pdf_path):
    """Reference text (what a perfect reader would transcribe), from the PDF before it was turned into an image."""
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(str(pdf_path))
    return "\n\f\n".join(doc[i].get_textpage().get_text_range().replace("\r\n", "\n") for i in range(len(doc)))


def fix_known_lines(ref, known):
    """Put the answer-key text of the Hindi and handwritten lines into the reference text.

    pdfium extracts Devanagari with artefacts (U+0235 where the vowel sign of कि is reordered) and wraps long lines, while
    the rendered image is correct. A run of 1 to 3 extracted lines is replaced by the known line when, after dropping every
    character that does not occur in the known line, it equals the known line (whitespace ignored)."""
    lines = ref.split("\n")
    for k in known:
        chars, want = set(k), "".join(k.split())
        for i in range(len(lines)):
            hit = next((n for n in (1, 2, 3) if i + n <= len(lines)
                        and len(" ".join(lines[i:i + n])) <= len(k) + 8
                        and "".join(c for c in " ".join(lines[i:i + n]) if c in chars and not c.isspace()) == want), None)
            if hit:
                lines[i:i + hit] = [k]
                break
        else:
            raise ValueError(f"known line not found in the reference text: {k}")
    return "\n".join(lines)


def to_photo(pdf_path, png_path, seed):
    """Phone photo of a printed page: tilted, on a desk, with a shadow across one side, warm cast, soft focus."""
    from PIL import Image, ImageFilter
    import numpy as np
    rnd = random.Random(seed)
    im = _render(pdf_path, 0, 1.35, "RGB")
    w, h = im.size
    canvas = Image.new("RGB", (int(w * 1.12), int(h * 1.08)), (122, 96, 70))                    # wooden desk
    canvas.paste(im, (int(w * 0.06), int(h * 0.04)))
    canvas = canvas.rotate(rnd.uniform(2.5, 4.0), resample=Image.BICUBIC, expand=False, fillcolor=(110, 86, 62))
    a = np.asarray(canvas).astype(np.float32)
    H, W = a.shape[:2]
    yy, xx = np.mgrid[0:H, 0:W]
    shade = 0.58 + 0.42 * np.clip((xx / W) * 1.3 + (yy / H) * 0.2, 0, 1)                         # hand / phone shadow from the left
    a = a * shade[..., None] * np.array([1.0, 0.97, 0.88]) + np.random.default_rng(seed).normal(0, 4, a.shape)
    im = Image.fromarray(np.clip(a, 0, 255).astype("uint8")).filter(ImageFilter.GaussianBlur(0.6))
    im.save(png_path, optimize=True)


def to_big_scan(pdf_path, out_pdf, seed):
    """Image-only PDF: every page rasterised at about 86 dpi, greyscale, light noise, JPEG inside the PDF."""
    from PIL import Image, ImageFilter
    import numpy as np
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(str(pdf_path))
    rng, rnd = np.random.default_rng(seed), random.Random(seed)
    pages = []
    for i in range(len(doc)):
        im = doc[i].render(scale=1.2).to_pil().convert("L")
        im = im.rotate(rnd.uniform(-1.0, 1.0), resample=Image.BICUBIC, fillcolor=245)
        a = np.asarray(im).astype(np.float32) * 0.92 + 14 + rng.normal(0, 3, im.size[::-1])
        pages.append(Image.fromarray(np.clip(a, 0, 255).astype("uint8")).filter(ImageFilter.GaussianBlur(0.4)))
    fixed = time.strptime("2026-01-01", "%Y-%m-%d")  # fixed PDF dates: reproducible bytes
    pages[0].save(out_pdf, "PDF", save_all=True, append_images=pages[1:], resolution=86, quality=50, title="Scanned case record (SYNTHETIC)",
                  creationDate=fixed, modDate=fixed)


def corrupt_pdf(good_pdf, out, seed):
    """A file that starts like a PDF but is broken: first 1,200 bytes of a real PDF, then noise, no xref or trailer."""
    raw = Path(good_pdf).read_bytes()
    rnd = random.Random(seed)
    junk = bytes(rnd.randrange(256) for _ in range(9000)).replace(b"%%EOF", b"%%EOX").replace(b"xref", b"xrex").replace(b"trailer", b"trailex")
    Path(out).write_bytes(raw[:1200] + junk)


# =================================================================================================================
# CASE TB-004: lung (NSCLC). One patient, many departments, UHID / CR No. / ABHA and name variants. Hard documents.
# =================================================================================================================
_rk_opd_rows, _rk_opd_id = ident(P4, "Shri Ramesh Kumar", ["uhid", "abha", "age_sex", "dob"])
_rk_ct_rows, _rk_ct_id = ident(P4, "R. Kumar", ["cr_no", "age_sex"], values={"age_sex": "58Y/M"})
_rk_pet_rows, _rk_pet_id = ident(P4, "KUMAR RAMESH", ["uhid", "age_sex"], labels={"name": "Name"}, values={"age_sex": "58 yrs / Male"})
_rk_hp_rows, _rk_hp_id = ident(P4, "Mr. Ramesh Kumar", ["uhid", "cr_no", "age_sex"])
_rk_mol_rows, _rk_mol_id = ident(P4, "Ramesh Kumar", ["uhid", "age_sex"])
_rk_lab_rows, _rk_lab_id = ident(P4, "Mr. RAMESH KUMAR", ["uhid", "age_sex", "aadhaar"], labels={"name": "Name"})
_rk_ds_rows, _rk_ds_id = ident(P4, "KUMAR, RAMESH (Mr.)", ["uhid", "ip_no", "age_sex", "abha"])
_rk_mri_rows, _rk_mri_id = ident(P4, "Ramesh Kumar", ["uhid", "cr_no", "age_sex"])

C4 = [
 dict(path="medical_oncology/medical_oncology_opd_2026-09-05.pdf", fmt="pdf", dept="Department of Medical Oncology", title="MEDICAL ONCOLOGY OPD NOTE",
      id_rows=_rk_opd_rows, meta=[("Relation", P4["relation"]), ("Visit date", "05/09/2026"), ("Next review", "19/09/2026")],
      sections=[("Presenting complaints", "Cough for 2 months, blood in sputum for 10 days, weight loss of about 5 kg."),
                ("History", "Beedi smoker, 25 years, about 20 per day (25 pack-years equivalent), stopped 2 months ago. Hypertension on telmisartan 40 mg once daily."),
                ("Performance status", "ECOG performance status: 1"),
                ("Question for the Tumour Board", "Discussion of staging work-up and management plan after biopsy.")],
      footer=signed("FINAL", "Dr. Anand Kulkarni, MD, DM (Medical Oncology), KMC Reg. No. 71234", "05/09/2026 15:20"), stamp="FINAL / SIGNED",
      truth=dict(doc_type="clinical_note", status="FINAL", signed=True, fields={"ecog": "1", "smoking_history": "25 pack-years", "clinical_question": "staging work-up and management plan"},
                 report_date="2026-09-05", event_date="2026-09-05", event_label="visit date", identity=_rk_opd_id,
                 ignore_dates={"2026-09-19": "next review date", "1968-03-14": "date of birth"},
                 exercises=["Indian title Shri", "ABHA number", "DOB and next-review date must be ignored", "DD/MM/YYYY"])),
 dict(path="medical_oncology/referral_letter_2026-08-30.docx", fmt="docx",
      blocks=[("b", "Kaveri Multispeciality Hospital (SYNTHETIC), Mandya"), ("p", WM), ("b", "REFERRAL LETTER"),
              ("p", "Date: 30/08/2026"), ("p", "To: The Consultant, Department of Medical Oncology, Sahyadri Cancer Institute (SYNTHETIC)"),
              ("table", [["Patient name", "Ramesh Kumar S/o Mohan Lal"], ["Age / Sex", "58 Y / M"], ["Aadhaar No.", AADHAAR_RK], ["OP No.", "KMH/OP/26/55120"]]),
              ("p", "Respected Sir / Madam,"),
              ("p", "Kindly see this 58 year old gentleman, a beedi smoker, with cough for 2 months and blood-streaked sputum for 10 days. "
                    "Chest X-ray shows a right lower zone opacity. Referred for further evaluation and management."),
              ("p", "Thanking you."), ("p", "Sd/-"), ("p", "Dr. Harish Gowda, MBBS, MD (General Medicine), KMC Reg. No. 80211")],
      truth=dict(doc_type="referral", status="UNSTATED", signed=True, fields={},
                 report_date="2026-08-30", event_date=None, event_label=None,
                 identity={"name": "Ramesh Kumar", "relation": "S/o Mohan Lal", "age_sex": "58 Y / M", "aadhaar": AADHAAR_RK, "op_no_outside": "KMH/OP/26/55120"},
                 exercises=["Word .docx", "Aadhaar printed (must be masked, never used for matching)", "no status line", "Sd/- signature", "outside hospital OP number"])),
 dict(path="radio_diagnosis/cect_thorax_2026-09-02.pdf", fmt="pdf", dept="Department of Radio-diagnosis", title="CECT THORAX",
      grid=_rk_ct_rows + [("Study date", "02/09/2026"), ("Reported on", "03/09/2026"), ("Ref. by", "Dr. Harish Gowda (Kaveri Multispeciality Hospital, Mandya)")],
      sections=[("Findings", "Lobulated soft tissue mass in the superior segment of the right lower lobe measuring 4.6 x 3.8 cm with post-obstructive consolidation.\n"
                             "Enlarged right hilar node (1.6 cm) and subcarinal node (1.4 cm short axis). No contralateral mediastinal node.\n"
                             "No pleural effusion. Liver and adrenals in the imaged sections normal. No destructive bone lesion."),
                ("Impression (reporting radiologist)", "Right lower lobe mass with ipsilateral hilar and subcarinal lymphadenopathy.")],
      footer=signed("FINAL", "Dr. Shalini Rao, MD (Radio-diagnosis), KMC Reg. No. 66310", "03/09/2026 11:45"), stamp="FINAL / SIGNED",
      truth=dict(doc_type="ct", status="FINAL", signed=True, fields={"lesion_size": "4.6 x 3.8 cm", "nodal_findings": "right hilar"},
                 report_date="2026-09-03", event_date="2026-09-02", event_label="study date", identity=_rk_ct_id,
                 exercises=["name as initial R. Kumar", "CR No. only (no UHID)", "label above the date (boxed table header)", "study date differs from report date"])),
 dict(path="radio_diagnosis/mri_brain_2026-09-08.pdf", fmt="corrupt", dept="Department of Radio-diagnosis", title="MRI BRAIN WITH CONTRAST",
      id_rows=_rk_mri_rows, meta=[("Study date", "08/09/2026")],
      sections=[("Findings", "No enhancing intracranial lesion.")], footer=signed("FINAL", "Dr. Shalini Rao, MD (Radio-diagnosis), KMC Reg. No. 66310", "08/09/2026 18:10"),
      truth=dict(doc_type="mri", status=None, signed=None, fields={}, expected="failed", report_date=None, event_date=None, event_label=None, identity={},
                 exercises=["corrupted PDF: must fail cleanly and be listed as a failed document; the brain MRI requirement stays open"])),
 dict(path="nuclear_medicine/pet_ct_2026-09-09_phone_photo.png", fmt="photo", dept="Department of Nuclear Medicine", title="WHOLE BODY 18F-FDG PET/CT",
      id_rows=_rk_pet_rows, meta=[("Study date", "09/09/2026"), ("Reported on", "10/09/2026")],
      sections=[("Findings (as recorded by the reporting physician)", "Primary: FDG-avid right lower lobe mass, 4.7 cm, SUVmax 11.6.\n"
                                                                     "Nodes: FDG-avid right hilar (SUVmax 6.2) and subcarinal (SUVmax 5.1) nodes.\nDistant: no FDG-avid distant metastatic disease."),
                ("Staging as recorded in this report", "cT2b N2 M0, Stage IIIA (AJCC 8th edition)")],
      footer=signed("FINAL", "Dr. Venkat Reddy, MD (Nuclear Medicine), KMC Reg. No. 58842", "10/09/2026 16:30"), stamp="FINAL / SIGNED",
      truth=dict(doc_type="pet_ct", status="FINAL", signed=True, fields={"suv_max": "11.6", "recorded_stage": "cT2b N2 M0, Stage IIIA"},
                 report_date="2026-09-10", event_date="2026-09-09", event_label="study date", identity=_rk_pet_id,
                 exercises=["phone photo (tilted, shadowed, on a desk)", "surname-first name in capitals", "58 yrs / Male"])),
 dict(path="pathology/histopathology_2026-09-11_preliminary.pdf", fmt="pdf", dept="Department of Pathology", title="HISTOPATHOLOGY REPORT",
      id_rows=_rk_hp_rows, meta=[("Specimen", "CT-guided core biopsy, right lower lobe lesion"), ("Received on", "10/09/2026"), ("Lab No.", "HP/2026/7731")],
      sections=[("Microscopy", "Cores show sheets and nests of malignant epithelial cells with focal gland formation, in a desmoplastic stroma."),
                ("Diagnosis", "Non-small cell carcinoma, favour adenocarcinoma."),
                ("Immunohistochemistry", [["Marker", "Result"], ["TTF-1", "Positive"], ["Napsin A", "Positive"], ["p40", "Negative"], ["PD-L1 (22C3) TPS", "Awaited"]]),
                ("Molecular testing", "Tissue preserved for EGFR / ALK / ROS1, sent to Molecular Pathology.")],
      footer=["Report status: PRELIMINARY (PD-L1 awaited)", "Reported by: Dr. Fatima Begum, MD (Pathology), KMC Reg. No. 62290 (electronically signed)", "Signed: 11/09/2026 17:05"],
      stamp="PRELIMINARY",
      truth=dict(doc_type="histopathology", status="PRELIMINARY", signed=True, fields={"histologic_type": "Non-small cell carcinoma, favour adenocarcinoma", "pdl1": None},
                 report_date="2026-09-11", event_date="2026-09-10", event_label="received on", identity=_rk_hp_id,
                 not_negations=["Non-small cell carcinoma"], pending=["PD-L1 (22C3) TPS: Awaited"],
                 exercises=["'Non-small cell carcinoma' is a diagnosis, not a negation", "pending value 'Awaited'", "PRELIMINARY status", "UHID and CR No. both printed"])),
 dict(path="molecular_pathology/egfr_alk_ros1_2026-09-16.pdf", fmt="pdf", dept="Department of Molecular Pathology", title="MOLECULAR PATHOLOGY REPORT",
      id_rows=_rk_mol_rows, meta=[("Specimen", "FFPE block HP/2026/7731 (biopsy received 10/09/2026)"), ("Reported on", "16/09/2026")],
      sections=[("Results", [["Test", "Method", "Result"], ["EGFR (exons 18 to 21)", "Real-time PCR", "Not detected"], ["ALK", "IHC (D5F3)", "Negative"],
                             ["ROS1", "IHC (D4D6)", "Negative"], ["KRAS G12C", "Real-time PCR", "Not detected"]]),
                ("Comment", "No EGFR sensitising mutation detected in the tested exons.")],
      footer=sd("Dr. Neha Joshi, MD (Pathology), PDF (Molecular Pathology)", "KMC Reg. No. 73305", "16/09/2026"),
      truth=dict(doc_type="molecular", status="FINAL", signed=True, fields={"egfr": "Not detected", "alk": "Negative", "ros1": "Negative", "kras": "Not detected"},
                 report_date="2026-09-16", event_date="2026-09-10", event_label="specimen (biopsy) date", identity=_rk_mol_id,
                 negated=["EGFR: Not detected", "KRAS G12C: Not detected"],
                 exercises=["negated value 'Not detected' is a real result", "Sd/- with KMC Reg. No.", "End of report marker (no status line)"])),
 dict(path="laboratory_medicine/cbc_2026-09-05.png", fmt="scan", dept="Department of Laboratory Medicine", title="HAEMATOLOGY REPORT",
      grid=lab_grid(_rk_lab_rows, "05/09/2026 08:02", "05/09/2026 08:10", "05/09/2026 12:40", "Dr. Anand Kulkarni", "LAB/26/118392"),
      sections=[("Complete blood count", [["Investigation", "Result", "Units", "Biological ref. interval"], ["Haemoglobin", "12.6", "gm%", "13.0 - 17.0"],
                                          ["Total leucocyte count (TLC)", "8,200", "cells/cumm", "4,000 - 11,000"], ["Platelet count", "2.4", "lakhs/cumm", "1.5 - 4.1"],
                                          ["ESR", "48", "mm/1st hr", "0 - 20"]])],
      footer=sd("Dr. Suresh Babu, MD (Pathology)", "KMC Reg. No. 69021"), nabl=NABL,
      truth=dict(doc_type="lab", status="FINAL", signed=True, fields={"haemoglobin": "12.6", "wbc": "8,200", "platelets": "2.4"},
                 report_date="2026-09-05", event_date="2026-09-05", event_label="collected on", identity=_rk_lab_id,
                 exercises=["Reg. date / Collected on / Reported on", "gm%, TLC, lakhs/cumm", "Aadhaar printed in the header (must be masked)", "NABL footer", "End of report + Sd/-", "label above the date"])),
 dict(path="laboratory_medicine/biochemistry_2026-09-05.xlsx", fmt="xlsx",
      rows=[[HOSP + ", Department of Biochemistry"], [WM], ["BIOCHEMISTRY REPORT (LIS export)"],
            ["Name", "Ramesh Kumar", "UHID", P4["uhid"]], ["Age / Sex", "58 Y / M", "Sample ID", "LAB/26/118393"],
            ["Reg. date", "05/09/2026", "Collected on", "05/09/2026", "Reported on", "05/09/2026"], [],
            ["Investigation", "Result", "Units", "Biological ref. interval"],
            ["S. Creatinine", 1.1, "mg/dl", "0.7 - 1.3"], ["Blood urea", 31, "mg/dl", "15 - 40"], ["Total bilirubin", 0.8, "mg/dl", "0.2 - 1.2"],
            ["SGPT (ALT)", 34, "U/L", "< 41"], ["SGOT (AST)", 29, "U/L", "< 40"], ["S. Albumin", 3.6, "gm/dl", "3.5 - 5.2"], ["S. Sodium", 136, "mmol/L", "135 - 145"], [],
            ["Report status: FINAL"], ["Verified by: Dr. R. Pillai, MD (Biochemistry), KMC Reg. No. 70418"]],
      truth=dict(doc_type="lab", status="FINAL", signed=True, fields={"creatinine": "1.1", "bilirubin": "0.8"},
                 report_date="2026-09-05", event_date="2026-09-05", event_label="collected on", identity={"name": "Ramesh Kumar", "uhid": P4["uhid"], "age_sex": "58 Y / M"},
                 exercises=["Excel .xlsx (read or reject clearly, item 1.4)", "numbers stored as numbers, not text"])),
 dict(path="discharge/discharge_summary_2026-09-14.pdf", fmt="pdf", dept="Department of Pulmonary Medicine", title="DISCHARGE SUMMARY",
      id_rows=_rk_ds_rows, meta=[("Date of admission", "06/09/2026"), ("Date of discharge", "14/09/2026"), ("Consultant", "Dr. Prakash Hegde (Pulmonary Medicine)")],
      sections=long_discharge_sections(),
      footer=signed("FINAL", "Dr. Prakash Hegde, MD (Pulmonary Medicine), KMC Reg. No. 64487", "14/09/2026 13:30"), stamp="FINAL / SIGNED",
      truth=dict(doc_type="discharge_summary", status="FINAL", signed=True, fields={"ecog": "2"},
                 report_date="2026-09-14", event_date="2026-09-06", event_end="2026-09-14", event_label="admission to discharge", identity=_rk_ds_id,
                 other_values={"hiv": "Non-reactive", "hbsag": "Non-reactive", "anti_hcv": "Non-reactive"},
                 not_negations=["HIV I and II antibodies: Non-reactive", "non-small cell carcinoma"],
                 ignore_dates={"2026-09-22": "follow-up review date"},
                 exercises=["very long document (about 24,700 characters) with the ECOG value near the end", "'HIV non-reactive' is a result, not a negation",
                            "ECOG 2 here conflicts with ECOG 1 in the OPD note of 05/09/2026 (later document)", "surname-first name"])),
]
_rk_hp2_rows, _rk_hp2_id = ident(P4, "Mr. Ramesh Kumar", ["uhid", "cr_no", "age_sex"])
_rk_cbc2_rows, _rk_cbc2_id = ident(P4, "Ramesh Kumar", ["uhid", "age_sex"])
A4 = [
 dict(path="pathology/histopathology_2026-09-18_amended.pdf", fmt="pdf", dept="Department of Pathology", title="HISTOPATHOLOGY REPORT (AMENDED REPORT)",
      id_rows=_rk_hp2_rows, meta=[("Specimen", "CT-guided core biopsy, right lower lobe lesion"), ("Received on", "10/09/2026"), ("Lab No.", "HP/2026/7731"),
                                  ("Amends", "Preliminary report of 11/09/2026")],
      sections=[("Diagnosis", "Adenocarcinoma, lung, acinar predominant (non-small cell carcinoma)."),
                ("Immunohistochemistry", [["Marker", "Result"], ["TTF-1", "Positive"], ["Napsin A", "Positive"], ["p40", "Negative"], ["PD-L1 (22C3) TPS", "55%"]]),
                ("Reason for amendment", "PD-L1 result added; diagnosis refined after review of additional levels.")],
      footer=["Report status: AMENDED", "Reported by: Dr. Fatima Begum, MD (Pathology), KMC Reg. No. 62290 (electronically signed)", "Signed: 18/09/2026 12:15"], stamp="AMENDED / SIGNED",
      truth=dict(doc_type="histopathology", status="AMENDED", signed=True, fields={"histologic_type": "Adenocarcinoma", "pdl1": "55%"},
                 report_date="2026-09-18", event_date="2026-09-10", event_label="received on", identity=_rk_hp2_id, supersedes="pathology/histopathology_2026-09-11_preliminary.pdf",
                 exercises=["AMENDED status", "conflicting values across versions (diagnosis refined, PD-L1 Awaited then 55%)"])),
 dict(path="laboratory_medicine/cbc_2026-09-19.pdf", fmt="pdf", dept="Department of Laboratory Medicine", title="HAEMATOLOGY REPORT",
      grid=lab_grid(_rk_cbc2_rows, "19/09/2026 08:30", "19/09/2026 08:41", "19/09/2026 13:02", "Dr. Anand Kulkarni", "LAB/26/121007"),
      sections=[("Complete blood count", [["Investigation", "Result", "Units", "Biological ref. interval"], ["Haemoglobin", "11.9", "gm%", "13.0 - 17.0"],
                                          ["Total leucocyte count (TLC)", "7,600", "cells/cumm", "4,000 - 11,000"], ["Platelet count", "2.1", "lakhs/cumm", "1.5 - 4.1"]])],
      footer=sd("Dr. Suresh Babu, MD (Pathology)", "KMC Reg. No. 69021"), nabl=NABL,
      truth=dict(doc_type="lab", status="FINAL", signed=True, fields={"haemoglobin": "11.9", "wbc": "7,600", "platelets": "2.1"},
                 report_date="2026-09-19", event_date="2026-09-19", event_label="collected on", identity=_rk_cbc2_id, supersedes_values_of="laboratory_medicine/cbc_2026-09-05.png",
                 exercises=["newer report arriving later with different values (latest wins)"])),
 dict(path="radio_diagnosis/mri_brain_2026-09-20.pdf", fmt="pdf", dept="Department of Radio-diagnosis", title="MRI BRAIN WITH CONTRAST",
      id_rows=_rk_mri_rows, meta=[("Study date", "20/09/2026")],
      sections=[("Findings", "No enhancing intracranial lesion. No perilesional oedema. Ventricles and sulci normal for age."),
                ("Impression (reporting radiologist)", "No evidence of intracranial metastasis.")],
      footer=signed("FINAL", "Dr. Shalini Rao, MD (Radio-diagnosis), KMC Reg. No. 66310", "20/09/2026 19:05"), stamp="FINAL / SIGNED",
      truth=dict(doc_type="mri", status="FINAL", signed=True, fields={}, report_date="2026-09-20", event_date="2026-09-20", event_label="study date", identity=_rk_mri_id,
                 exercises=["readable replacement for the corrupted MRI"])),
]

# =================================================================================================================
# CASE TB-005: breast. Hindi line + handwriting, cancelled and corrected reports, unsigned report, HER2 non-amplified,
# HIV non-reactive, and a board record with a 6 mg vs 60 mg slip.
# =================================================================================================================
_sd_opd_rows, _sd_opd_id = ident(P5, "Smt. Sunita Devi", ["relation", "uhid", "age_sex"], labels={"relation": ""})
_sd_usg_rows, _sd_usg_id = ident(P5, "Sunita Devi", ["uhid", "age_sex"])
_sd_hp_rows, _sd_hp_id = ident(P5, "Mrs. Sunita Devi", ["uhid", "abha", "age_sex"])
_sd_ct_rows, _sd_ct_id = ident(P5, "SUNITA DEVI", ["uhid", "age_sex"])
_sd_lab_rows, _sd_lab_id = ident(P5, "Smt. Sunita Devi", ["uhid", "age_sex", "dob"], labels={"name": "Name"})
HINDI_LINE = "मरीज़ ने बताया कि बाएँ स्तन में गांठ चार महीने से है।"
HAND_NOTE = "Pt and husband counselled. Prefers breast conservation if feasible. Review on 17/09/2026"
DECISION_TEXT = ("Neoadjuvant chemotherapy: 4 cycles of AC (Inj. Doxorubicin 6 mg/m2 IV and Inj. Cyclophosphamide 600 mg/m2 IV, every 21 days), "
                 "followed by Inj. Paclitaxel 80 mg/m2 IV weekly for 12 weeks. Response assessment with MRI breast after chemotherapy, then surgery "
                 "(breast conservation if response permits) and adjuvant radiotherapy. Endocrine therapy as per receptor status after surgery.")
BOARD_DECISION = {"document": "tumour_board/tumour_board_record_2026-09-24.pdf", "board_date": "2026-09-24", "text": DECISION_TEXT,
                  "dose_slips": [{"drug": "Doxorubicin", "regimen": "AC", "written": "6 mg/m2", "reference": "60 mg/m2", "kind": "tenfold low (missing zero)"}],
                  "absent_specialties": ["Radiation Oncology"], "note": "Planted error for adjudication tests; the board record is fictional."}

C5 = [
 dict(path="surgical_oncology/surgical_oncology_opd_2026-09-03.png", fmt="scan", dept="Department of Surgical Oncology", title="SURGICAL ONCOLOGY OPD",
      id_rows=_sd_opd_rows, meta=[("Visit date", "03/09/2026")],
      sections=[("History", "Painless lump in the left breast. Postmenopausal (menopause at 49 years). No family history of breast or ovarian cancer.\n"
                            "Hypothyroidism on thyroxine 50 mcg once daily."),
                ("", {"html": f"<p class='hi'>{HINDI_LINE}</p>"}),
                ("Examination", "Left breast: 3.5 x 3 cm hard lump, upper outer quadrant, not fixed to chest wall. Left axilla: one mobile node, about 1.5 cm."),
                ("Performance status", "ECOG performance status: 0"),
                ("Question for the Tumour Board", "Discussion of the treatment sequence."),
                ("", {"html": wobble(HAND_NOTE, 5051)})],
      footer=["Sd/-", "Dr. Pooja Hegde, MS, MCh (Surgical Oncology), KMC Reg. No. 90577"],
      truth=dict(doc_type="clinical_note", status="UNSTATED", signed=True, fields={"ecog": "0", "menopausal_status": "Postmenopausal", "clinical_question": "treatment sequence"},
                 report_date="2026-09-03", event_date="2026-09-03", event_label="visit date", identity=_sd_opd_id,
                 hindi_lines=[HINDI_LINE], hindi_meaning_for_testers="Patient says the lump in the left breast has been there for four months (do NOT turn into a fact).",
                 handwritten_lines=[HAND_NOTE], handwriting_method=HANDWRITING_METHOD, ignore_dates={"2026-09-17": "review date (handwritten)"},
                 exercises=["Hindi (Devanagari) line: transcribe as is and flag, never translate into facts", "handwritten-style note", "no status line, Sd/- signature",
                            "title Smt. and W/o relation", "scanned image"])),
 dict(path="radio_diagnosis/usg_breast_2026-08-27_cancelled.pdf", fmt="pdf", dept="Department of Radio-diagnosis", title="ULTRASOUND BOTH BREASTS: REPORT CANCELLED",
      id_rows=_sd_usg_rows, meta=[("Study date", "27/08/2026")],
      sections=[("Notice", "This report cancelled: findings were entered under the wrong side. See the corrected report dated 28/08/2026."),
                ("Findings (cancelled text)", "Right breast: irregular hypoechoic lesion 2.6 x 2.1 cm at 10 o'clock.")],
      footer=["Report status: CANCELLED", "Cancelled by: Dr. Shalini Rao, MD (Radio-diagnosis), KMC Reg. No. 66310 (electronically signed)", "Signed: 28/08/2026 09:10"], stamp="CANCELLED",
      truth=dict(doc_type="ultrasound", status="CANCELLED", signed=True, fields={}, report_date="2026-08-28", event_date="2026-08-27", event_label="study date", identity=_sd_usg_id,
                 superseded_by="radio_diagnosis/usg_mammo_2026-08-28_corrected.pdf",
                 exercises=["CANCELLED report must never count; its wrong-side finding must not be used"])),
 dict(path="radio_diagnosis/usg_mammo_2026-08-28_corrected.pdf", fmt="pdf", dept="Department of Radio-diagnosis", title="MAMMOGRAPHY AND ULTRASOUND BOTH BREASTS (CORRECTED REPORT)",
      id_rows=_sd_usg_rows, meta=[("Study date", "27/08/2026"), ("Replaces", "Report of 27/08/2026 (cancelled)")],
      sections=[("Findings", "Left breast, upper outer quadrant (2 o'clock): irregular spiculated hypoechoic mass 2.6 x 2.1 cm.\nLeft axilla: one node with thickened cortex, 1.5 cm.\nRight breast: no suspicious lesion."),
                ("Assessment (reporting radiologist)", "Left breast BI-RADS 5. Right breast BI-RADS 1.")],
      footer=["Report status: CORRECTED", "Reported by: Dr. Shalini Rao, MD (Radio-diagnosis), KMC Reg. No. 66310 (electronically signed)", "Signed: 28/08/2026 10:05"], stamp="CORRECTED / SIGNED",
      truth=dict(doc_type="mammogram", status="CORRECTED", signed=True, fields={"lesion_size": "2.6 x 2.1 cm", "birads": "BI-RADS 5"},
                 report_date="2026-08-28", event_date="2026-08-27", event_label="study date", identity=_sd_usg_id,
                 exercises=["CORRECTED status counts as final", "study date earlier than report date"])),
 dict(path="pathology/core_biopsy_2026-08-31.pdf", fmt="pdf", dept="Department of Pathology", title="HISTOPATHOLOGY REPORT",
      id_rows=_sd_hp_rows, meta=[("Specimen", "USG-guided core biopsy, left breast mass"), ("Received on", "29/08/2026"), ("Lab No.", "HP/2026/7490")],
      sections=[("Diagnosis", "Invasive breast carcinoma of no special type (ductal)."),
                ("Grade", "Modified Bloom-Richardson (Nottingham) grade 2 (score 6/9)."),
                ("Lymphovascular invasion", "Not identified.")],
      footer=signed("FINAL", "Dr. Fatima Begum, MD (Pathology), KMC Reg. No. 62290", "31/08/2026 16:20"), stamp="FINAL / SIGNED",
      truth=dict(doc_type="histopathology", status="FINAL", signed=True, fields={"histologic_type": "Invasive breast carcinoma of no special type", "grade": "grade 2", "lvi": "Not identified"},
                 report_date="2026-08-31", event_date="2026-08-29", event_label="received on", identity=_sd_hp_id, negated=["Lymphovascular invasion: Not identified"],
                 exercises=["ABHA number printed", "negated value 'Not identified'"])),
 dict(path="pathology/ihc_2026-09-04.pdf", fmt="pdf", dept="Department of Pathology", title="IMMUNOHISTOCHEMISTRY REPORT",
      id_rows=_sd_hp_rows, meta=[("Specimen", "Block HP/2026/7490"), ("Reported on", "04/09/2026")],
      sections=[("Results", [["Marker", "Result"], ["Estrogen receptor (ER)", "Positive, 80% (Allred 7)"], ["Progesterone receptor (PR)", "Positive, 40% (Allred 5)"],
                             ["HER2 (IHC)", "2+ (equivocal); sent for FISH"], ["Ki-67", "30%"]])],
      footer=signed("FINAL", "Dr. Fatima Begum, MD (Pathology), KMC Reg. No. 62290", "04/09/2026 14:00"), stamp="FINAL / SIGNED",
      truth=dict(doc_type="ihc", status="FINAL", signed=True, fields={"er": "80%", "pr": "40%", "her2": "2+", "ki67": "30%"},
                 report_date="2026-09-04", event_date=None, event_label=None, identity=_sd_hp_id, exercises=["receptor values"])),
 dict(path="molecular_pathology/her2_fish_2026-09-10.pdf", fmt="pdf", dept="Department of Molecular Pathology", title="HER2 FISH REPORT",
      id_rows=_sd_hp_rows, meta=[("Specimen", "Block HP/2026/7490"), ("Relates to", "IHC report of 04/09/2026")],
      sections=[("Result", "HER2/CEP17 ratio: 1.4. Average HER2 copy number: 3.2 signals per cell.\nInterpretation: HER2 non-amplified (ASCO/CAP 2023, group 5)."),
                ("Final HER2 status", "HER2 negative (IHC 2+, FISH non-amplified).")],
      footer=sd("Dr. Neha Joshi, MD (Pathology), PDF (Molecular Pathology)", "KMC Reg. No. 73305", "10/09/2026"),
      truth=dict(doc_type="molecular", status="FINAL", signed=True, fields={"her2": "non-amplified"},
                 report_date="2026-09-10", event_date=None, event_label=None, identity=_sd_hp_id, not_negations=["HER2 non-amplified"],
                 exercises=["'HER2 non-amplified' is a result, not a negation of HER2", "conflicting HER2 values across documents (2+ then non-amplified / negative)"])),
 dict(path="radio_diagnosis/cect_thorax_abdomen_2026-09-06.pdf", fmt="pdf", dept="Department of Radio-diagnosis", title="CECT THORAX AND ABDOMEN (STAGING)",
      grid=_sd_ct_rows + [("Study date", "06/09/2026"), ("Ref. by", "Dr. Pooja Hegde")], grid_cols=4,
      sections=[("Findings", "Lungs clear. No mediastinal lymphadenopathy. Liver normal in size, no focal lesion. Adrenals normal. No ascites. No lytic or sclerotic bone lesion."),
                ("Impression", "No evidence of distant metastasis in the thorax or abdomen.")],
      truth=dict(doc_type="ct", status="UNSTATED", signed=False, fields={"distant_findings": "No evidence of distant metastasis"},
                 report_date=None, event_date="2026-09-06", event_label="study date", identity=_sd_ct_id,
                 exercises=["no status line and no signature at all (unsigned)", "report date not printed"])),
 dict(path="laboratory_medicine/cbc_rft_serology_2026-09-03.pdf", fmt="pdf", dept="Department of Laboratory Medicine", title="LABORATORY INVESTIGATION REPORT",
      grid=lab_grid(_sd_lab_rows, "03/09/2026 09:12", "03/09/2026 09:20", "03/09/2026 15:45", "Dr. Pooja Hegde", "LAB/26/118011"),
      sections=[("Haematology", [["Investigation", "Result", "Units", "Biological ref. interval"], ["Haemoglobin", "11.4", "gm%", "12.0 - 15.0"],
                                  ["Total leucocyte count (TLC)", "6,900", "cells/cumm", "4,000 - 11,000"], ["Platelet count", "3.1", "lakhs/cumm", "1.5 - 4.1"]]),
                ("Renal function", [["Investigation", "Result", "Units", "Biological ref. interval"], ["S. Creatinine", "0.7", "mg/dl", "0.5 - 1.1"], ["Blood urea", "24", "mg/dl", "15 - 40"]]),
                ("Serology", [["Investigation", "Result", "Method"], ["HIV I and II antibodies", "Non-reactive", "CLIA"], ["HBsAg", "Non-reactive", "CLIA"], ["Anti-HCV", "Non-reactive", "CLIA"]])],
      footer=sd("Dr. Suresh Babu, MD (Pathology)", "KMC Reg. No. 69021"), nabl=NABL,
      truth=dict(doc_type="lab", status="FINAL", signed=True, fields={"haemoglobin": "11.4", "wbc": "6,900", "platelets": "3.1", "creatinine": "0.7"},
                 report_date="2026-09-03", event_date="2026-09-03", event_label="collected on", identity=_sd_lab_id,
                 other_values={"hiv": "Non-reactive", "hbsag": "Non-reactive", "anti_hcv": "Non-reactive"}, not_negations=["HIV I and II antibodies: Non-reactive"],
                 ignore_dates={"1974-01-02": "date of birth"},
                 exercises=["'HIV non-reactive' is a result, not a negation", "DOB in a boxed header next to the dates", "gm%, TLC, lakhs/cumm", "NABL footer"])),
]
A5 = [
 dict(path="tumour_board/tumour_board_record_2026-09-24.pdf", fmt="pdf", dept="Multidisciplinary Tumour Board", title="TUMOUR BOARD RECORD",
      id_rows=_sd_usg_rows, meta=[("Board date", "24/09/2026")],
      sections=[("Present", "Surgical oncology (Dr. Pooja Hegde), medical oncology (Dr. Anand Kulkarni), radio-diagnosis (Dr. Shalini Rao), pathology (Dr. Fatima Begum)."),
                ("Absent", "Radiation oncology."),
                ("Decision recorded by the board", DECISION_TEXT),
                ("Actions", "Medical Oncology: start chemotherapy after cardiac evaluation (2D echo). Radio-diagnosis: MRI breast after chemotherapy.")],
      footer=["Record status: FINAL", "Recorded by: Dr. Anand Kulkarni, Tumour Board coordinator (electronically signed)", "Signed: 24/09/2026 18:30"], stamp="FINAL / SIGNED",
      truth=dict(doc_type="tumour_board_record", status="FINAL", signed=True, fields={}, report_date="2026-09-24", event_date="2026-09-24", event_label="board date",
                 identity=_sd_usg_id, board_decision=BOARD_DECISION,
                 exercises=["dose slip: Doxorubicin written as 6 mg/m2 (reference 60 mg/m2)", "radiation oncologist absent (PM-JAY board composition)"])),
]

# =================================================================================================================
# CASE TB-006: rectum. 100-page image-only outside record, DRAFT then FINAL MRI with a changed value, CEA awaited.
# =================================================================================================================
_ir_rows, _ir_id = ident(P6, "Mohammed Irfan Shaikh", ["mrn", "age_sex"])
_ir_ip_rows, _ir_ip_id = ident(P6, "Md. Irfan Shaikh", ["mrn", "ip_no", "age_sex"])
C6 = [
 dict(path="outside_records/deccan_general_hospital_records_scan.pdf", fmt="bigscan",
      truth=dict(doc_type="other", status="UNSTATED", signed=True, fields={}, pages=100,
                 report_date=None, event_date="2026-05-11", event_end="2026-05-18", event_label="outside admission",
                 identity={"name": "Md. Irfan Shaikh", "relation": "S/o Abdul Kareem Shaikh", "age_sex": "61 Y / M", "outside_id": P6["outside_id"]},
                 facts_by_page={str(k): v[1] for k, v in BIG_FACTS.items()},
                 exercises=["100-page image-only scan (no text layer): batch it and warn (item 3.7)", "outside hospital number only, no UHID / MRN of this hospital",
                            "the few clinical facts are buried on pages 37, 62 and 88"])),
 dict(path="gastroenterology/colonoscopy_2026-09-22.pdf", fmt="pdf", dept="Department of Gastroenterology", title="COLONOSCOPY REPORT",
      id_rows=_ir_rows, meta=[("Procedure date", "22/09/2026")],
      sections=[("Findings", "Ulceroproliferative growth from 8 cm to 12 cm from the anal verge, about three-quarters circumferential. Scope negotiated beyond the growth. Rest of the colon normal up to the caecum."),
                ("Procedure", "Biopsies taken from the growth.")],
      footer=signed("FINAL", "Dr. Imtiaz Ahmed, DM (Gastroenterology), TSMC Reg. No. 44120", "22/09/2026 12:50"), stamp="FINAL / SIGNED",
      truth=dict(doc_type="endoscopy", status="FINAL", signed=True, fields={"distance_from_anal_verge": "8 cm"}, report_date="2026-09-22", event_date="2026-09-22",
                 event_label="procedure date", identity=_ir_id, exercises=["Telangana council registration (TSMC)"])),
 dict(path="pathology/rectal_biopsy_2026-09-25.pdf", fmt="pdf", dept="Department of Pathology", title="HISTOPATHOLOGY REPORT",
      id_rows=_ir_rows, meta=[("Specimen", "Endoscopic biopsies, rectal growth"), ("Received on", "22/09/2026")],
      sections=[("Diagnosis", "Adenocarcinoma, moderately differentiated."),
                ("Mismatch repair proteins (IHC)", [["Protein", "Result"], ["MLH1", "Retained"], ["PMS2", "Retained"], ["MSH2", "Retained"], ["MSH6", "Retained"]]),
                ("Interpretation", "Loss of mismatch repair protein expression: not detected (pMMR)."),
                ("KRAS / NRAS / BRAF", "Not detected (KRAS exon 2, 3, 4; NRAS exon 2, 3, 4; BRAF V600E).")],
      footer=signed("FINAL", "Dr. Fatima Begum, MD (Pathology), KMC Reg. No. 62290", "25/09/2026 15:10"), stamp="FINAL / SIGNED",
      truth=dict(doc_type="histopathology", status="FINAL", signed=True, fields={"histologic_type": "Adenocarcinoma", "grade": "moderately differentiated", "mmr": "pMMR", "ras_braf": "Not detected"},
                 report_date="2026-09-25", event_date="2026-09-22", event_label="received on", identity=_ir_id, negated=["Loss of MMR expression: not detected", "KRAS / NRAS / BRAF: Not detected"],
                 exercises=["negated values 'not detected' are real results"])),
 dict(path="radio_diagnosis/mri_pelvis_2026-09-25_draft.pdf", fmt="pdf", dept="Department of Radio-diagnosis", title="MRI PELVIS (RECTAL CANCER PROTOCOL): DRAFT REPORT",
      id_rows=_ir_ip_rows, meta=[("Study date", "25/09/2026")],
      sections=[("Findings", "Mid rectal tumour, lower edge 8 cm from the anal verge. Extramural spread 3 mm (mrT3b). Mesorectal fascia clear (5 mm). EMVI negative. Two mesorectal nodes, largest 6 mm."),
                ("Staging as recorded by the reporting radiologist", "mrT3b N1, MRF clear, EMVI negative.")],
      footer=["Report status: DRAFT", "Reported by: (signature pending)", "Date: 25/09/2026"], stamp="DRAFT / UNSIGNED",
      truth=dict(doc_type="mri", status="DRAFT", signed=False, fields={"recorded_stage": "mrT3b N1", "mrf_status": "clear", "emvi": "negative"},
                 report_date="2026-09-25", event_date="2026-09-25", event_label="study date", identity=_ir_ip_id,
                 exercises=["DRAFT, signature pending", "IP No. printed with MRN", "name as Md."])),
 dict(path="laboratory_medicine/cbc_cea_2026-09-23.pdf", fmt="pdf", dept="Department of Laboratory Medicine", title="LABORATORY REPORT",
      grid=lab_grid(_ir_rows, "23/09/2026 07:50", "23/09/2026 08:05", "23/09/2026 14:30", "Dr. Imtiaz Ahmed", "LAB/26/120554"),
      sections=[("Haematology", [["Investigation", "Result", "Units", "Biological ref. interval"], ["Haemoglobin", "10.2", "gm%", "13.0 - 17.0"],
                                  ["Total leucocyte count (TLC)", "7,100", "cells/cumm", "4,000 - 11,000"], ["Platelet count", "3.3", "lakhs/cumm", "1.5 - 4.1"]]),
                ("Biochemistry", [["Investigation", "Result", "Units", "Biological ref. interval"], ["S. Creatinine", "0.9", "mg/dl", "0.7 - 1.3"], ["CEA", "Awaited", "ng/ml", "< 5.0"]])],
      footer=sd("Dr. Suresh Babu, MD (Pathology)", "KMC Reg. No. 69021"), nabl=NABL,
      truth=dict(doc_type="lab", status="FINAL", signed=True, fields={"haemoglobin": "10.2", "wbc": "7,100", "platelets": "3.3", "creatinine": "0.9", "cea": None},
                 report_date="2026-09-23", event_date="2026-09-23", event_label="collected on", identity=_ir_id, pending=["CEA: Awaited"],
                 exercises=["pending value 'Awaited' in a results table"])),
]
A6 = [
 dict(path="radio_diagnosis/mri_pelvis_2026-09-27_final.pdf", fmt="pdf", dept="Department of Radio-diagnosis", title="MRI PELVIS (RECTAL CANCER PROTOCOL)",
      id_rows=_ir_ip_rows, meta=[("Study date", "25/09/2026"), ("Replaces", "Draft report of 25/09/2026")],
      sections=[("Findings", "Mid rectal tumour, lower edge 8 cm from the anal verge. Extramural spread 6 mm (mrT3c). Mesorectal fascia clear (3 mm). EMVI negative. Two mesorectal nodes, largest 6 mm."),
                ("Staging as recorded by the reporting radiologist", "mrT3c N1, MRF clear, EMVI negative.")],
      footer=signed("FINAL", "Dr. Shalini Rao, MD (Radio-diagnosis), KMC Reg. No. 66310", "27/09/2026 10:40"), stamp="FINAL / SIGNED",
      truth=dict(doc_type="mri", status="FINAL", signed=True, fields={"recorded_stage": "mrT3c N1", "mrf_status": "clear", "emvi": "negative"},
                 report_date="2026-09-27", event_date="2026-09-25", event_label="study date", identity=_ir_ip_id, supersedes="radio_diagnosis/mri_pelvis_2026-09-25_draft.pdf",
                 exercises=["FINAL replaces DRAFT with a changed value (mrT3b to mrT3c, MRF 5 mm to 3 mm)"])),
 dict(path="laboratory_medicine/cea_2026-09-28.pdf", fmt="pdf", dept="Department of Laboratory Medicine", title="TUMOUR MARKER REPORT",
      grid=lab_grid(_ir_rows, "23/09/2026 07:50", "23/09/2026 08:05", "28/09/2026 11:15", "Dr. Imtiaz Ahmed", "LAB/26/120554"),
      sections=[("Result", [["Investigation", "Result", "Units", "Biological ref. interval"], ["CEA", "9.4", "ng/ml", "< 5.0"]])],
      footer=sd("Dr. R. Pillai, MD (Biochemistry)", "KMC Reg. No. 70418"), nabl=NABL,
      truth=dict(doc_type="lab", status="FINAL", signed=True, fields={"cea": "9.4"}, report_date="2026-09-28", event_date="2026-09-23", event_label="collected on", identity=_ir_id,
                 exercises=["pending value arrives later", "collected 5 days before reported"])),
]

# =================================================================================================================
# CASE TB-007: oral cavity (left buccal mucosa, plan item V1-9.1). Gutka chewer, cT4a N1 recorded by the surgeon,
# dental evaluation only in a Word file (name with the title Sri), and a board record with weekly cisplatin and adjuvant RT.
# =================================================================================================================
_mg_rows, _mg_id = ident(P7, "Manjunath Gowda", ["uhid", "age_sex"])
_mg_opd_rows, _mg_opd_id = ident(P7, "Manjunath Gowda", ["uhid", "age_sex", "relation"])
_mg_hp_rows, _mg_hp_id = ident(P7, "Manjunath Gowda", ["uhid", "abha", "age_sex"])
_mg_lab_rows, _mg_lab_id = ident(P7, "Manjunath Gowda", ["uhid", "age_sex"], labels={"name": "Name"})
_SHALINI = "Dr. Shalini Rao, MD (Radio-diagnosis), KMC Reg. No. 66310"
DECISION_TEXT_7 = ("Composite resection: wide local excision of the left buccal mucosa lesion with segmental mandibulectomy, left modified neck "
                   "dissection (levels I to V) and reconstruction with a pectoralis major myocutaneous flap. Adjuvant radiotherapy 60 Gy in 30 "
                   "fractions to the tumour bed and neck, with concurrent Inj. Cisplatin 40 mg/m2 IV weekly if the final histopathology shows a "
                   "positive margin or extranodal extension. Stage as recorded: cT4a N1 M0.")
BOARD_DECISION_7 = {"document": "tumour_board/tumour_board_record_2026-09-24.pdf", "board_date": "2026-09-24", "text": DECISION_TEXT_7,
                    "dose_slips": [], "absent_specialties": [],
                    "note": "No planted error: doses as in the references and all three oncologists present; the board record is fictional."}

C7 = [
 dict(path="surgical_oncology/head_neck_opd_2026-09-14.pdf", fmt="pdf", dept="Department of Surgical Oncology (Head and Neck Services)",
      title="HEAD AND NECK ONCOLOGY OPD", id_rows=_mg_opd_rows, meta=[("Visit date", "14/09/2026")],
      sections=[("Presenting complaints", "Non-healing ulcer in the left cheek for 3 months. Difficulty in opening the mouth for 1 month."),
                ("History", "Chews gutka (tobacco with areca nut) for 20 years, 4 to 5 sachets a day; stopped 3 months ago. Occasional bidi smoking. "
                            "Type 2 diabetes mellitus on metformin 500 mg twice daily."),
                ("Examination", "Ulceroproliferative lesion 4 x 3 cm in the left buccal mucosa extending to the lower gingivobuccal sulcus; induration up to "
                                "the skin of the cheek, skin free. Mouth opening two fingers (interincisal distance 2.5 cm). Left level IB lymph node 2 x 2 cm, "
                                "firm, mobile. No other palpable neck node."),
                ("Performance status", "ECOG performance status: 1"),
                ("Clinical stage as recorded by the treating surgeon", "cT4a N1 M0 (AJCC 8th edition), Stage IVA"),
                ("Question for the Tumour Board", "Operability: composite resection with segmental or marginal mandibulectomy, and the need for adjuvant treatment.")],
      footer=signed("FINAL", "Dr. Prakash Hegde, MS, MCh (Surgical Oncology), KMC Reg. No. 81234", "14/09/2026 13:10"), stamp="FINAL / SIGNED",
      truth=dict(doc_type="clinical_note", status="FINAL", signed=True,
                 fields={"ecog": "1", "clinical_question": "Operability", "recorded_stage": "cT4a N1 M0", "tobacco_use": "gutka",
                         "presenting_complaint": "Non-healing ulcer in the left cheek for 3 months"},
                 report_date="2026-09-14", event_date="2026-09-14", event_label="visit date", identity=_mg_opd_id,
                 exercises=["smokeless tobacco (gutka) recorded as tobacco use", "stage recorded by the treating surgeon (never derived)",
                            "no dental evaluation in this note: the dental record must come from the dental Word file only"])),
 dict(path="pathology/biopsy_left_buccal_mucosa_2026-09-10.pdf", fmt="pdf", dept="Department of Pathology", title="HISTOPATHOLOGY REPORT",
      id_rows=_mg_hp_rows, meta=[("Specimen", "Punch biopsy, left buccal mucosa"), ("Received on", "08/09/2026"), ("Lab No.", "HP/2026/8123")],
      sections=[("Diagnosis", "Squamous cell carcinoma, keratinising, moderately differentiated."),
                ("Additional findings", "Perineural invasion: Not identified in this biopsy.\n"
                                        "Depth of invasion: cannot be assessed in this superficial biopsy (see imaging).")],
      footer=signed("FINAL", "Dr. Fatima Begum, MD (Pathology), KMC Reg. No. 62290", "10/09/2026 16:40"), stamp="FINAL / SIGNED",
      truth=dict(doc_type="histopathology", status="FINAL", signed=True,
                 fields={"histologic_type": "Squamous cell carcinoma", "grade": "moderately differentiated", "pni": "Not identified"},
                 report_date="2026-09-10", event_date="2026-09-08", event_label="received on", identity=_mg_hp_id,
                 negated=["Perineural invasion: Not identified"],
                 exercises=["ABHA number printed", "negated value 'Not identified' is a real result",
                            "depth of invasion not assessable in a superficial biopsy: must not be filled from this report"])),
 dict(path="radio_diagnosis/cect_face_neck_2026-09-16.pdf", fmt="pdf", dept="Department of Radio-diagnosis", title="CECT FACE AND NECK",
      id_rows=_mg_rows, meta=[("Study date", "16/09/2026"), ("Ref. by", "Dr. Prakash Hegde")],
      sections=[("Findings", "Enhancing ulcerative mass in the left buccal mucosa measuring 4.2 x 3.1 x 2.6 cm, extending to the lower gingivobuccal sulcus "
                             "and the retromolar trigone. Depth of invasion about 12 mm. Erosion of the outer cortex of the left mandibular body (premolar to "
                             "molar region); no medullary involvement. Masticator space free. Skin of the cheek free.\n"
                             "Neck: left level IB lymph node 2.1 x 1.8 cm with central necrosis; no perinodal extension. No other significant cervical lymphadenopathy."),
                ("Impression (reporting radiologist)", "Carcinoma of the left buccal mucosa with outer cortical erosion of the mandible and a left level IB "
                                                       "metastatic node. Stage as recorded: cT4a N1.")],
      footer=signed("FINAL", _SHALINI, "16/09/2026 17:35"), stamp="FINAL / SIGNED",
      truth=dict(doc_type="ct", status="FINAL", signed=True,
                 fields={"lesion_size": "4.2 x 3.1 x 2.6 cm", "nodal_findings": "left level IB lymph node 2.1 x 1.8 cm", "depth_of_invasion": "12 mm",
                         "recorded_stage": "cT4a N1", "ene": "no perinodal extension"},
                 report_date="2026-09-16", event_date="2026-09-16", event_label="study date", identity=_mg_id,
                 negated=["Perinodal extension: no perinodal extension"],
                 exercises=["depth of invasion from imaging", "outer cortical erosion of the mandible (recorded stage cT4a, never derived)",
                            "negated value 'no perinodal extension' is a real result"])),
 dict(path="radio_diagnosis/xray_chest_pa_2026-09-15.png", fmt="scan", dept="Department of Radio-diagnosis", title="X-RAY CHEST PA VIEW",
      id_rows=_mg_rows, meta=[("Study date", "15/09/2026")],
      sections=[("Findings", "Both lung fields clear. No nodule or mass. Costophrenic angles clear. Cardiac silhouette normal."),
                ("Impression", "No radiological evidence of pulmonary metastasis.")],
      footer=signed("FINAL", _SHALINI, "15/09/2026 16:20"), stamp="FINAL / SIGNED",
      truth=dict(doc_type="xray", status="FINAL", signed=True, fields={"distant_findings": "No radiological evidence of pulmonary metastasis"},
                 report_date="2026-09-15", event_date="2026-09-15", event_label="study date", identity=_mg_id,
                 exercises=["scanned image", "chest X-ray as the distant work-up"])),
 dict(path="surgical_oncology/dental_evaluation_2026-09-17.docx", fmt="docx",
      blocks=[("b", HOSP), ("p", WM), ("p", "Department of Dental and Prosthetic Surgery"), ("b", "PRE-TREATMENT DENTAL EVALUATION"),
              ("p", "Date: 17/09/2026"),
              ("table", [["Patient name", "Sri Manjunath Gowda"], ["UHID", P7["uhid"]], ["Age / Sex", P7["age_sex"]]]),
              ("p", "OPG (orthopantomogram) dated 17/09/2026: horizontal bone loss around 36 and 37; no other bony lesion seen."),
              ("p", "Dental evaluation: grossly carious 36 and 37, extraction advised before radiotherapy. Oral prophylaxis done. Fluoride trays advised."),
              ("p", "Nutrition: weight 58 kg, BMI 20.1 kg/m2; high-protein diet counselling by the dietician."),
              ("p", "Swallowing: no difficulty in swallowing reported."),
              ("p", "Sd/-"), ("p", "Dr. Kavya Shetty, MDS (Prosthodontics), KSDC Reg. No. A-10422")],
      truth=dict(doc_type="clinical_note", status="UNSTATED", signed=True, fields={"dental_evaluation": "36 and 37"},
                 report_date="2026-09-17", event_date="2026-09-17", event_label="date",
                 identity={"name": "Sri Manjunath Gowda", "uhid": P7["uhid"], "age_sex": P7["age_sex"]},
                 exercises=["Word file", "name with the title Sri", "no status line, Sd/- signature", "Karnataka State Dental Council registration (KSDC)",
                            "the only source of the dental evaluation (pre-radiotherapy dental clearance)"])),
 dict(path="laboratory_medicine/cbc_rft_lft_serology_2026-09-15.pdf", fmt="pdf", dept="Department of Laboratory Medicine", title="LABORATORY INVESTIGATION REPORT",
      grid=lab_grid(_mg_lab_rows, "15/09/2026 08:05", "15/09/2026 08:15", "15/09/2026 14:20", "Dr. Prakash Hegde", "LAB/26/121044"),
      sections=[("Haematology", [["Investigation", "Result", "Units", "Biological ref. interval"], ["Haemoglobin", "13.1", "gm%", "13.0 - 17.0"],
                                  ["Total leucocyte count (TLC)", "8,400", "cells/cumm", "4,000 - 11,000"], ["Platelet count", "2.6", "lakhs/cumm", "1.5 - 4.1"]]),
                ("Biochemistry", [["Investigation", "Result", "Units", "Biological ref. interval"], ["S. Creatinine", "0.9", "mg/dl", "0.7 - 1.3"],
                                   ["Total bilirubin", "0.6", "mg/dl", "0.2 - 1.2"], ["HbA1c", "7.4", "%", "4.0 - 5.6"]]),
                ("Serology", [["Investigation", "Result", "Method"], ["HIV I and II antibodies", "Non-reactive", "CLIA"], ["HBsAg", "Non-reactive", "CLIA"],
                              ["Anti-HCV", "Non-reactive", "CLIA"]])],
      footer=sd("Dr. Suresh Babu, MD (Pathology)", "KMC Reg. No. 69021"), nabl=NABL,
      truth=dict(doc_type="lab", status="FINAL", signed=True,
                 fields={"haemoglobin": "13.1", "wbc": "8,400", "platelets": "2.6", "creatinine": "0.9", "bilirubin": "0.6"},
                 report_date="2026-09-15", event_date="2026-09-15", event_label="collected on", identity=_mg_lab_id,
                 other_values={"hba1c": "7.4", "hiv": "Non-reactive", "hbsag": "Non-reactive", "anti_hcv": "Non-reactive"},
                 not_negations=["HIV I and II antibodies: Non-reactive", "HBsAg: Non-reactive", "Anti-HCV: Non-reactive"],
                 exercises=["'Non-reactive' serology is a result, not a negation", "gm%, TLC, lakhs/cumm", "HbA1c of a diabetic (no protocol fact)", "NABL footer"])),
]
A7 = [
 dict(path="tumour_board/tumour_board_record_2026-09-24.pdf", fmt="pdf", dept="Multidisciplinary Tumour Board", title="TUMOUR BOARD RECORD",
      id_rows=_mg_rows, meta=[("Board date", "24/09/2026")],
      sections=[("Present", "Surgical oncology (Dr. Prakash Hegde), radiation oncology (Dr. Meera Iyer), medical oncology (Dr. Anand Kulkarni), "
                            "radio-diagnosis (Dr. Shalini Rao), pathology (Dr. Fatima Begum)."),
                ("Decision recorded by the board", DECISION_TEXT_7),
                ("Actions", "Dental and Prosthetic Surgery: extraction of 36 and 37 before surgery. Surgical Oncology: schedule surgery within two weeks.")],
      footer=["Record status: FINAL", "Recorded by: Dr. Anand Kulkarni, Tumour Board coordinator (electronically signed)", "Signed: 24/09/2026 18:45"], stamp="FINAL / SIGNED",
      truth=dict(doc_type="tumour_board_record", status="FINAL", signed=True, fields={}, report_date="2026-09-24", event_date="2026-09-24", event_label="board date",
                 identity=_mg_id, board_decision=BOARD_DECISION_7,
                 exercises=["board decision with weekly cisplatin and an adjuvant RT schedule (guideline check against NCG head and neck)",
                            "all three oncologists present (PM-JAY composition met)"])),
]

# =================================================================================================================
# CASE TB-008: cervix (plan item V1-9.2). FIGO 2018 Stage IIB recorded by the gynaecologic oncologist and the radiologist,
# a phone photo of the chest X-ray, LVSI not identified, HIV non-reactive, cystoscopy / proctoscopy arriving later, and a
# board record with concurrent weekly cisplatin, EBRT and HDR brachytherapy.
# =================================================================================================================
_pn_rows, _pn_id = ident(P8, "Parvathi Naik", ["uhid", "age_sex"])
_pn_opd_rows, _pn_opd_id = ident(P8, "Parvathi Naik", ["uhid", "age_sex", "relation"])
_pn_hp_rows, _pn_hp_id = ident(P8, "Parvathi Naik", ["uhid", "abha", "age_sex"])
_pn_lab_rows, _pn_lab_id = ident(P8, "Smt. Parvathi Naik", ["uhid", "age_sex"], labels={"name": "Name"})
_ANJALI = "Dr. Anjali Deshpande, MS (OBG), MCh (Gynaecologic Oncology), KMC Reg. No. 84512"
DECISION_TEXT_8 = ("Radical concurrent chemoradiation: external beam radiotherapy 50 Gy in 25 fractions to the pelvis with concurrent Inj. Cisplatin "
                   "40 mg/m2 IV weekly, followed by HDR intracavitary brachytherapy 7 Gy x 3 fractions to point A. FIGO 2018 Stage IIB as recorded.")
BOARD_DECISION_8 = {"document": "tumour_board/tumour_board_record_2026-09-26.pdf", "board_date": "2026-09-26", "text": DECISION_TEXT_8,
                    "dose_slips": [], "absent_specialties": [],
                    "note": "No planted error: doses as in the references and all three oncologists present; the board record is fictional."}

C8 = [
 dict(path="surgical_oncology/gynae_onc_opd_2026-09-15.pdf", fmt="pdf", dept="Department of Surgical Oncology (Gynaecologic Oncology)",
      title="GYNAECOLOGIC ONCOLOGY OPD", id_rows=_pn_opd_rows, meta=[("Visit date", "15/09/2026")],
      sections=[("Presenting complaints", "Post-coital bleeding and foul-smelling vaginal discharge for 4 months."),
                ("History", "P3 L3, all normal deliveries; tubal ligation 15 years ago. No known comorbidities."),
                ("Examination", "Per speculum: ulceroproliferative growth replacing the cervix, about 4 cm, bleeds on touch.\n"
                                "Per vaginal: growth 4 x 4 cm; upper third of the vagina involved, lower two thirds free; left parametrium involved, "
                                "not reaching the lateral pelvic wall; right parametrium free.\n"
                                "Per rectal: left parametrial thickening; rectal mucosa free."),
                ("Performance status", "ECOG performance status: 1"),
                ("FIGO stage as recorded by the treating gynaecologic oncologist", "FIGO 2018 Stage IIB"),
                ("Question for the Tumour Board", "Definitive treatment plan and its sequence.")],
      footer=signed("FINAL", _ANJALI, "15/09/2026 12:40"), stamp="FINAL / SIGNED",
      truth=dict(doc_type="clinical_note", status="FINAL", signed=True,
                 fields={"ecog": "1", "figo_stage": "IIB", "clinical_question": "Definitive treatment plan",
                         "parametrial_involvement": "left parametrium involved", "presenting_complaint": "Post-coital bleeding"},
                 report_date="2026-09-15", event_date="2026-09-15", event_label="visit date", identity=_pn_opd_id,
                 exercises=["FIGO stage recorded by the treating clinician (never derived)", "clinical parametrial assessment (per vaginal, per rectal)",
                            "relation W/o", "obstetric history P3 L3"])),
 dict(path="pathology/cervical_biopsy_2026-09-12.pdf", fmt="pdf", dept="Department of Pathology", title="HISTOPATHOLOGY REPORT",
      id_rows=_pn_hp_rows, meta=[("Specimen", "Punch biopsy, cervix"), ("Received on", "10/09/2026"), ("Lab No.", "HP/2026/8377")],
      sections=[("Diagnosis", "Squamous cell carcinoma, non-keratinising, moderately differentiated (grade 2)."),
                ("Additional findings", "Depth of invasion: at least 5 mm in this biopsy (base of the lesion not included).\n"
                                        "Lymphovascular space invasion (LVSI): Not identified.")],
      footer=signed("FINAL", "Dr. Fatima Begum, MD (Pathology), KMC Reg. No. 62290", "12/09/2026 15:55"), stamp="FINAL / SIGNED",
      truth=dict(doc_type="histopathology", status="FINAL", signed=True,
                 fields={"histologic_type": "Squamous cell carcinoma", "grade": "moderately differentiated", "depth_of_invasion": "5 mm", "lvi": "Not identified"},
                 report_date="2026-09-12", event_date="2026-09-10", event_label="received on", identity=_pn_hp_id,
                 negated=["Lymphovascular space invasion (LVSI): Not identified"],
                 exercises=["ABHA number printed", "negated value 'Not identified' is a real result",
                            "depth of invasion is a minimum ('at least 5 mm') in a biopsy without the base of the lesion"])),
 dict(path="radio_diagnosis/mri_pelvis_2026-09-17.pdf", fmt="pdf", dept="Department of Radio-diagnosis", title="MRI PELVIS (CARCINOMA CERVIX PROTOCOL)",
      id_rows=_pn_rows, meta=[("Study date", "17/09/2026"), ("Ref. by", "Dr. Anjali Deshpande")],
      sections=[("Findings", "Cervical mass 4.3 x 3.8 x 3.5 cm involving the upper third of the vagina. Left parametrial invasion (disrupted stromal ring "
                             "with a spiculated interface), not reaching the pelvic side wall; right parametrium free. Urinary bladder and rectum free, fat "
                             "planes preserved. No hydroureteronephrosis. No enlarged pelvic lymph node."),
                ("Impression (reporting radiologist)", "Carcinoma cervix with left parametrial invasion. FIGO stage on imaging, as recorded by the "
                                                       "reporting radiologist: IIB.")],
      footer=signed("FINAL", _SHALINI, "17/09/2026 18:05"), stamp="FINAL / SIGNED",
      truth=dict(doc_type="mri", status="FINAL", signed=True,
                 fields={"lesion_size": "4.3 x 3.8 x 3.5 cm", "parametrial_involvement": "Left parametrial invasion",
                         "nodal_findings": "No enlarged pelvic lymph node", "figo_stage": "IIB"},
                 report_date="2026-09-17", event_date="2026-09-17", event_label="study date", identity=_pn_id,
                 negated=["Pelvic lymph nodes: No enlarged pelvic lymph node"],
                 exercises=["parametrial invasion on MRI agrees with the clinical examination", "FIGO stage recorded by the radiologist (never derived)",
                            "negated nodal finding is a real result"])),
 dict(path="radio_diagnosis/cect_abdomen_pelvis_2026-09-18.pdf", fmt="pdf", dept="Department of Radio-diagnosis", title="CECT ABDOMEN AND PELVIS",
      id_rows=_pn_rows, meta=[("Study date", "18/09/2026"), ("Ref. by", "Dr. Anjali Deshpande")],
      sections=[("Findings", "Known cervical mass. No pelvic or para-aortic lymphadenopathy. No hydronephrosis; both kidneys normal. Liver, spleen and "
                             "adrenals normal. No ascites. No lytic or sclerotic bone lesion in the scanned skeleton."),
                ("Impression (reporting radiologist)", "No nodal or distant disease in the abdomen and pelvis.")],
      footer=signed("FINAL", _SHALINI, "18/09/2026 16:50"), stamp="FINAL / SIGNED",
      truth=dict(doc_type="ct", status="FINAL", signed=True,
                 fields={"nodal_findings": "No pelvic or para-aortic lymphadenopathy", "distant_findings": "No nodal or distant disease in the abdomen and pelvis"},
                 report_date="2026-09-18", event_date="2026-09-18", event_label="study date", identity=_pn_id,
                 negated=["Pelvic and para-aortic nodes: No pelvic or para-aortic lymphadenopathy"],
                 exercises=["para-aortic nodes and hydronephrosis assessed (FIGO IIIB / IIIC would change the plan; stage is never derived)"])),
 dict(path="radio_diagnosis/xray_chest_pa_2026-09-16_phone_photo.png", fmt="photo", dept="Department of Radio-diagnosis", title="X-RAY CHEST PA VIEW",
      id_rows=_pn_rows, meta=[("Study date", "16/09/2026")],
      sections=[("Findings", "Both lung fields clear. No nodule. Costophrenic angles clear. Cardiac silhouette normal."),
                ("Impression", "No radiological evidence of metastasis.")],
      footer=signed("FINAL", _SHALINI, "16/09/2026 15:30"), stamp="FINAL / SIGNED",
      truth=dict(doc_type="xray", status="FINAL", signed=True, fields={"distant_findings": "No radiological evidence of metastasis"},
                 report_date="2026-09-16", event_date="2026-09-16", event_label="study date", identity=_pn_id,
                 exercises=["phone photo (tilted, shadowed, on a desk)", "chest X-ray as the distant work-up"])),
 dict(path="laboratory_medicine/cbc_lft_rft_hiv_2026-09-15.pdf", fmt="pdf", dept="Department of Laboratory Medicine", title="LABORATORY INVESTIGATION REPORT",
      grid=lab_grid(_pn_lab_rows, "15/09/2026 08:40", "15/09/2026 08:50", "15/09/2026 15:10", "Dr. Anjali Deshpande", "LAB/26/121377"),
      sections=[("Haematology", [["Investigation", "Result", "Units", "Biological ref. interval"], ["Haemoglobin", "9.8", "gm%", "12.0 - 15.0"],
                                  ["Total leucocyte count (TLC)", "7,600", "cells/cumm", "4,000 - 11,000"], ["Platelet count", "3.4", "lakhs/cumm", "1.5 - 4.1"]]),
                ("Biochemistry", [["Investigation", "Result", "Units", "Biological ref. interval"], ["S. Creatinine", "1.1", "mg/dl", "0.5 - 1.1"],
                                   ["Blood urea", "32", "mg/dl", "15 - 40"], ["Total bilirubin", "0.5", "mg/dl", "0.2 - 1.2"], ["SGPT (ALT)", "24", "U/L", "< 35"]]),
                ("Serology", [["Investigation", "Result", "Method"], ["HIV I and II antibodies", "Non-reactive", "CLIA"], ["HBsAg", "Non-reactive", "CLIA"]])],
      footer=sd("Dr. Suresh Babu, MD (Pathology)", "KMC Reg. No. 69021"), nabl=NABL,
      truth=dict(doc_type="lab", status="FINAL", signed=True,
                 fields={"haemoglobin": "9.8", "wbc": "7,600", "platelets": "3.4", "creatinine": "1.1", "bilirubin": "0.5", "hiv_status": "Non-reactive"},
                 report_date="2026-09-15", event_date="2026-09-15", event_label="collected on", identity=_pn_lab_id,
                 other_values={"hbsag": "Non-reactive"}, not_negations=["HIV I and II antibodies: Non-reactive", "HBsAg: Non-reactive"],
                 exercises=["'HIV non-reactive' is a result, not a negation", "name with the title Smt.", "gm%, TLC, lakhs/cumm", "NABL footer"])),
]
A8 = [
 dict(path="surgical_oncology/cystoscopy_proctoscopy_2026-09-22.pdf", fmt="pdf", dept="Department of Surgical Oncology (Gynaecologic Oncology)",
      title="CYSTOSCOPY AND PROCTO-SIGMOIDOSCOPY", id_rows=_pn_rows, meta=[("Procedure date", "22/09/2026")],
      sections=[("Findings", "Cystoscopy: bladder mucosa normal; no bullous oedema; both ureteric orifices normal.\n"
                             "Procto-sigmoidoscopy up to 20 cm: rectal mucosa free; no growth."),
                ("Impression", "No bladder or rectal mucosal involvement.")],
      footer=signed("FINAL", _ANJALI, "22/09/2026 13:15"), stamp="FINAL / SIGNED",
      truth=dict(doc_type="endoscopy", status="FINAL", signed=True, fields={}, report_date="2026-09-22", event_date="2026-09-22", event_label="procedure date",
                 identity=_pn_id,
                 exercises=["arrives later and closes the Level 1 gap of the cystoscopy / proctoscopy record (locally advanced work-up)"])),
 dict(path="tumour_board/tumour_board_record_2026-09-26.pdf", fmt="pdf", dept="Multidisciplinary Tumour Board", title="TUMOUR BOARD RECORD",
      id_rows=_pn_rows, meta=[("Board date", "26/09/2026")],
      sections=[("Present", "Surgical oncology, gynaecologic oncology (Dr. Anjali Deshpande), radiation oncology (Dr. Meera Iyer), medical oncology "
                            "(Dr. Anand Kulkarni), radio-diagnosis (Dr. Shalini Rao), pathology (Dr. Fatima Begum)."),
                ("Decision recorded by the board", DECISION_TEXT_8),
                ("Actions", "Radiation Oncology: start chemoradiation within two weeks. Laboratory Medicine: weekly CBC and serum creatinine during chemoradiation.")],
      footer=["Record status: FINAL", "Recorded by: Dr. Anand Kulkarni, Tumour Board coordinator (electronically signed)", "Signed: 26/09/2026 18:20"], stamp="FINAL / SIGNED",
      truth=dict(doc_type="tumour_board_record", status="FINAL", signed=True, fields={}, report_date="2026-09-26", event_date="2026-09-26", event_label="board date",
                 identity=_pn_id, board_decision=BOARD_DECISION_8,
                 exercises=["board decision with concurrent weekly cisplatin, EBRT and HDR brachytherapy (guideline check against NCG cervix)",
                            "all three oncologists present (PM-JAY composition met)"])),
]

V1_CASES = [("TB-004", "lung_nsclc", dict(name="Ramesh Kumar", mrn=P4["uhid"], agesex=P4["age_sex"]), C4, A4),
            ("TB-005", "breast", dict(name="Sunita Devi", mrn=P5["uhid"], agesex=P5["age_sex"]), C5, A5),
            ("TB-006", "colorectal_rectum", dict(name="Mohammed Irfan Shaikh", mrn=P6["mrn"], agesex=P6["age_sex"]), C6, A6),
            ("TB-007", "oral_cavity", dict(name="Manjunath Gowda", mrn=P7["uhid"], agesex=P7["age_sex"]), C7, A7),
            ("TB-008", "cervix", dict(name="Parvathi Naik", mrn=P8["uhid"], agesex=P8["age_sex"]), C8, A8)]
V1_PATIENTS = {"TB-004": P4, "TB-005": P5, "TB-006": P6, "TB-007": P7, "TB-008": P8}
BOARD_DECISIONS = {"TB-005": BOARD_DECISION, "TB-007": BOARD_DECISION_7, "TB-008": BOARD_DECISION_8}  # truth["board_decision"] per case

# =================================================================================================================
# INTAKE: department batches without a Case File, mixing several patients (patient matching, item 2.4)
# =================================================================================================================
_in = {}
_in["rk1_xray"] = ident(P1, "R. Kumar", ["uhid", "age_sex"], values={"age_sex": "62 Y / M"})
_in["rk4_usg"] = ident(P4, "RAMESH KUMAR", ["cr_no", "age_sex"], labels={"name": "Name"})
_in["li_mammo"] = ident(P2, "Smt. Laxmi Iyer", ["uhid", "age_sex"])
_in["sd5_review"] = ident(P5, "Smt. S. Devi", ["uhid", "age_sex"])
_in["sd2_pap"] = ident(P5B, "Sunita Devi", ["relation", "uhid", "age_sex"], labels={"relation": ""})
_in["sd2_cbc"] = ident(P5B, "Smt. Sunita Devi", ["uhid", "age_sex", "aadhaar"], labels={"name": "Name"})
_in["ir_lft"] = ident(P6, "Md. Irfan Shaikh", ["mrn", "age_sex"], labels={"mrn": "Hospital No."})
_noid_rows = [("Name", "Ramesh Kumar"), ("Age / Sex", "60 Y / M")]

INTAKE = {
 "Radio-diagnosis": [
  dict(path="radio_diagnosis/xray_chest_pa_2026-09-03.pdf", fmt="pdf", dept="Department of Radio-diagnosis", title="X-RAY CHEST PA VIEW",
       id_rows=_in["rk1_xray"][0], meta=[("Study date", "03/09/2026")],
       sections=[("Findings", "Right upper zone mass lesion. Right hilum prominent. No pleural effusion. Cardiac silhouette normal."),
                 ("Impression (reporting radiologist)", "Right upper zone mass, correlate with CT.")],
       footer=signed("FINAL", "Dr. Shalini Rao, MD (Radio-diagnosis), KMC Reg. No. 66310", "03/09/2026 17:20"), stamp="FINAL / SIGNED",
       truth=dict(doc_type="xray", status="FINAL", signed=True, report_date="2026-09-03", event_date="2026-09-03", event_label="study date", identity=_in["rk1_xray"][1],
                  expected_case="TB-001", route="case", reason="UHID SYN-100231 matches TB-001; same common name as TB-004 (SYN-400118, 58 Y) but a different person")),
  dict(path="radio_diagnosis/usg_abdomen_2026-09-10.pdf", fmt="pdf", dept="Department of Radio-diagnosis", title="ULTRASOUND ABDOMEN AND PELVIS",
       grid=_in["rk4_usg"][0] + [("Study date", "10/09/2026"), ("Reported on", "10/09/2026")], grid_cols=4,
       sections=[("Findings", "Liver normal in size and echotexture, no focal lesion. Gall bladder, pancreas, spleen and kidneys normal. No ascites. Both adrenals not well seen."),
                 ("Impression", "No sonographic abnormality in the abdomen.")],
       footer=signed("FINAL", "Dr. Shalini Rao, MD (Radio-diagnosis), KMC Reg. No. 66310", "10/09/2026 12:00"), stamp="FINAL / SIGNED",
       truth=dict(doc_type="ultrasound", status="FINAL", signed=True, report_date="2026-09-10", event_date="2026-09-10", event_label="study date", identity=_in["rk4_usg"][1],
                  expected_case="TB-004", route="case", reason="CR No. CR/2026/04118 belongs to TB-004 (only the CR No. is printed, no UHID)")),
  dict(path="radio_diagnosis/mammogram_followup_2026-09-20.pdf", fmt="pdf", dept="Department of Radio-diagnosis", title="DIGITAL MAMMOGRAPHY (FOLLOW-UP VIEWS)",
       id_rows=_in["li_mammo"][0], meta=[("Study date", "20/09/2026")],
       sections=[("Findings", "Left breast: known mass in the upper outer quadrant with a marker clip in place. Right breast: no suspicious finding."),
                 ("Assessment (reporting radiologist)", "Left breast BI-RADS 6 (known biopsy-proven malignancy). Right breast BI-RADS 1.")],
       footer=signed("FINAL", "Dr. Nisha Kulkarni, MD (Radio-diagnosis), MMC Reg. No. 2009/03/1187", "20/09/2026 16:40"), stamp="FINAL / SIGNED",
       truth=dict(doc_type="mammogram", status="FINAL", signed=True, report_date="2026-09-20", event_date="2026-09-20", event_label="study date", identity=_in["li_mammo"][1],
                  expected_case="TB-002", route="case", reason="UHID SYN-200417 matches TB-002; name spelt Laxmi (Case File says Lakshmi)")),
 ],
 "Pathology": [
  dict(path="pathology/slide_review_2026-09-12.pdf", fmt="pdf", dept="Department of Pathology", title="SLIDE REVIEW (SECOND OPINION)",
       id_rows=_in["sd5_review"][0], meta=[("Material", "Slides of left breast core biopsy HP/2026/7490, internal second opinion"), ("Received on", "10/09/2026")],
       sections=[("Opinion", "Agree with invasive breast carcinoma of no special type, grade 2.")],
       footer=signed("FINAL", "Dr. Meenakshi Iyengar, MD (Pathology), KMC Reg. No. 68814", "12/09/2026 13:00"), stamp="FINAL / SIGNED",
       truth=dict(doc_type="histopathology", status="FINAL", signed=True, report_date="2026-09-12", event_date="2026-09-10", event_label="received on", identity=_in["sd5_review"][1],
                  expected_case="TB-005", route="case", reason="UHID SYN-500263 matches TB-005; name printed with an initial")),
  dict(path="pathology/pap_smear_2026-09-15.pdf", fmt="pdf", dept="Department of Pathology", title="CERVICAL CYTOLOGY (PAP SMEAR)",
       id_rows=_in["sd2_pap"][0], meta=[("Collected on", "13/09/2026"), ("Reported on", "15/09/2026")],
       sections=[("Interpretation (Bethesda 2014)", "Negative for intraepithelial lesion or malignancy (NILM). Inflammatory smear.")],
       footer=sd("Dr. Fatima Begum, MD (Pathology)", "KMC Reg. No. 62290"),
       truth=dict(doc_type="cytology", status="FINAL", signed=True, report_date="2026-09-15", event_date="2026-09-13", event_label="collected on", identity=_in["sd2_pap"][1],
                  expected_case=None, route="new_patient_or_needs_matching",
                  reason="different person with the same common name as TB-005 (Sunita Devi, but UHID SYN-500911, 67 Y): must NOT be filed into TB-005",
                  negated=["Negative for intraepithelial lesion or malignancy"])),
 ],
 "Laboratory Medicine": [
  dict(path="laboratory_medicine/cbc_2026-09-15.png", fmt="scan", dept="Department of Laboratory Medicine", title="HAEMATOLOGY REPORT",
       grid=lab_grid(_in["sd2_cbc"][0], "15/09/2026 08:20", "15/09/2026 08:30", "15/09/2026 12:10", "OPD (Gynaecology)", "LAB/26/119870"),
       sections=[("Complete blood count", [["Investigation", "Result", "Units", "Biological ref. interval"], ["Haemoglobin", "10.8", "gm%", "12.0 - 15.0"],
                                           ["Total leucocyte count (TLC)", "5,400", "cells/cumm", "4,000 - 11,000"], ["Platelet count", "1.9", "lakhs/cumm", "1.5 - 4.1"]])],
       footer=sd("Dr. Suresh Babu, MD (Pathology)", "KMC Reg. No. 69021"), nabl=NABL,
       truth=dict(doc_type="lab", status="FINAL", signed=True, report_date="2026-09-15", event_date="2026-09-15", event_label="collected on", identity=_in["sd2_cbc"][1],
                  expected_case=None, route="new_patient_or_needs_matching",
                  reason="same common name as TB-005 but a different UHID and age; Aadhaar printed (mask it, never match on it)")),
  dict(path="laboratory_medicine/lft_2026-09-23.pdf", fmt="pdf", dept="Department of Laboratory Medicine", title="LIVER FUNCTION TESTS",
       grid=lab_grid(_in["ir_lft"][0], "23/09/2026 07:50", "23/09/2026 08:05", "23/09/2026 13:00", "Dr. Imtiaz Ahmed", "LAB/26/120555"),
       sections=[("Liver function", [["Investigation", "Result", "Units", "Biological ref. interval"], ["Total bilirubin", "0.6", "mg/dl", "0.2 - 1.2"],
                                      ["SGPT (ALT)", "22", "U/L", "< 41"], ["SGOT (AST)", "25", "U/L", "< 40"], ["Alkaline phosphatase", "88", "U/L", "40 - 129"], ["S. Albumin", "3.8", "gm/dl", "3.5 - 5.2"]])],
       footer=sd("Dr. R. Pillai, MD (Biochemistry)", "KMC Reg. No. 70418"), nabl=NABL,
       truth=dict(doc_type="lab", status="FINAL", signed=True, report_date="2026-09-23", event_date="2026-09-23", event_label="collected on", identity=_in["ir_lft"][1],
                  expected_case="TB-006", route="case", reason="MRN printed under the label 'Hospital No.'; name as Md.")),
  dict(path="laboratory_medicine/rbs_2026-09-16_no_id.pdf", fmt="pdf", dept="Department of Laboratory Medicine", title="BLOOD SUGAR REPORT",
       grid=_noid_rows + [("Collected on", "16/09/2026 09:00"), ("Reported on", "16/09/2026 11:30")], grid_cols=4,
       sections=[("Result", [["Investigation", "Result", "Units", "Biological ref. interval"], ["Random blood sugar", "132", "mg/dl", "70 - 140"]])],
       footer=sd("Dr. R. Pillai, MD (Biochemistry)", "KMC Reg. No. 70418"), nabl=NABL,
       truth=dict(doc_type="lab", status="FINAL", signed=True, report_date="2026-09-16", event_date="2026-09-16", event_label="collected on",
                  identity={"name": "Ramesh Kumar", "age_sex": "60 Y / M"},
                  expected_case=None, route="needs_matching",
                  reason="no ID printed; name fits both TB-001 (62 Y) and TB-004 (58 Y) and the age fits neither exactly: a person must decide")),
 ],
}


# =================================================================================================================
def _write_doc(d, target, weasyprint, to_scan):
    """Write one document; returns the reference text for image documents (else None)."""
    fmt = d["fmt"]
    seed = stable_seed(str(target.name))
    if fmt == "docx":
        write_docx(target, d["blocks"]); return None
    if fmt == "xlsx":
        write_xlsx(target, d["rows"]); return None
    if fmt == "bigscan":
        tmp = target.with_suffix(".tmp.pdf")
        weasyprint.HTML(string=big_scan_pages()).write_pdf(str(tmp))
        ref = pdf_text(tmp)
        to_big_scan(tmp, target, seed); tmp.unlink()
        return ref
    html = html_page(d)
    if fmt == "pdf":
        weasyprint.HTML(string=html).write_pdf(str(target)); return None
    tmp = target.with_suffix(".tmp.pdf")
    weasyprint.HTML(string=html).write_pdf(str(tmp))
    ref = None
    if fmt == "corrupt":
        corrupt_pdf(tmp, target, seed)
    elif fmt == "photo":
        ref = pdf_text(tmp); to_photo(tmp, target, seed)
    else:
        ref = pdf_text(tmp); to_scan(tmp, target, seed=seed)
    tmp.unlink()
    known = d["truth"].get("hindi_lines", []) + d["truth"].get("handwritten_lines", [])
    return fix_known_lines(ref, known) if ref is not None and known else ref


def save_ref(out, cid, rel, ref):
    if ref is None:
        return
    p = out / "truth" / "reference_text" / cid / (rel + ".txt")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(ref)


def build_v1(out, weasyprint, to_scan, only=None):
    """Write the V1 cases and the intake batches. `only` (a set of case ids) writes just those cases: their own folders under
    cases/, arrivals/ and truth/reference_text/ are replaced and their truth file rewritten; nothing else (other cases, intake)
    is touched."""
    out = Path(out)
    for cid, protocol, pat, docs, arrivals in V1_CASES:
        if only is not None and cid not in only:
            continue
        if only is not None:
            for d in (out / "cases" / cid, out / "arrivals" / cid, out / "truth" / "reference_text" / cid):
                if d.exists():
                    shutil.rmtree(d)
        truth = {"case_id": cid, "protocol": protocol, "patient": pat, "registered_identity": V1_PATIENTS[cid], "documents": {}, "arrivals": {}}
        for group, items in (("cases", docs), ("arrivals", arrivals)):
            for d in items:
                target = out / group / cid / d["path"]; target.parent.mkdir(parents=True, exist_ok=True)
                save_ref(out, cid, d["path"], _write_doc(d, target, weasyprint, to_scan))
                truth["documents" if group == "cases" else "arrivals"][d["path"]] = d["truth"]
        if cid in BOARD_DECISIONS:
            truth["board_decision"] = BOARD_DECISIONS[cid]
        (out / "truth").mkdir(parents=True, exist_ok=True)
        (out / "truth" / f"{cid}.json").write_text(json.dumps(truth, indent=2, ensure_ascii=False))
        (out / "cases" / cid / "case.json").write_text(json.dumps({"case_id": cid, "protocol": protocol, "patient": pat}, indent=2))
    if only is not None:
        return
    intake = {"note": "Department batches without a Case File. Each file must reach expected_case; null means it must NOT be filed into any existing Case File.",
              "patients": {"TB-001": P1, "TB-002": P2, "TB-004": P4, "TB-005": P5, "TB-006": P6, "TB-007": P7, "TB-008": P8, "no Case File (second Sunita Devi)": P5B},
              "files": {}}
    for dept, items in INTAKE.items():
        for d in items:
            target = out / "intake" / d["path"]; target.parent.mkdir(parents=True, exist_ok=True)
            save_ref(out, "intake", d["path"], _write_doc(d, target, weasyprint, to_scan))
            intake["files"][d["path"]] = {"department": dept, **d["truth"]}
    (out / "truth" / "intake.json").write_text(json.dumps(intake, indent=2, ensure_ascii=False))
