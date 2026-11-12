"""Hospital-system adapters by standard (after-healthathon): one module per connection method, each a subclass of
his_client.HISClient that returns the same dict shapes as the FHIR client, and a registry with per-product presets.

    fhir_generic    plain FHIR R4 servers that are not in NRCeS shapes (HAPI FHIR, OpenMRS FHIR2 / Bahmni, Epic / Cerner style)
    hl7v2           HL7 v2.x result messages (ORU^R01, MDM^T02, ORM^O01) dropped into a folder
    folder_bridge   a folder of report PDFs with an index.csv (hospitals with no API)
    abdm_bundle     ABDM health-record documents (FHIR Bundles of type `document`) in a folder
    registry        KINDS, make(settings), validate(...), describe() and the presets (protocols/his_presets.json)

Read only: nothing is ever written to a hospital system or into its folder. Adapters deliver records and candidate values; they
never mark anything verified (his_overlay checks every candidate against the report text). Design note: docs/his-adapters/DESIGN.md.
"""
