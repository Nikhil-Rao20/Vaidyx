"""One definition of the negation cues, shared by extraction, Q&A and adjudication (V1 item 1.1 and its review).

"non-" alone is not a negation (Non-small cell carcinoma, Non-Hodgkin, non-mucinous): only the result negations count.
"no special type" (breast carcinoma NST) is a diagnosis, not a negation."""
NO = r"no(?!\s+special\s+type\b)"
NON = r"non[- ]?(?:reactive|amplified|detected|detectable)"
