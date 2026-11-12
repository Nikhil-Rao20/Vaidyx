"""Signature from a connection that cannot carry one (12 Nov 2026, after the Health-a-thon): HL7 v2 files, a report folder, ABDM bundle
files and plain FHIR without Provenance deliver no signature Vaidyx-TB can verify. The hospital system's status still stands; whether
the report is signed is then read from the report text (as for an uploaded report), never "yes" from the connection itself. The demo
hospital (NRCeS FHIR, carries signatures) keeps its rule: no signature for a version means not signed. Synthetic data only."""
import pytest

from tumour_board import his_client, his_overlay
from tumour_board.his_adapters import abdm_bundle, fhir_generic, folder_bridge, hl7v2


def _doc(text_status, text_signed, his_status="final", carried=None, signature=None):
    his = {"id": "rep-1", "version": 1, "status": his_status, "signature": signature}
    if carried is not None:
        his["signature_carried"] = carried
    return {"doc_id": "D1", "his": his, "pages": [{"text": "SYNTHETIC\nHISTOPATHOLOGY REPORT\nReport status: FINAL"}],
            "classification": {"status": text_status, "signed": text_signed, "status_quote": "", "signature_quote": "Reported by: Dr A (SYNTHETIC)"}}


def test_the_demo_hospital_rule_is_unchanged():
    c = his_overlay.apply_status(_doc("FINAL", "yes"))["classification"]            # no key at all: as before
    assert c["signed"] == "no" and c["signed_source"] == "his"
    c = his_overlay.apply_status(_doc("FINAL", "yes", carried=True))["classification"]
    assert c["signed"] == "no" and any("no digital signature for this version" in n for n in c["status_notes"])


@pytest.mark.parametrize("text_signed", ["yes", "no", "unknown"])
def test_a_connection_without_signatures_leaves_it_to_the_report_text(text_signed):
    c = his_overlay.apply_status(_doc("FINAL", text_signed, carried=False))["classification"]
    assert c["signed"] == text_signed and c["signed_source"] == "text" and "his_signature" not in c
    assert c["status"] == "FINAL" and c["status_source"] == "his"                    # the hospital system's status still stands
    assert any("carries no digital signature" in n for n in c["status_notes"])


def test_a_preliminary_report_never_counts_whatever_its_text_says():
    c = his_overlay.apply_status(_doc("FINAL", "yes", his_status="preliminary", carried=False))["classification"]
    assert c["status"] in his_overlay.NEGATIVE and c["signed"] == "yes"             # signed text, but the status is not final


def test_the_overlay_is_idempotent_for_such_a_connection():
    d = _doc("FINAL", "unknown", carried=False)
    a = dict(his_overlay.apply_status(d)["classification"]); b = dict(his_overlay.apply_status(d)["classification"])
    assert a == b and sum("carries no digital signature" in n for n in b["status_notes"]) == 1


def test_which_connections_carry_a_signature():
    assert his_client.HISClient.carries_signature is True and his_client.FHIRClient.carries_signature is True
    for cls in (hl7v2.HL7v2FolderClient, folder_bridge.FolderBridgeClient, abdm_bundle.ABDMBundleClient, fhir_generic.GenericFHIRClient):
        assert cls.carries_signature is False, cls.__name__
