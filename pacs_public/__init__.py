"""Public-image library for the Vaidyx-TB demo PACS: de-identified CC BY research images from The Cancer Imaging
Archive (TCIA), downloaded into /data/vaidyx/tb_resources/dicom_public/, face-checked, and relabelled with the
synthetic identities of the mock hospital (his_mock) before they reach Orthanc. See pacs_public/README.md.

Modules: manifest (collections, licences, roles, MANIFEST.json/csv, LICENCES.md), relabel (assignment planner,
DICOM relabelling, verification), qa_check (face and burned-in text check renders). No module here reads the real case.
"""
