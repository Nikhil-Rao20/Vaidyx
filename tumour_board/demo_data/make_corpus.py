"""Generate SYNTHETIC Tumour Board Case Files for development, testing and demos.

Every document is fictional and watermarked "SYNTHETIC". Output layout:
  <out>/cases/<CASE_ID>/<department>/<file>     the folder a hospital would hand over (pdf text layer, scanned png, txt)
  <out>/arrivals/<CASE_ID>/<department>/<file>  documents that "arrive later" (to demo gap closure and re-check)
  <out>/truth/<CASE_ID>.json                    answer key used by the automated evaluation (never shown to the app)

Run with an environment that has weasyprint + pypdfium2 + pillow:
  python make_corpus.py --out /path/to/demo_corpus
"""
import argparse, json, random, shutil
from pathlib import Path

HOSP = "Sahyadri Cancer Institute (SYNTHETIC)"

CSS = """
@page { size: A4; margin: 16mm 15mm; }
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
.foot { margin-top: 26px; border-top: 1px solid #999; padding-top: 6px; font-size: 10pt; }
.stamp { display: inline-block; border: 2px solid #333; padding: 3px 10px; font-weight: bold; margin-top: 6px; }
p { margin: 3px 0 6px; line-height: 1.35; }
"""


def html_doc(d, patient):
    pt = "".join(f"<tr><td><b>{k}</b></td><td>{v}</td></tr>" for k, v in [
        ("Patient", patient["name"]), ("UHID", patient["mrn"]), ("Age / Sex", patient["agesex"])] + d.get("meta", []))
    body = ""
    for sec in d["sections"]:
        body += f"<h2>{sec[0]}</h2>"
        c = sec[1]
        if isinstance(c, list):
            head, *rows = c
            body += "<table class='res'><tr>" + "".join(f"<th>{h}</th>" for h in head) + "</tr>"
            body += "".join("<tr>" + "".join(f"<td>{x}</td>" for x in r) + "</tr>" for r in rows) + "</table>"
        else:
            body += "".join(f"<p>{line}</p>" for line in c.split("\n"))
    foot = "".join(f"<div>{line}</div>" for line in d["footer"])
    return f"""<html><head><meta charset='utf-8'><style>{CSS}</style></head><body>
<div class='wm'>SYNTHETIC - DEMO ONLY</div>
<div class='hdr'><div class='h'>{HOSP}</div><div class='d'>{d['dept']}</div></div>
<h1>{d['title']}</h1><table class='pt'>{pt}</table>{body}
<div class='foot'>{foot}<div class='stamp'>{d['stamp']}</div></div></body></html>"""


def signed(status, who, when):
    return [f"Report status: {status}", f"Reported by: {who} (electronically signed)", f"Signed: {when}"]


def draft(when):
    return ["Report status: DRAFT", "Reported by: (signature pending)", f"Date: {when}"]


# ----------------------------------------------------------------------------------------------------------------
# CASE TB-001: lung (NSCLC). Incomplete at first: draft pathology, PD-L1 pending, molecular awaited, brain MRI
# missing, WBC not reported. Arrivals later close every gap.
# ----------------------------------------------------------------------------------------------------------------
P1 = dict(name="SYNTHETIC, Ramesh Kumar", mrn="SYN-100231", agesex="62 Y / M")
C1 = [
 dict(path="01_clinical/medical_oncology_opd_note_2026-09-02.pdf", fmt="pdf", dept="Department of Medical Oncology",
      title="MEDICAL ONCOLOGY OPD NOTE", meta=[("Visit date", "02-Sep-2026")],
      sections=[("Presenting complaints", "Haemoptysis for 6 weeks, weight loss of 6 kg over 2 months, cough."),
                ("History", "Ex-smoker, 30 pack-years, quit in 2020. Hypertension on amlodipine 5 mg once daily. No diabetes."),
                ("Performance status", "ECOG performance status: 1"),
                ("Investigations so far", "CECT thorax (28-Aug-2026), PET/CT (06-Sep-2026) and CT-guided biopsy (08-Sep-2026) arranged."),
                ("Question for the Tumour Board", "Multidisciplinary discussion of staging and management plan.")],
      footer=signed("FINAL", "Dr. Meera Nair, Consultant Medical Oncologist", "02-Sep-2026 16:40"), stamp="FINAL / SIGNED",
      truth=dict(doc_type="clinical_note", status="FINAL", signed=True, fields={"ecog": "1", "smoking_history": "30 pack-years", "clinical_question": "staging and management plan"})),
 dict(path="02_radiology/cect_thorax_2026-08-28.pdf", fmt="pdf", dept="Department of Radiology",
      title="CECT THORAX REPORT", meta=[("Study date", "28-Aug-2026"), ("Comparison", "CT thorax 10-Nov-2025")],
      sections=[("Findings", "Spiculated mass in the right upper lobe measuring 5.2 x 4.1 cm, previously 2.1 cm on CT dated 10-Nov-2025.\n"
                             "Enlarged right hilar lymph node, 1.8 cm short axis. Subcarinal (station 7) node 1.6 cm. Right lower paratracheal (4R) node 1.2 cm.\n"
                             "No pleural effusion. Adrenal glands normal. No lytic or sclerotic bone lesion in the imaged skeleton."),
                ("Impression (reporting radiologist)", "Right upper lobe mass with interval increase in size; ipsilateral hilar and mediastinal lymphadenopathy.")],
      footer=signed("FINAL", "Dr. Arjun Rao, Consultant Radiologist", "28-Aug-2026 19:12"), stamp="FINAL / SIGNED",
      truth=dict(doc_type="ct", status="FINAL", signed=True, fields={"lesion_size": "5.2 x 4.1 cm", "nodes": "right hilar", "comparison": "10-Nov-2025"})),
 dict(path="02_radiology/ct_thorax_2025-11-10_prior.pdf", fmt="pdf", dept="Department of Radiology",
      title="CT THORAX REPORT", meta=[("Study date", "10-Nov-2025")],
      sections=[("Findings", "Solid nodule in the right upper lobe measuring 2.1 cm. No mediastinal lymphadenopathy."),
                ("Impression (reporting radiologist)", "Right upper lobe nodule. Follow-up advised.")],
      footer=signed("FINAL", "Dr. Arjun Rao, Consultant Radiologist", "10-Nov-2025 11:05"), stamp="FINAL / SIGNED",
      truth=dict(doc_type="ct", status="FINAL", signed=True, fields={"lesion_size": "2.1 cm"})),
 dict(path="03_nuclear_medicine/pet_ct_2026-09-06.png", fmt="scan", dept="Department of Nuclear Medicine",
      title="WHOLE BODY 18F-FDG PET/CT REPORT", meta=[("Study date", "06-Sep-2026")],
      sections=[("Findings (as recorded by the reporting physician)",
                 "Primary: 5.2 cm spiculated right upper lobe mass, SUVmax 14.2.\nNodes: FDG-avid right hilar (SUVmax 8.1) and subcarinal (SUVmax 6.4) lymph nodes.\n"
                 "Distant: no FDG-avid distant metastatic disease."),
                ("Staging as recorded in this report", "cT3 N2 M0, Stage IIIB (AJCC 8th edition)")],
      footer=signed("FINAL", "Dr. S. Iyer, Consultant Nuclear Medicine", "06-Sep-2026 17:05"), stamp="FINAL / SIGNED",
      truth=dict(doc_type="pet_ct", status="FINAL", signed=True, fields={"suv_max": "14.2", "recorded_stage": "cT3 N2 M0, Stage IIIB"})),
 dict(path="04_pathology/histopathology_2026-09-08_draft.png", fmt="scan", dept="Department of Pathology",
      title="HISTOPATHOLOGY REPORT", meta=[("Specimen", "CT-guided core biopsy, right upper lobe lesion"), ("Received", "08-Sep-2026")],
      sections=[("Microscopy", "Cores show infiltrating malignant glands with acinar predominant pattern."),
                ("Diagnosis", "Adenocarcinoma, lung, acinar predominant."),
                ("Immunohistochemistry", [["Marker", "Result"], ["TTF-1", "Positive"], ["Napsin A", "Positive"], ["p40", "Negative"], ["PD-L1 (22C3) TPS", "Pending"]]),
                ("Molecular testing", "EGFR / ALK / ROS1: sample sent to reference laboratory, result awaited.")],
      footer=draft("08-Sep-2026"), stamp="DRAFT / UNSIGNED",
      truth=dict(doc_type="histopathology", status="DRAFT", signed=False, fields={"histologic_type": "Adenocarcinoma", "pdl1": None, "egfr": None})),
 dict(path="05_lab/cbc_2026-09-04.png", fmt="scan", dept="Department of Laboratory Medicine",
      title="HAEMATOLOGY REPORT (CBC)", meta=[("Sample date", "04-Sep-2026")],
      sections=[("Complete blood count", [["Test", "Result", "Unit", "Ref. range"], ["Haemoglobin", "11.8", "g/dL", "13.0 - 17.0"],
                                          ["WBC count", "Not reported", "x10^3/uL", "4.0 - 11.0"], ["Platelet count", "245", "x10^3/uL", "150 - 410"]]),
                ("Comment", "WBC count not available for this sample (clotted). Repeat sample requested.")],
      footer=signed("FINAL", "Dr. A. Menon, Consultant Pathologist", "04-Sep-2026 11:42"), stamp="FINAL / SIGNED",
      truth=dict(doc_type="lab", status="FINAL", signed=True, fields={"haemoglobin": "11.8", "wbc": None, "platelets": "245"})),
 dict(path="05_lab/renal_liver_function_2026-09-04.pdf", fmt="pdf", dept="Department of Biochemistry",
      title="BIOCHEMISTRY REPORT", meta=[("Sample date", "04-Sep-2026")],
      sections=[("Renal and liver function", [["Test", "Result", "Unit", "Ref. range"], ["Serum creatinine", "0.9", "mg/dL", "0.7 - 1.3"], ["eGFR", "88", "mL/min/1.73m2", "> 60"],
                                               ["Total bilirubin", "0.7", "mg/dL", "0.2 - 1.2"], ["ALT", "32", "U/L", "< 41"], ["AST", "28", "U/L", "< 40"], ["Albumin", "3.9", "g/dL", "3.5 - 5.2"], ["Sodium", "138", "mmol/L", "135 - 145"]])],
      footer=signed("FINAL", "Dr. R. Pillai, Consultant Biochemist", "04-Sep-2026 13:10"), stamp="FINAL / SIGNED",
      truth=dict(doc_type="lab", status="FINAL", signed=True, fields={"creatinine": "0.9"})),
 dict(path="06_discharge/discharge_summary_2026-09-05.pdf", fmt="pdf", dept="Department of Medicine",
      title="DISCHARGE SUMMARY", meta=[("Admitted / Discharged", "01-Sep-2026 / 05-Sep-2026")],
      sections=[("Reason for admission", "Haemoptysis."),
                ("Course in hospital", "Haemodynamically stable. Tranexamic acid given for 48 hours. IV antibiotics were not required. Biopsy planned as outpatient."),
                ("Medications at discharge", "Amlodipine 5 mg once daily. Pantoprazole 40 mg once daily.")],
      footer=signed("FINAL", "Dr. K. Nair, Consultant Physician", "05-Sep-2026 19:20"), stamp="FINAL / SIGNED",
      truth=dict(doc_type="discharge_summary", status="FINAL", signed=True, fields={"iv_antibiotics": "not required"})),
]
A1 = [
 dict(path="04_pathology/histopathology_2026-09-12_final.pdf", fmt="pdf", dept="Department of Pathology",
      title="HISTOPATHOLOGY REPORT (FINAL)", meta=[("Specimen", "CT-guided core biopsy, right upper lobe lesion"), ("Received", "08-Sep-2026")],
      sections=[("Microscopy", "Cores show infiltrating malignant glands with acinar predominant pattern."),
                ("Diagnosis", "Adenocarcinoma, lung, acinar predominant."),
                ("Immunohistochemistry", [["Marker", "Result"], ["TTF-1", "Positive"], ["Napsin A", "Positive"], ["p40", "Negative"], ["PD-L1 (22C3) TPS", "60%"]]),
                ("Molecular testing", "EGFR / ALK / ROS1: see separate molecular pathology report.")],
      footer=signed("FINAL", "Dr. Kavita Shah, Consultant Pathologist", "12-Sep-2026 15:30"), stamp="FINAL / SIGNED",
      truth=dict(doc_type="histopathology", status="FINAL", signed=True, fields={"histologic_type": "Adenocarcinoma", "pdl1": "60%"})),
 dict(path="07_molecular/molecular_pathology_2026-09-15.pdf", fmt="pdf", dept="Molecular Pathology Laboratory",
      title="MOLECULAR PATHOLOGY REPORT", meta=[("Specimen", "FFPE block from CT-guided biopsy (08-Sep-2026)")],
      sections=[("Results", [["Test", "Method", "Result"], ["EGFR (exons 18-21)", "Real-time PCR", "No mutation detected"],
                             ["ALK", "IHC (D5F3)", "Negative"], ["ROS1", "IHC (D4D6)", "Negative"], ["KRAS G12C", "Real-time PCR", "Detected"]])],
      footer=signed("FINAL", "Dr. P. Banerjee, Molecular Pathologist", "15-Sep-2026 10:15"), stamp="FINAL / SIGNED",
      truth=dict(doc_type="molecular", status="FINAL", signed=True, fields={"egfr": "No mutation detected", "alk": "Negative", "ros1": "Negative", "kras": "Detected"})),
 dict(path="02_radiology/mri_brain_2026-09-14.pdf", fmt="pdf", dept="Department of Radiology",
      title="MRI BRAIN WITH CONTRAST REPORT", meta=[("Study date", "14-Sep-2026")],
      sections=[("Findings", "No enhancing intracranial lesion. No midline shift. Ventricles normal."),
                ("Impression (reporting radiologist)", "No evidence of intracranial metastasis.")],
      footer=signed("FINAL", "Dr. Arjun Rao, Consultant Radiologist", "14-Sep-2026 18:00"), stamp="FINAL / SIGNED",
      truth=dict(doc_type="mri", status="FINAL", signed=True, fields={})),
 dict(path="05_lab/cbc_2026-09-14.pdf", fmt="pdf", dept="Department of Laboratory Medicine",
      title="HAEMATOLOGY REPORT (CBC)", meta=[("Sample date", "14-Sep-2026")],
      sections=[("Complete blood count", [["Test", "Result", "Unit", "Ref. range"], ["Haemoglobin", "12.1", "g/dL", "13.0 - 17.0"],
                                          ["WBC count", "7.8", "x10^3/uL", "4.0 - 11.0"], ["Platelet count", "262", "x10^3/uL", "150 - 410"]])],
      footer=signed("FINAL", "Dr. A. Menon, Consultant Pathologist", "14-Sep-2026 12:02"), stamp="FINAL / SIGNED",
      truth=dict(doc_type="lab", status="FINAL", signed=True, fields={"haemoglobin": "12.1", "wbc": "7.8", "platelets": "262"})),
]

# ----------------------------------------------------------------------------------------------------------------
# CASE TB-002: breast. Complete; includes an IHC report superseded by a FISH addendum.
# ----------------------------------------------------------------------------------------------------------------
P2 = dict(name="SYNTHETIC, Lakshmi Iyer", mrn="SYN-200417", agesex="48 Y / F")
C2 = [
 dict(path="clinical/surgical_oncology_note_2026-08-20.pdf", fmt="pdf", dept="Department of Surgical Oncology",
      title="SURGICAL ONCOLOGY CLINIC NOTE", meta=[("Visit date", "20-Aug-2026")],
      sections=[("History", "Painless lump in the left breast for 3 months. Premenopausal. Mother had breast cancer at 55 years."),
                ("Examination", "3 cm firm mass, upper outer quadrant, left breast. Palpable mobile left axillary node."),
                ("Performance status", "ECOG performance status: 0"),
                ("Clinical stage as recorded by the treating surgeon", "cT2 N1 M0, Stage IIB (AJCC 8th edition, anatomic)"),
                ("Question for the Tumour Board", "Discussion of sequencing of treatment.")],
      footer=signed("FINAL", "Dr. Vivek Menon, Consultant Surgical Oncologist", "20-Aug-2026 13:15"), stamp="FINAL / SIGNED",
      truth=dict(doc_type="clinical_note", status="FINAL", signed=True, fields={"ecog": "0", "menopausal_status": "Premenopausal", "recorded_stage": "cT2 N1 M0"})),
 dict(path="radiology/mammogram_ultrasound_2026-08-12.pdf", fmt="pdf", dept="Department of Radiology",
      title="BILATERAL MAMMOGRAPHY AND BREAST ULTRASOUND", meta=[("Study date", "12-Aug-2026")],
      sections=[("Findings", "Left breast upper outer quadrant: irregular spiculated mass, 2.8 x 2.4 cm.\nLeft axilla: one node with cortical thickening, 1.4 cm.\nRight breast: no suspicious finding."),
                ("Assessment (reporting radiologist)", "Left breast BI-RADS 5. Right breast BI-RADS 1.")],
      footer=signed("FINAL", "Dr. Nisha Kulkarni, Consultant Radiologist", "12-Aug-2026 17:40"), stamp="FINAL / SIGNED",
      truth=dict(doc_type="mammogram", status="FINAL", signed=True, fields={"lesion_size": "2.8 x 2.4 cm", "birads": "BI-RADS 5"})),
 dict(path="radiology/mri_breast_2026-08-18.pdf", fmt="pdf", dept="Department of Radiology",
      title="MRI BREAST (BILATERAL) WITH CONTRAST", meta=[("Study date", "18-Aug-2026")],
      sections=[("Findings", "Left breast: irregular enhancing mass, 3.1 x 2.6 x 2.5 cm, upper outer quadrant. No multifocal or multicentric disease.\nRight breast: no suspicious enhancement.\nLeft axilla: one abnormal level I node."),
                ("Impression (reporting radiologist)", "Unifocal left breast mass, 3.1 cm. Single abnormal left axillary node.")],
      footer=signed("FINAL", "Dr. Nisha Kulkarni, Consultant Radiologist", "18-Aug-2026 20:05"), stamp="FINAL / SIGNED",
      truth=dict(doc_type="mri", status="FINAL", signed=True, fields={"lesion_size": "3.1 x 2.6 x 2.5 cm"})),
 dict(path="pathology/core_biopsy_histopathology_2026-08-16.pdf", fmt="pdf", dept="Department of Pathology",
      title="HISTOPATHOLOGY REPORT", meta=[("Specimen", "Ultrasound-guided core biopsy, left breast mass"), ("Received", "14-Aug-2026")],
      sections=[("Diagnosis", "Invasive breast carcinoma of no special type (ductal)."),
                ("Grade", "Nottingham grade 2 (tubules 3, pleomorphism 2, mitoses 2; score 7/9)."),
                ("Lymphovascular invasion", "Not identified in the cores.")],
      footer=signed("FINAL", "Dr. Kavita Shah, Consultant Pathologist", "16-Aug-2026 12:20"), stamp="FINAL / SIGNED",
      truth=dict(doc_type="histopathology", status="FINAL", signed=True, fields={"histologic_type": "Invasive breast carcinoma of no special type", "grade": "Nottingham grade 2"})),
 dict(path="pathology/fnac_left_axilla_2026-08-16.pdf", fmt="pdf", dept="Department of Pathology",
      title="CYTOLOGY REPORT (FNAC)", meta=[("Specimen", "FNAC, left axillary lymph node")],
      sections=[("Diagnosis", "Positive for metastatic carcinoma.")],
      footer=signed("FINAL", "Dr. Kavita Shah, Consultant Pathologist", "16-Aug-2026 12:45"), stamp="FINAL / SIGNED",
      truth=dict(doc_type="cytology", status="FINAL", signed=True, fields={})),
 dict(path="pathology/ihc_breast_2026-08-19_preliminary.pdf", fmt="pdf", dept="Department of Pathology",
      title="IMMUNOHISTOCHEMISTRY REPORT (PRELIMINARY)", meta=[("Specimen", "Core biopsy, left breast")],
      sections=[("Results", [["Marker", "Result"], ["Estrogen receptor (ER)", "Positive, 90% strong (Allred 8)"], ["Progesterone receptor (PR)", "Positive, 70% (Allred 7)"],
                             ["HER2 (IHC)", "2+ (equivocal); reflex FISH sent"], ["Ki-67", "25%"]])],
      footer=["Report status: PRELIMINARY (pending HER2 FISH)", "Reported by: Dr. Kavita Shah, Consultant Pathologist (electronically signed)", "Signed: 19-Aug-2026 10:30"], stamp="PRELIMINARY",
      truth=dict(doc_type="ihc", status="PRELIMINARY", signed=True, fields={"er": "90%", "pr": "70%", "her2": "2+", "ki67": "25%"})),
 dict(path="pathology/her2_fish_addendum_2026-08-25.pdf", fmt="pdf", dept="Department of Pathology",
      title="ADDENDUM: HER2 FISH", meta=[("Specimen", "Core biopsy, left breast"), ("Relates to", "IHC report of 19-Aug-2026")],
      sections=[("HER2 in situ hybridisation", "HER2/CEP17 ratio: 1.3. Average HER2 copy number: 3.1 signals per cell.\nResult: HER2 not amplified (ASCO/CAP 2023 group 5)."),
                ("Final receptor status", "ER positive (90%), PR positive (70%), HER2 negative (IHC 2+, FISH not amplified), Ki-67 25%.")],
      footer=signed("FINAL (AMENDED)", "Dr. Kavita Shah, Consultant Pathologist", "25-Aug-2026 16:00"), stamp="FINAL / SIGNED",
      truth=dict(doc_type="ihc", status="FINAL", signed=True, fields={"her2": "not amplified", "er": "90%", "ki67": "25%"})),
 dict(path="radiology/cect_chest_abdomen_2026-08-22.pdf", fmt="pdf", dept="Department of Radiology",
      title="CECT CHEST AND ABDOMEN (STAGING)", meta=[("Study date", "22-Aug-2026")],
      sections=[("Findings", "Lungs clear. No pleural effusion. Liver normal in size with no focal lesion. Adrenals normal. No abdominal lymphadenopathy."),
                ("Impression (reporting radiologist)", "No evidence of distant metastatic disease in the chest or abdomen.")],
      footer=signed("FINAL", "Dr. Arjun Rao, Consultant Radiologist", "22-Aug-2026 18:30"), stamp="FINAL / SIGNED",
      truth=dict(doc_type="ct", status="FINAL", signed=True, fields={})),
 dict(path="nuclear_medicine/bone_scan_2026-08-23.png", fmt="scan", dept="Department of Nuclear Medicine",
      title="WHOLE BODY BONE SCAN (99mTc-MDP)", meta=[("Study date", "23-Aug-2026")],
      sections=[("Findings", "Physiological tracer distribution. No focal abnormal tracer uptake to suggest skeletal metastasis."),
                ("Impression (reporting physician)", "No scintigraphic evidence of skeletal metastasis.")],
      footer=signed("FINAL", "Dr. S. Iyer, Consultant Nuclear Medicine", "23-Aug-2026 15:20"), stamp="FINAL / SIGNED",
      truth=dict(doc_type="bone_scan", status="FINAL", signed=True, fields={})),
 dict(path="lab/blood_tests_2026-08-20.pdf", fmt="pdf", dept="Department of Laboratory Medicine",
      title="HAEMATOLOGY AND BIOCHEMISTRY", meta=[("Sample date", "20-Aug-2026")],
      sections=[("Results", [["Test", "Result", "Unit", "Ref. range"], ["Haemoglobin", "12.9", "g/dL", "12.0 - 15.0"], ["WBC count", "6.4", "x10^3/uL", "4.0 - 11.0"],
                             ["Platelet count", "280", "x10^3/uL", "150 - 410"], ["Serum creatinine", "0.7", "mg/dL", "0.5 - 1.1"], ["ALT", "21", "U/L", "< 35"], ["Total bilirubin", "0.5", "mg/dL", "0.2 - 1.2"]])],
      footer=signed("FINAL", "Dr. A. Menon, Consultant Pathologist", "20-Aug-2026 14:00"), stamp="FINAL / SIGNED",
      truth=dict(doc_type="lab", status="FINAL", signed=True, fields={"haemoglobin": "12.9", "wbc": "6.4", "platelets": "280", "creatinine": "0.7"})),
]

# ----------------------------------------------------------------------------------------------------------------
# CASE TB-003: rectal, re-discussion after neoadjuvant chemoradiation. Restaging MRI pelvis missing.
# ----------------------------------------------------------------------------------------------------------------
P3 = dict(name="SYNTHETIC, Abdul Rahman", mrn="SYN-300582", agesex="57 Y / M")
C3 = [
 dict(path="clinical/gi_oncology_note_2026-09-18.txt", fmt="txt", dept="Department of GI Oncology", title="GI ONCOLOGY FOLLOW-UP NOTE",
      text="""SAHYADRI CANCER INSTITUTE (SYNTHETIC) - DEPARTMENT OF GI ONCOLOGY
GI ONCOLOGY FOLLOW-UP NOTE
Patient: SYNTHETIC, Abdul Rahman | MRN: SYN-300582 | 57 Y / M
Visit date: 18-Sep-2026

Diagnosis on record: adenocarcinoma of the rectum (biopsy 02-Jun-2026).
Completed long-course chemoradiation (50.4 Gy in 28 fractions with capecitabine) on 10-Aug-2026.
Tolerated well. Mild proctitis, settled. Type 2 diabetes on metformin 500 mg twice daily.
ECOG performance status: 1
Restaging MRI pelvis requested, appointment awaited.
Question for the Tumour Board: re-discussion after completion of chemoradiation, as planned at the Tumour Board of 12-Jun-2026.

Report status: FINAL
Signed: Dr. Farhan Siddiqui, Consultant GI Oncologist (electronically signed) 18-Sep-2026 12:30
""", truth=dict(doc_type="clinical_note", status="FINAL", signed=True, fields={"ecog": "1"})),
 dict(path="endoscopy/colonoscopy_2026-05-30.pdf", fmt="pdf", dept="Department of Gastroenterology",
      title="COLONOSCOPY REPORT", meta=[("Procedure date", "30-May-2026")],
      sections=[("Findings", "Circumferential ulceroproliferative growth from 6 cm to 11 cm from the anal verge. Scope could be negotiated beyond. Rest of the colon normal to caecum."),
                ("Procedure", "Multiple biopsies taken from the growth.")],
      footer=signed("FINAL", "Dr. L. Thomas, Consultant Gastroenterologist", "30-May-2026 13:45"), stamp="FINAL / SIGNED",
      truth=dict(doc_type="endoscopy", status="FINAL", signed=True, fields={"distance_from_anal_verge": "6 cm"})),
 dict(path="pathology/rectal_biopsy_2026-06-02.pdf", fmt="pdf", dept="Department of Pathology",
      title="HISTOPATHOLOGY REPORT", meta=[("Specimen", "Endoscopic biopsies, rectal growth")],
      sections=[("Diagnosis", "Adenocarcinoma, moderately differentiated."),
                ("Mismatch repair proteins (IHC)", [["Protein", "Result"], ["MLH1", "Retained"], ["PMS2", "Retained"], ["MSH2", "Retained"], ["MSH6", "Retained"]]),
                ("Interpretation of MMR IHC (as reported)", "Mismatch repair proficient (pMMR)."),
                ("KRAS / NRAS / BRAF", "Not performed.")],
      footer=signed("FINAL", "Dr. Kavita Shah, Consultant Pathologist", "02-Jun-2026 17:10"), stamp="FINAL / SIGNED",
      truth=dict(doc_type="histopathology", status="FINAL", signed=True, fields={"histologic_type": "Adenocarcinoma", "grade": "moderately differentiated", "mmr": "proficient"})),
 dict(path="radiology/mri_pelvis_2026-06-05_baseline.pdf", fmt="pdf", dept="Department of Radiology",
      title="MRI PELVIS (RECTAL CANCER PROTOCOL), BASELINE", meta=[("Study date", "05-Jun-2026")],
      sections=[("Findings", "Tumour in the mid rectum, lower edge 6 cm from the anal verge, 5.5 cm craniocaudal length.\n"
                             "Extramural spread 6 mm (mrT3c). Mesorectal fascia: tumour 1 mm from the fascia (threatened).\n"
                             "EMVI: positive. Two mesorectal lymph nodes with irregular borders."),
                ("Staging as recorded by the reporting radiologist", "mrT3c N1, MRF threatened, EMVI positive.")],
      footer=signed("FINAL", "Dr. Nisha Kulkarni, Consultant Radiologist", "05-Jun-2026 19:40"), stamp="FINAL / SIGNED",
      truth=dict(doc_type="mri", status="FINAL", signed=True, fields={"recorded_stage": "mrT3c N1", "mrf": "threatened", "emvi": "positive"})),
 dict(path="radiology/cect_chest_abdomen_pelvis_2026-06-06.pdf", fmt="pdf", dept="Department of Radiology",
      title="CECT CHEST, ABDOMEN AND PELVIS", meta=[("Study date", "06-Jun-2026")],
      sections=[("Findings", "No pulmonary nodules. Liver without focal lesion. No retroperitoneal lymphadenopathy. Rectal wall thickening as known."),
                ("Impression (reporting radiologist)", "No distant metastatic disease.")],
      footer=signed("FINAL", "Dr. Arjun Rao, Consultant Radiologist", "06-Jun-2026 18:05"), stamp="FINAL / SIGNED",
      truth=dict(doc_type="ct", status="FINAL", signed=True, fields={})),
 dict(path="lab/cea_2026-06-04.pdf", fmt="pdf", dept="Department of Biochemistry",
      title="TUMOUR MARKER REPORT", meta=[("Sample date", "04-Jun-2026")],
      sections=[("Result", [["Test", "Result", "Unit", "Ref. range"], ["CEA", "35.2", "ng/mL", "< 5.0"]])],
      footer=signed("FINAL", "Dr. R. Pillai, Consultant Biochemist", "04-Jun-2026 15:00"), stamp="FINAL / SIGNED",
      truth=dict(doc_type="lab", status="FINAL", signed=True, fields={"cea": "35.2"})),
 dict(path="lab/blood_tests_2026-09-15.png", fmt="scan", dept="Department of Laboratory Medicine",
      title="HAEMATOLOGY AND BIOCHEMISTRY", meta=[("Sample date", "15-Sep-2026")],
      sections=[("Results", [["Test", "Result", "Unit", "Ref. range"], ["Haemoglobin", "10.9", "g/dL", "13.0 - 17.0"], ["WBC count", "5.2", "x10^3/uL", "4.0 - 11.0"],
                             ["Platelet count", "198", "x10^3/uL", "150 - 410"], ["Serum creatinine", "1.0", "mg/dL", "0.7 - 1.3"], ["CEA", "12.4", "ng/mL", "< 5.0"]])],
      footer=signed("FINAL", "Dr. A. Menon, Consultant Pathologist", "15-Sep-2026 11:20"), stamp="FINAL / SIGNED",
      truth=dict(doc_type="lab", status="FINAL", signed=True, fields={"haemoglobin": "10.9", "wbc": "5.2", "cea": "12.4"})),
 dict(path="tumour_board/tumour_board_record_2026-06-12.pdf", fmt="pdf", dept="Multidisciplinary Tumour Board",
      title="TUMOUR BOARD RECORD", meta=[("Board date", "12-Jun-2026")],
      sections=[("Present", "Surgical oncology, radiation oncology, medical oncology, radiology, pathology."),
                ("Decision recorded by the board", "Long-course chemoradiation. Restaging MRI pelvis 8 to 10 weeks after completion. Re-discuss at the Tumour Board with restaging."),
                ("Actions", "Radiation Oncology: start chemoradiation. Radiology: restaging MRI pelvis after completion.")],
      footer=["Record status: FINAL", "Recorded by: Dr. Farhan Siddiqui, Tumour Board coordinator (electronically signed)", "Signed: 12-Jun-2026 18:00"], stamp="FINAL / SIGNED",
      truth=dict(doc_type="tumour_board_record", status="FINAL", signed=True, fields={})),
 dict(path="radiotherapy/rt_completion_summary_2026-08-10.pdf", fmt="pdf", dept="Department of Radiation Oncology",
      title="RADIOTHERAPY COMPLETION SUMMARY", meta=[("Treatment dates", "30-Jun-2026 to 10-Aug-2026")],
      sections=[("Treatment delivered", "50.4 Gy in 28 fractions to the pelvis (IMRT) with concurrent capecitabine 825 mg/m2 twice daily on radiotherapy days."),
                ("Acute toxicity", "Grade 1 proctitis, grade 1 skin reaction.")],
      footer=signed("FINAL", "Dr. Sunita Rao, Consultant Radiation Oncologist", "10-Aug-2026 17:30"), stamp="FINAL / SIGNED",
      truth=dict(doc_type="treatment_summary", status="FINAL", signed=True, fields={"dose": "50.4 Gy in 28 fractions"})),
]

A3 = [
 dict(path="radiology/mri_pelvis_restaging_2026-10-01.pdf", fmt="pdf", dept="Department of Radiology",
      title="MRI PELVIS (RECTAL CANCER PROTOCOL), RESTAGING", meta=[("Study date", "01-Oct-2026"), ("Comparison", "MRI pelvis 05-Jun-2026")],
      sections=[("Findings", "Mid rectal tumour, lower edge 6 cm from the anal verge, reduced in bulk compared with 05-Jun-2026.\n"
                             "Residual intermediate signal confined to the rectal wall with fibrosis. Mesorectal fascia: clear, closest distance 4 mm.\n"
                             "EMVI: no longer seen. Mesorectal nodes reduced in size, largest 4 mm."),
                ("Restaging as recorded by the reporting radiologist", "ymrT2 N0, MRF clear, EMVI negative, mrTRG 2.")],
      footer=signed("FINAL", "Dr. Nisha Kulkarni, Consultant Radiologist", "01-Oct-2026 18:20"), stamp="FINAL / SIGNED",
      truth=dict(doc_type="mri", status="FINAL", signed=True, fields={"recorded_stage": "ymrT2 N0", "mrf_status": "clear"})),
 dict(path="lab/cbc_kft_cea_2026-09-29.png", fmt="scan", dept="Department of Pathology and Laboratory Medicine",
      title="LABORATORY REPORT", meta=[("Sample collected", "29/09/2026 08:40"), ("Referred by", "Dr. Farhan Siddiqui (GI Oncology)"), ("Lab No.", "L-2609-11873")],
      sections=[("Haematology", [["Investigation", "Result", "Units", "Biological ref. interval"], ["Haemoglobin (Hb)", "11.2", "gm/dl", "13.0 - 17.0"],
                                  ["Total leucocyte count (TLC)", "6,400", "/cumm", "4,000 - 11,000"], ["Platelet count", "2.10", "lakh/cumm", "1.50 - 4.10"]]),
                ("Biochemistry", [["Investigation", "Result", "Units", "Biological ref. interval"], ["S. Creatinine", "0.9", "mg/dl", "0.7 - 1.3"], ["CEA", "4.1", "ng/ml", "< 5.0"]])],
      footer=["Report status: FINAL", "Checked and verified by: Dr. A. Menon, MD (Pathology) (electronically signed)", "Signed: 29/09/2026 14:05"], stamp="FINAL / SIGNED",
      truth=dict(doc_type="lab", status="FINAL", signed=True, fields={"haemoglobin": "11.2", "wbc": "6,400", "platelets": "2.10", "creatinine": "0.9", "cea": "4.1"})),
]

CASES = [("TB-001", "lung_nsclc", P1, C1, A1), ("TB-002", "breast", P2, C2, []), ("TB-003", "colorectal_rectum", P3, C3, A3)]


def to_scan(pdf_path, png_path, seed):
    import pypdfium2 as pdfium
    from PIL import Image, ImageFilter
    import numpy as np
    rnd = random.Random(seed)
    pg = pdfium.PdfDocument(str(pdf_path))[0]
    im = pg.render(scale=1.45).to_pil().convert("L")  # ~105 dpi, like a fast office scanner
    im = im.rotate(rnd.uniform(-0.8, 0.8), resample=Image.BICUBIC, expand=False, fillcolor=255)
    a = np.asarray(im).astype(np.float32)
    a = a * 0.93 + 10 + np.random.default_rng(seed).normal(0, 6, a.shape)  # paper tone + sensor noise
    im = Image.fromarray(np.clip(a, 0, 255).astype("uint8")).filter(ImageFilter.GaussianBlur(0.35))
    im.save(png_path, optimize=True)


def build(out):
    import weasyprint
    out = Path(out)
    if out.exists(): shutil.rmtree(out)
    for cid, protocol, pat, docs, arrivals in CASES:
        truth = {"case_id": cid, "protocol": protocol, "patient": pat, "documents": {}, "arrivals": {}}
        for group, items in (("cases", docs), ("arrivals", arrivals)):
            for i, d in enumerate(items):
                target = out / group / cid / d["path"]; target.parent.mkdir(parents=True, exist_ok=True)
                if d["fmt"] == "txt":
                    target.write_text(d["text"])
                else:
                    html = html_doc(d, pat)
                    if d["fmt"] == "pdf":
                        weasyprint.HTML(string=html).write_pdf(str(target))
                    else:
                        tmp = target.with_suffix(".tmp.pdf"); weasyprint.HTML(string=html).write_pdf(str(tmp))
                        to_scan(tmp, target, seed=hash(d["path"]) % 10000); tmp.unlink()
                truth["documents" if group == "cases" else "arrivals"][d["path"]] = d["truth"]
        (out / "truth").mkdir(parents=True, exist_ok=True)
        (out / "truth" / f"{cid}.json").write_text(json.dumps(truth, indent=2))
        (out / "cases" / cid / "case.json").write_text(json.dumps({"case_id": cid, "protocol": protocol, "patient": pat}, indent=2))
    print("written", out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--out", required=True); build(ap.parse_args().out)
