"""
openfda_tool.py — Real-time FDA drug label lookup via OpenFDA API.

Free, no API key required. Fetches authoritative drug information:
- Indications, contraindications, warnings, dosage, interactions
- Works for most FDA-approved drugs (primarily for US labels, but comprehensive for international drugs sold in India)
"""

import json
import logging
from typing import Any, Dict

import httpx

logger = logging.getLogger(__name__)

OPENFDA_BASE = "https://api.fda.gov/drug/label.json"
CDSCO_SEARCH_NOTE = "Note: OpenFDA covers FDA-approved labels. For India-specific CDSCO approved drugs and Indian brand equivalents, cross-reference CIMS India or the Indian Pharmacopoeia."


def _extract_field(label: dict, *field_names: str) -> str:
    """Extract first available field from a label dict, joining list values."""
    for field in field_names:
        val = label.get(field)
        if val:
            if isinstance(val, list):
                return " ".join(val)
            return str(val)
    return ""


def _format_label(label: dict, drug_name: str) -> str:
    """Format a drug label dict into a structured clinical summary."""
    sections = []

    # Drug identification
    brand = _extract_field(label, "openfda", "brand_name")
    if isinstance(label.get("openfda"), dict):
        brand = ", ".join(label["openfda"].get("brand_name", [drug_name]))
        generic = ", ".join(label["openfda"].get("generic_name", ["N/A"]))
        manufacturer = ", ".join(label["openfda"].get("manufacturer_name", ["N/A"]))
        route = ", ".join(label["openfda"].get("route", ["N/A"]))
    else:
        brand = drug_name
        generic = drug_name
        manufacturer = "N/A"
        route = "N/A"

    sections.append(f"**{brand}** ({generic})\nManufacturer: {manufacturer} | Route: {route}")

    # Clinical sections
    field_map = [
        ("INDICATIONS", "indications_and_usage", "indications_and_usage"),
        ("DOSAGE", "dosage_and_administration"),
        ("CONTRAINDICATIONS", "contraindications"),
        ("WARNINGS", "warnings_and_cautions", "warnings"),
        ("DRUG INTERACTIONS", "drug_interactions"),
        ("ADVERSE REACTIONS", "adverse_reactions"),
        ("USE IN SPECIFIC POPULATIONS", "use_in_specific_populations"),
        ("OVERDOSAGE", "overdosage"),
        ("HOW SUPPLIED", "how_supplied"),
    ]

    for section_title, *fields in field_map:
        content = _extract_field(label, *fields)
        if content:
            # Truncate long sections
            content = content[:800] + ("..." if len(content) > 800 else "")
            sections.append(f"\n**{section_title}**\n{content}")

    return "\n".join(sections)


class OpenFDADrugTool:
    """Look up FDA drug label information — free, no API key, real-time."""

    async def execute(self, content: str, ctx: dict) -> dict:
        import asyncio

        raw = content.strip()
        drug_name = raw
        search_type = "brand"

        # Support JSON input: {"drug": "metformin", "type": "generic"}
        if raw.startswith("{"):
            try:
                parsed = json.loads(raw)
                drug_name = parsed.get("drug", parsed.get("name", raw)).strip()
                search_type = parsed.get("type", "brand").lower()
            except json.JSONDecodeError:
                pass

        if not drug_name:
            return {"output": "Please provide a drug name to look up.", "error": True}

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, self._fetch_drug, drug_name, search_type)
        return result

    def _fetch_drug(self, drug_name: str, search_type: str = "brand") -> dict:
        """Fetch drug label from OpenFDA API."""
        # Try multiple search strategies
        search_queries = []

        if search_type == "generic":
            search_queries = [
                f'openfda.generic_name:"{drug_name}"',
                f'openfda.generic_name:"{drug_name.upper()}"',
                f'generic_name:"{drug_name}"',
            ]
        else:
            # Try brand first, then generic
            search_queries = [
                f'openfda.brand_name:"{drug_name}"',
                f'openfda.generic_name:"{drug_name}"',
                f'openfda.generic_name:"{drug_name.upper()}"',
                f'"{drug_name}"',
            ]

        label = None
        for query in search_queries:
            try:
                resp = httpx.get(
                    OPENFDA_BASE,
                    params={"search": query, "limit": 1},
                    timeout=10.0,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    results = data.get("results", [])
                    if results:
                        label = results[0]
                        break
            except Exception as e:
                logger.debug(f"OpenFDA query failed for {query!r}: {e}")
                continue

        if not label:
            # Fallback: broader text search
            try:
                resp = httpx.get(
                    OPENFDA_BASE,
                    params={"search": drug_name, "limit": 1},
                    timeout=10.0,
                )
                if resp.status_code == 200:
                    results = resp.json().get("results", [])
                    if results:
                        label = results[0]
            except Exception:
                pass

        if not label:
            return {
                "output": (
                    f"No FDA label found for '{drug_name}'. "
                    f"This drug may not be FDA-approved or may be under a different name. "
                    f"For Indian-only drugs (e.g., Ayurvedic, Unani, or CDSCO-only approvals), "
                    f"consult CIMS India or the Indian Pharmacopoeia directly.\n\n"
                    f"{CDSCO_SEARCH_NOTE}"
                ),
                "error": False,
            }

        formatted = _format_label(label, drug_name)
        output = (
            f"## FDA Drug Label — {drug_name.upper()}\n\n"
            f"{formatted}\n\n"
            f"---\n*Source: OpenFDA (fda.gov). {CDSCO_SEARCH_NOTE}*"
        )

        return {"output": output, "error": False}
