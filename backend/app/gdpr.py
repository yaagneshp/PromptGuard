"""Maps a detected PII category to the UK GDPR articles it's most relevant
to, for the compliance-tagging feature.

This is an illustrative mapping for the tool's audit/reporting output, not
legal advice — a real deployment would want a data-protection professional
to review and own this table.
"""

# category -> [(article, short rationale)]
CATEGORY_GDPR_MAP: dict[str, list[tuple[str, str]]] = {
    "email": [("Art. 4(1)", "Email address is personal data under the GDPR's definition of an identifier")],
    "uk_phone": [("Art. 4(1)", "Phone number is a personal identifier")],
    "ni_number": [
        ("Art. 4(1)", "National Insurance number is a personal identifier"),
        ("Art. 5(1)(f)", "High-sensitivity identifier requiring confidentiality safeguards"),
    ],
    "credit_card": [
        ("Art. 4(1)", "Financial account data is personal data"),
        ("Art. 32", "Requires appropriate technical security measures"),
    ],
    "aws_key": [("Art. 32", "Credential leakage is a security-of-processing risk")],
    "ip_address": [("Art. 4(1)", "IP addresses are cited as online identifiers in Recital 30")],
    "token_url": [("Art. 32", "Bearer-token URLs risk unauthorised access to personal data")],
    "person": [("Art. 4(1)", "Named individual is personal data")],
    "location": [("Art. 4(1)", "Location data can identify a person, especially combined with other identifiers")],
    "nrp": [("Art. 9", "Nationality/religious/political affiliation is a special category of data")],
    "medical_license": [("Art. 9", "Health-related professional data is a special category")],
    "uk_nhs": [
        ("Art. 9", "NHS number is closely tied to health data, a special category"),
        ("Art. 4(1)", "Also a direct personal identifier"),
    ],
    "us_ssn": [("Art. 4(1)", "Foreign national identifier; still personal data if it identifies a data subject")],
    "iban_code": [
        ("Art. 4(1)", "Bank account identifier is personal data"),
        ("Art. 32", "Requires security safeguards"),
    ],
    "crypto": [("Art. 32", "Wallet addresses risk financial account exposure")],
}


def tags_for_categories(categories: set[str]) -> list[tuple[str, str, str]]:
    """Returns (category, article, rationale) tuples for every category that
    has a mapping, deduplicated by (category, article)."""
    seen: set[tuple[str, str]] = set()
    tags: list[tuple[str, str, str]] = []
    for category in categories:
        for article, rationale in CATEGORY_GDPR_MAP.get(category, []):
            key = (category, article)
            if key not in seen:
                seen.add(key)
                tags.append((category, article, rationale))
    return tags
