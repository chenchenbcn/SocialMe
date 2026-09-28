"""ISO-3166 alpha-2 code -> country name, for APIs that return codes."""

COUNTRY_NAMES = {
    "AD": "Andorra", "AE": "United Arab Emirates", "AR": "Argentina", "AT": "Austria",
    "AU": "Australia", "BD": "Bangladesh", "BE": "Belgium", "BO": "Bolivia", "BR": "Brazil",
    "CA": "Canada", "CH": "Switzerland", "CL": "Chile", "CN": "China", "CO": "Colombia",
    "CR": "Costa Rica", "CU": "Cuba", "CZ": "Czechia", "DE": "Germany", "DK": "Denmark",
    "DO": "Dominican Republic", "DZ": "Algeria", "EC": "Ecuador", "EG": "Egypt", "ES": "Spain",
    "FI": "Finland", "FR": "France", "GB": "United Kingdom", "GR": "Greece", "GT": "Guatemala",
    "HK": "Hong Kong", "HN": "Honduras", "HU": "Hungary", "ID": "Indonesia", "IE": "Ireland",
    "IL": "Israel", "IN": "India", "IT": "Italy", "JP": "Japan", "KR": "South Korea",
    "MA": "Morocco", "MX": "Mexico", "MY": "Malaysia", "NG": "Nigeria", "NI": "Nicaragua",
    "NL": "Netherlands", "NO": "Norway", "NZ": "New Zealand", "PA": "Panama", "PE": "Peru",
    "PH": "Philippines", "PK": "Pakistan", "PL": "Poland", "PR": "Puerto Rico", "PT": "Portugal",
    "PY": "Paraguay", "RO": "Romania", "RU": "Russia", "SA": "Saudi Arabia", "SE": "Sweden",
    "SG": "Singapore", "SV": "El Salvador", "TH": "Thailand", "TR": "Turkey", "TW": "Taiwan",
    "UA": "Ukraine", "US": "United States", "UY": "Uruguay", "VE": "Venezuela", "VN": "Vietnam",
    "ZA": "South Africa",
}


def country_name(code_or_name: str) -> str:
    key = (code_or_name or "").strip()
    return COUNTRY_NAMES.get(key.upper(), key) if len(key) == 2 else key
