// "Choose your hospital system" (docs/new-case/DESIGN.md N7) in mock mode: GET /his/kinds, POST /his/try and POST /setup/his answered
// here for e2e/shots/his-chooser.spec.ts. The kinds and presets are copied from tumour_board/his_adapters/registry.py and
// protocols/his_presets.json (17 Nov 2026). SYNTHETIC values only; no secret ever comes back.
import type { Page, Route } from "@playwright/test";

export const hisKindsData = {
 "kinds": [
  {
   "kind": "fhir",
   "label": "FHIR R4 in ABDM / NRCeS shapes",
   "tested": true,
   "description": "A hospital system that serves FHIR R4 in the Indian (NRCeS) profiles, as the demo hospital does.",
   "fields": [
    {
     "name": "url",
     "label": "Server address",
     "type": "url",
     "required": true,
     "help": "The hospital system's address, for example http://127.0.0.1:7130."
    },
    {
     "name": "token",
     "label": "Token",
     "type": "secret",
     "required": true,
     "help": "The bearer token the hospital gave. It is never shown again."
    },
    {
     "name": "label",
     "label": "Name shown to doctors",
     "type": "text",
     "required": false,
     "help": "For example the hospital's name for its system."
    }
   ],
   "cannot": []
  },
  {
   "kind": "fhir_generic",
   "label": "Plain FHIR R4 server",
   "tested": false,
   "description": "Any FHIR R4 server that is not in NRCeS shapes: HAPI FHIR, Bahmni / OpenMRS (FHIR2), Epic or Oracle Cerner style.",
   "fields": [
    {
     "name": "url",
     "label": "Server address",
     "type": "url",
     "required": true,
     "help": "The server's address. Add the FHIR path here or in the next field."
    },
    {
     "name": "base_path",
     "label": "FHIR base path",
     "type": "text",
     "required": false,
     "help": "Only if the FHIR API is under a path, for example /openmrs/ws/fhir2/R4."
    },
    {
     "name": "identifier_systems",
     "label": "Identifier systems for UHID / MRN",
     "type": "text",
     "required": false,
     "help": "One per line or comma separated. Used when the server needs system|value to find a patient."
    },
    {
     "name": "auth",
     "label": "Sign-in",
     "type": "select",
     "required": true,
     "help": "How Vaidyx-TB signs in to the server.",
     "options": [
      {
       "value": "bearer",
       "label": "Bearer token"
      },
      {
       "value": "basic",
       "label": "User name and password (HTTP basic)"
      },
      {
       "value": "api_key",
       "label": "API key in a header"
      },
      {
       "value": "oauth2",
       "label": "OAuth2 client credentials"
      },
      {
       "value": "none",
       "label": "No sign-in"
      }
     ]
    },
    {
     "name": "token",
     "label": "Token",
     "type": "secret",
     "required": true,
     "help": "The bearer token. It is never shown again.",
     "when": {
      "auth": [
       "bearer"
      ]
     }
    },
    {
     "name": "username",
     "label": "User name",
     "type": "text",
     "required": true,
     "help": "",
     "when": {
      "auth": [
       "basic"
      ]
     }
    },
    {
     "name": "password",
     "label": "Password",
     "type": "secret",
     "required": true,
     "help": "Kept in an owner-only file on this server.",
     "when": {
      "auth": [
       "basic"
      ]
     }
    },
    {
     "name": "api_key_header",
     "label": "Header name",
     "type": "text",
     "required": false,
     "help": "The header that carries the key (default X-API-Key).",
     "when": {
      "auth": [
       "api_key"
      ]
     }
    },
    {
     "name": "api_key",
     "label": "API key",
     "type": "secret",
     "required": true,
     "help": "Kept in an owner-only file on this server.",
     "when": {
      "auth": [
       "api_key"
      ]
     }
    },
    {
     "name": "token_url",
     "label": "Token endpoint",
     "type": "url",
     "required": true,
     "help": "Where the access token is asked for.",
     "when": {
      "auth": [
       "oauth2"
      ]
     }
    },
    {
     "name": "client_id",
     "label": "Client id",
     "type": "text",
     "required": true,
     "help": "",
     "when": {
      "auth": [
       "oauth2"
      ]
     }
    },
    {
     "name": "client_secret",
     "label": "Client secret",
     "type": "secret",
     "required": true,
     "help": "Kept in an owner-only file on this server.",
     "when": {
      "auth": [
       "oauth2"
      ]
     }
    },
    {
     "name": "scope",
     "label": "Scope",
     "type": "text",
     "required": false,
     "help": "Only if the hospital asks for one, for example system/*.read.",
     "when": {
      "auth": [
       "oauth2"
      ]
     }
    },
    {
     "name": "label",
     "label": "Name shown to doctors",
     "type": "text",
     "required": false,
     "help": "For example the hospital's name for its system."
    }
   ],
   "cannot": [
    "no signature check (the signature stays unknown and is never counted as signed)",
    "no images (Bahmni / OpenMRS FHIR2 has no ImagingStudy)",
    "a report with no file is read as text only (its conclusion and values, line by line)",
    "no earlier versions of an amended report unless they were fetched before",
    "no sign-in with a signed JWT (SMART backend services)"
   ]
  },
  {
   "kind": "hl7v2_folder",
   "label": "HL7 v2 result messages in a folder",
   "tested": false,
   "description": "The hospital's lab, radiology or HIMS interface drops HL7 v2 result files (ORU^R01) into a folder on this server.",
   "fields": [
    {
     "name": "folder",
     "label": "Folder",
     "type": "folder",
     "required": true,
     "help": "A folder on this server, inside the allowed folder root. Vaidyx-TB only reads it."
    },
    {
     "name": "label",
     "label": "Name shown to doctors",
     "type": "text",
     "required": false,
     "help": "For example the hospital's name for its system."
    }
   ],
   "cannot": [
    "no signature check (HL7 v2 carries no signature that can be verified)",
    "no imaging links",
    "no referrals",
    "no link between duplicate registrations",
    "open orders only if order messages (ORM^O01) are dropped too",
    "no network listener (MLLP): files only"
   ]
  },
  {
   "kind": "folder_bridge",
   "label": "Report folder with an index file",
   "tested": false,
   "description": "For a hospital with no API: report PDFs in a folder with an index.csv that lists them.",
   "fields": [
    {
     "name": "folder",
     "label": "Folder",
     "type": "folder",
     "required": true,
     "help": "A folder on this server, inside the allowed folder root. Vaidyx-TB only reads it. It holds index.csv and the report files."
    },
    {
     "name": "label",
     "label": "Name shown to doctors",
     "type": "text",
     "required": false,
     "help": "For example the hospital's name for its system."
    }
   ],
   "cannot": [
    "no open orders",
    "no signature check (the report text decides)",
    "no imaging links",
    "no referrals",
    "no link between duplicate registrations",
    "no candidate values"
   ]
  },
  {
   "kind": "abdm_bundles",
   "label": "ABDM record bundles in a folder",
   "tested": false,
   "description": "ABDM health-record documents (FHIR document bundles) that the hospital, as an ABDM provider, hands over as files.",
   "fields": [
    {
     "name": "folder",
     "label": "Folder",
     "type": "folder",
     "required": true,
     "help": "A folder on this server, inside the allowed folder root. Vaidyx-TB only reads it. One .json bundle per record."
    },
    {
     "name": "label",
     "label": "Name shown to doctors",
     "type": "text",
     "required": false,
     "help": "For example the hospital's name for its system."
    }
   ],
   "cannot": [
    "no open orders",
    "no signature check (the bundle's signature is not verified)",
    "no imaging links",
    "no referrals",
    "no live ABDM gateway (consent requests)"
   ]
  },
  {
   "kind": "mcp",
   "label": "MCP connector",
   "tested": true,
   "description": "A configured MCP connector that lists a patient's records and serves their files.",
   "fields": [
    {
     "name": "connector",
     "label": "Connector",
     "type": "text",
     "required": true,
     "help": "The id of a configured MCP connector."
    },
    {
     "name": "label",
     "label": "Name shown to doctors",
     "type": "text",
     "required": false,
     "help": "For example the hospital's name for its system."
    }
   ],
   "cannot": [
    "no visits",
    "no open orders",
    "no report status",
    "no signature check",
    "no imaging links",
    "no referrals"
   ]
  },
  {
   "kind": "none",
   "label": "No hospital system",
   "tested": true,
   "description": "Case Files are made from uploaded files only.",
   "fields": [],
   "cannot": [
    "no lookup by UHID",
    "no re-fetch"
   ]
  }
 ],
 "presets": [
  {
   "id": "vaidyx_demo",
   "name": "Vaidyx demo hospital (SYNTHETIC)",
   "vendor": "Vaidyx",
   "sector": "national",
   "kind": "fhir",
   "defaults": {
    "url": "http://127.0.0.1:7130"
   },
   "status": "tested with the demo hospital",
   "interface": "documented",
   "notes": "The demo hospital on this server: FHIR R4 in ABDM / NRCeS shapes with a bearer token. Synthetic patients only."
  },
  {
   "id": "abdm_nrces_fhir",
   "name": "ABDM / NRCeS FHIR server (hospital that is an ABDM provider)",
   "vendor": "any",
   "sector": "national",
   "kind": "fhir",
   "defaults": {},
   "status": "by standard, not tested with the product",
   "interface": "documented",
   "notes": "Only for a hospital that keeps its own FHIR R4 store in NRCeS shapes (DocumentReference, DiagnosticReport, Provenance) that can be queried. ABDM compliant means the product pushes record bundles through the ABDM gateway after patient consent; it is not a FHIR server to query (RESEARCH.md section 2). For those products choose 'ABDM record bundles' (bundles handed over as files)."
  },
  {
   "id": "bahmni_openmrs",
   "name": "Bahmni / OpenMRS (FHIR2 module)",
   "vendor": "Bahmni Coalition / OpenMRS",
   "sector": "open source",
   "kind": "fhir_generic",
   "defaults": {
    "base_path": "/openmrs/ws/fhir2/R4",
    "auth": "basic",
    "identifier_systems": []
   },
   "status": "by standard, not tested with the product",
   "interface": "documented",
   "notes": "Plain FHIR R4 at /openmrs/ws/fhir2/R4 (capability at /metadata) with HTTP basic; ask for a read-only OpenMRS user (RESEARCH.md 3a). The FHIR2 module has no DocumentReference, Composition or ImagingStudy: a report is read from its DiagnosticReport (the file in presentedForm when present, else its values as a text-only report). No images, no signature."
  },
  {
   "id": "hapi_fhir",
   "name": "HAPI FHIR or any plain FHIR R4 server",
   "vendor": "any",
   "sector": "open source",
   "kind": "fhir_generic",
   "defaults": {
    "auth": "bearer",
    "identifier_systems": []
   },
   "status": "by standard, not tested with the product",
   "interface": "documented",
   "notes": "Any FHIR R4 server that is not in NRCeS shapes. Give the FHIR base address (for HAPI usually ending in /fhir), the sign-in the server uses, and the identifier system of the hospital number if the server needs system|value."
  },
  {
   "id": "international_fhir",
   "name": "International HIS with FHIR R4 (Epic / Oracle Health (Cerner) / TrakCare style)",
   "vendor": "Epic, Oracle Health, InterSystems",
   "sector": "international",
   "kind": "fhir_generic",
   "defaults": {
    "auth": "oauth2",
    "identifier_systems": []
   },
   "status": "by standard, not tested with the product",
   "interface": "by standard",
   "notes": "FHIR R4 with a bearer token or OAuth2 client credentials (client id and secret). Epic and Oracle Health normally ask for SMART backend services with a signed JWT (RESEARCH.md 1d and section 2), which Vaidyx-TB does not have yet: this preset works only where the site issues a client secret or a token. No Indian hospital on Epic was found; TrakCare and Cerner sites exist."
  },
  {
   "id": "nic_ehospital",
   "name": "NIC e-Hospital / NextGen eHospital",
   "vendor": "National Informatics Centre",
   "sector": "government",
   "kind": "folder_bridge",
   "defaults": {},
   "status": "by standard, not tested with the product",
   "interface": "no public API found",
   "notes": "No public API found; needs NIC cooperation; use HL7 v2 files or a report folder if the hospital can export (RESEARCH.md 1a). ABDM compliant means the product pushes record bundles through the ABDM gateway after patient consent; it is not a FHIR server to query (RESEARCH.md section 2). If NIC can hand over those bundles as files, choose 'ABDM record bundles'. Ask the vendor for FHIR R4 or HL7 v2 export."
  },
  {
   "id": "cdac_esushrut",
   "name": "C-DAC e-Sushrut (HMIS)",
   "vendor": "C-DAC",
   "sector": "government",
   "kind": "folder_bridge",
   "defaults": {},
   "status": "by standard, not tested with the product",
   "interface": "no public API found",
   "notes": "No public API found; needs C-DAC cooperation; use HL7 v2 files or a report folder if the hospital can export (RESEARCH.md 1a: C-DAC says HL7 is built in, with no interface document). ABDM compliant means the product pushes record bundles through the ABDM gateway after patient consent; it is not a FHIR server to query (RESEARCH.md section 2). If C-DAC can hand over those bundles as files, choose 'ABDM record bundles'. Ask the vendor for FHIR R4 or HL7 v2 export."
  },
  {
   "id": "insta_hms",
   "name": "Insta HMS (Practo)",
   "vendor": "Practo",
   "sector": "commercial",
   "kind": "hl7v2_folder",
   "defaults": {},
   "status": "by standard, not tested with the product",
   "interface": "vendor claim only",
   "notes": "The vendor names 'out-of-the-box HL7 and API based integrations', with no public document (RESEARCH.md 1c). Ask the vendor for FHIR R4 or HL7 v2 export (ORU^R01 result files with the report PDF); if neither is offered, choose 'Report folder with an index file'."
  },
  {
   "id": "karexpert",
   "name": "KareXpert",
   "vendor": "KareXpert",
   "sector": "commercial",
   "kind": "folder_bridge",
   "defaults": {},
   "status": "by standard, not tested with the product",
   "interface": "vendor claim only",
   "notes": "Only an ABDM connector is announced (a vendor claim); no FHIR, HL7 or API document was found (RESEARCH.md 1c). ABDM compliant means the product pushes record bundles through the ABDM gateway after patient consent; it is not a FHIR server to query (RESEARCH.md section 2). Start with a report folder; ask the vendor for FHIR R4 or HL7 v2 export, or for its ABDM record bundles as files."
  },
  {
   "id": "mocdoc",
   "name": "MocDoc",
   "vendor": "Yro Systems",
   "sector": "commercial",
   "kind": "folder_bridge",
   "defaults": {},
   "status": "by standard, not tested with the product",
   "interface": "vendor claim only",
   "notes": "The vendor says 'FHIR R4 compatible' and ABDM milestones 1 to 3 (vendor claims), with no API document found (RESEARCH.md 1c). ABDM compliant means the product pushes record bundles through the ABDM gateway after patient consent; it is not a FHIR server to query (RESEARCH.md section 2). Start with a report folder; ask the vendor for FHIR R4 or HL7 v2 export, or for its ABDM record bundles as files."
  },
  {
   "id": "napier",
   "name": "Napier Healthcare",
   "vendor": "Napier Healthcare",
   "sector": "commercial",
   "kind": "folder_bridge",
   "defaults": {},
   "status": "by standard, not tested with the product",
   "interface": "interface not known",
   "notes": "Interface not known: nothing was found about this product (RESEARCH.md 1c). Start with a report folder; ask the vendor for FHIR R4 or HL7 v2 export."
  },
  {
   "id": "akhil_miracle",
   "name": "Akhil Systems Miracle HIS",
   "vendor": "Akhil Systems",
   "sector": "commercial",
   "kind": "folder_bridge",
   "defaults": {},
   "status": "by standard, not tested with the product",
   "interface": "interface not known",
   "notes": "Interface not known: no primary source (RESEARCH.md 1c; a third-party list says ABDM yes, FHIR partial). Start with a report folder; ask the vendor for FHIR R4 or HL7 v2 export."
  },
  {
   "id": "generic_hl7v2",
   "name": "LIS / RIS with HL7 v2 results",
   "vendor": "any",
   "sector": "international",
   "kind": "hl7v2_folder",
   "defaults": {},
   "status": "by standard, not tested with the product",
   "interface": "by standard",
   "notes": "Any lab, radiology or hospital system that can send HL7 v2 results (ORU^R01, with the report PDF in an OBX of type ED where possible): what most commercial vendors name (Insta HMS, Attune LIS, Birlamedisoft; RESEARCH.md 1c and 3b). The hospital's interface engine or a small relay writes one file per message into the folder."
  },
  {
   "id": "generic_folder",
   "name": "Report folder with an index file",
   "vendor": "any",
   "sector": "national",
   "kind": "folder_bridge",
   "defaults": {},
   "status": "by standard, not tested with the product",
   "interface": "by standard",
   "notes": "For a hospital with no API: report PDFs in a folder with index.csv (uhid, patient_name, sex, dob or age, visit_no, visit_type, report_id, report_type, report_date, status, signed_by, file)."
  },
  {
   "id": "abdm_bundles",
   "name": "ABDM record bundles",
   "vendor": "any ABDM provider product",
   "sector": "national",
   "kind": "abdm_bundles",
   "defaults": {},
   "status": "by standard, not tested with the product",
   "interface": "by standard",
   "notes": "ABDM health-record documents (FHIR document bundles in NRCeS shapes, guide version 6.5.0) saved as .json files in a folder: how an ABDM compliant product (e-Hospital, e-Sushrut, Bahmni, MediXcel, Eka Care and others) can hand over the bundles it creates. No live ABDM gateway and no consent flow here (RESEARCH.md 3c)."
  }
 ],
 "current": {
  "kind": "fhir",
  "preset": "",
  "enabled": true,
  "settings": {
   "kind": "fhir",
   "label": "Vaidyx Demo Hospital HIS (SYNTHETIC)",
   "url": "http://127.0.0.1:7130",
   "enabled": true,
   "has_token": true,
   "pacs_url": "http://127.0.0.1:8042",
   "connector": ""
  }
 },
 "folder_roots": [
  "/data/vaidyx/tb_data/his_inbox"
 ],
 "remote_allowed": false
};

/** The mock's fingerprint: a plain hash of the values tried (the server's is an HMAC; the screen only carries it back). */
export function mockFingerprint(body: Record<string, unknown>): string {
  const plain = Object.fromEntries(Object.entries(body).filter(([k]) => k !== "identifier" && k !== "tested_fingerprint").sort(([a], [b]) => a.localeCompare(b)));
  let h = 0;
  for (const ch of JSON.stringify(plain)) h = (h * 31 + ch.charCodeAt(0)) | 0;
  return `fp1-mock-${(h >>> 0).toString(16)}`;
}

export interface HisMockLog {
  tries: Array<Record<string, unknown>>;
  saves: Array<Record<string, unknown>>;
  headers: Array<Record<string, string>>;
}

/** Answers the three routes of the chooser. A try fails when the address is on port 9 (nothing listens), the password is "wrong",
 *  or the folder ends in "/missing"; the UHID VXH/26/004201 is found, any other is not. Call after prepare() so these win. */
export async function routeHisChooser(page: Page, opts: { current?: Partial<typeof hisKindsData.current> } = {}): Promise<HisMockLog> {
  const log: HisMockLog = { tries: [], saves: [], headers: [] };
  const answer = (route: Route, body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  await page.route("**/api/tb/his/kinds", (route) => {
    log.headers.push(route.request().headers());
    return answer(route, { ...hisKindsData, current: { ...hisKindsData.current, ...(opts.current ?? {}) } });
  });
  await page.route("**/api/tb/his/try", async (route) => {
    const b = (route.request().postDataJSON() ?? {}) as Record<string, string>;
    log.tries.push(b);
    log.headers.push(route.request().headers());
    await new Promise((r) => setTimeout(r, 150));
    const down = /:9(\/|$)/.test(b.url ?? "");
    const refused = b.password === "wrong";
    const missing = (b.folder ?? "").endsWith("/missing");
    if (down || refused || missing) {
      return answer(route, {
        ok: false, checked_at: "2026-11-17T10:00:00+05:30", kind: b.kind ?? "fhir_generic", label: "", ping: { ok: false }, counts: null, fingerprint: "", latency_ms: 40,
        error: missing ? "The hospital-system folder does not exist on this server" : refused ? "The HIS refused the token (HTTP 401); check the HIS token in the settings" : "Cannot reach the HIS at http://127.0.0.1:9: ConnectError",
        hint: missing ? "Check that the folder exists on this server, inside the allowed folder root, and that Vaidyx-TB may read it." : refused ? "Check the sign-in details: the token, user name and password, API key or client id and secret the hospital gave." : "Check the server address and port, and that the hospital system is running and can be reached from this server.",
      });
    }
    const id = (b.identifier ?? "").trim();
    return answer(route, {
      ok: true, checked_at: "2026-11-17T10:00:00+05:30", kind: b.kind ?? "fhir_generic", label: b.label ?? "", preset: b.preset ?? "", error: "", hint: "",
      ping: { ok: true, name: "OpenMRS FHIR2 (SYNTHETIC)", fhir_version: "4.0.1", token_ok: true, latency_ms: 62 }, counts: { patients: 1240, reports: 9876 },
      fingerprint: mockFingerprint(b), latency_ms: 210,
      ...(id ? { sample: id === "VXH/26/004201"
        ? { found: true, identifier: id, visits: 3, reports: 8, newest_report_date: "2026-09-20" }
        : { found: false, identifier: id } } : {}),
    });
  });
  await page.route("**/api/tb/setup/his", (route) => {
    const b = (route.request().postDataJSON() ?? {}) as Record<string, string>;
    log.saves.push(b);
    if (b.tested_fingerprint && b.tested_fingerprint !== mockFingerprint(b)) return answer(route, { detail: { message: "Test these settings again before using them.", code: "untested" } }, 409);
    return answer(route, { ok: true, step: "his", test: { ok: true, hospital_name: "", patients: 1240, reports: 9876, latency_ms: 90, error: "" } });
  });
  return log;
}
