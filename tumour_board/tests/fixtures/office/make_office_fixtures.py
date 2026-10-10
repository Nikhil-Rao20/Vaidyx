"""Build the small SYNTHETIC office fixtures used by test_ingest.py (no real patient data).

    /data/vaidyx/venv/app/bin/python tumour_board/tests/fixtures/office/make_office_fixtures.py

Writes lab_values.xlsx (sheets Haematology, Biochemistry) and board_slides.pptx (2 slides) next to this script."""
from pathlib import Path

HERE = Path(__file__).resolve().parent


def make_xlsx(path: Path):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Haematology"
    for row in [("Investigation", "Result", "Units"),
                ("Patient", "SYNTHETIC, Test Patient", ""),
                ("UHID", "SYN-900001", ""),
                ("Haemoglobin", "11.8", "g/dL"),
                ("Platelets", "2.45", "lakhs/cumm"),
                ("Note", "SYNTHETIC - DEMO ONLY", "")]:
        ws.append(row)
    ws2 = wb.create_sheet("Biochemistry")
    for row in [("Investigation", "Result", "Units"),
                ("UHID", "SYN-900001", ""),
                ("Creatinine", "0.9", "mg/dL"),
                ("Note", "SYNTHETIC - DEMO ONLY", "")]:
        ws2.append(row)
    wb.properties.creator = "SYNTHETIC"
    wb.save(path)


def make_pptx(path: Path):
    from pptx import Presentation
    prs = Presentation()
    s1 = prs.slides.add_slide(prs.slide_layouts[0])
    s1.shapes.title.text = "Tumour Board Case File SYN-900001 (SYNTHETIC)"
    s1.placeholders[1].text = "SYNTHETIC - DEMO ONLY"
    s2 = prs.slides.add_slide(prs.slide_layouts[1])
    s2.shapes.title.text = "Findings (SYNTHETIC)"
    body = s2.placeholders[1].text_frame
    body.text = "Histopathology: adenocarcinoma"
    body.add_paragraph().text = "PD-L1 TPS 60%"
    prs.core_properties.author = "SYNTHETIC"
    prs.save(path)


if __name__ == "__main__":
    make_xlsx(HERE / "lab_values.xlsx")
    make_pptx(HERE / "board_slides.pptx")
    print("wrote", HERE / "lab_values.xlsx", HERE / "board_slides.pptx")
