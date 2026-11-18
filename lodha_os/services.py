"""Service list. Names are the same as the Proposal Maker service library (repo nkl-proposal-stream,
src/data/services.ts) so an executed proposal maps to service lines without a lookup by hand."""

LINES = ("Financials", "ROC", "GST", "Income tax", "TDS", "Other levies", "Other")

SERVICES = {
    "Accounting & MIS": "Financials",
    "Statutory Audit": "Financials",
    "MCA Annual Compliance": "ROC",
    "Company Incorporation": "ROC",
    "LLP Incorporation": "ROC",
    "GST Monthly Compliance": "GST",
    "GST Registration": "GST",
    "GST Refund": "GST",
    "GST Notice": "GST",
    "Corporate Income Tax Return": "Income tax",
    "Individual Income Tax Return": "Income tax",
    "Tax Audit": "Income tax",
    "TDS Compliance": "TDS",
    "Payroll": "Other levies",
    "Virtual CFO": "Other",
    "Debtor Recovery": "Other",
}


def by_line():
    out = {l: [] for l in LINES}
    for s, l in SERVICES.items():
        out[l].append(s)
    return out


def lines_of(services):
    return [l for l in LINES if any(SERVICES.get(s) == l for s in services or [])]
