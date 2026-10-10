"""Document dates (V1 item 3.1).

One place that answers "what date does this document carry?" for the gate, search, agents, Q&A, the timeline and the
UI. Two dates per document, both read from the text with their labels (the finder lives below `doc_dates`):

  report date   when the report was signed out (reported on, authorised, verified, signed, date of report, the date on the
                signature line): which version of a report is the newest
  event date    when the clinical event happened (study / scan date, sample collected, procedure, visit, discharge,
                date of completion): the clinical order, "after treatment" checks, the timeline

If only one of the two was found, it stands in for the other and is marked assumed. A document with neither is marked
unconfirmed: the gate asks a clinician to confirm the date (confirm_dates) wherever the date matters, and never guesses
from the DOB, a next-review date or the filename (the filename date is only a suggestion for the dialog).
"""


def doc_dates(doc) -> dict:
    """The dates of a document as every consumer should see them (the clinician's confirmation, overlaid by
    rules.case_docs(), is already in the classification when it exists).

    report / event: ISO date or "" · report_assumed / event_assumed: the other date stands in · unconfirmed: no date was
    found in the text (nothing stands in) · flags: sanity flags from the finder · sort: key for ordering by (event, report)."""
    c = doc.get("classification") or {}
    report = c.get("report_date_iso") or ""
    event = c.get("event_date_iso") or ""
    return {"report": report or event, "event": event or report,
            "report_assumed": bool(c.get("report_date_assumed")) or (not report and bool(event)),
            "event_assumed": bool(c.get("event_date_assumed")) or (not event and bool(report)),
            "unconfirmed": bool(c.get("date_unconfirmed")) or not (report or event),
            "flags": list(c.get("date_flags") or []),
            "sort": (event or report, report or event)}
