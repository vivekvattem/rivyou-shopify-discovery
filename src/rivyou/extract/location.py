"""Conservative Indian city/state extraction."""

from __future__ import annotations

import re
from dataclasses import dataclass

from rivyou.utils.text import clean_text


INDIAN_STATES_AND_UTS = (
    "Andaman and Nicobar Islands", "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar",
    "Chandigarh", "Chhattisgarh", "Dadra and Nagar Haveli and Daman and Diu", "Delhi", "Goa",
    "Gujarat", "Haryana", "Himachal Pradesh", "Jammu and Kashmir", "Jharkhand", "Karnataka",
    "Kerala", "Ladakh", "Lakshadweep", "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya",
    "Mizoram", "Nagaland", "Odisha", "Puducherry", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu",
    "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal",
)

CITY_TO_STATE = {
    "bengaluru": "Karnataka", "bangalore": "Karnataka", "mysuru": "Karnataka", "mysore": "Karnataka",
    "mumbai": "Maharashtra", "pune": "Maharashtra", "nagpur": "Maharashtra", "nashik": "Maharashtra",
    "hyderabad": "Telangana", "chennai": "Tamil Nadu", "coimbatore": "Tamil Nadu",
    "new delhi": "Delhi", "delhi": "Delhi", "kolkata": "West Bengal", "ahmedabad": "Gujarat",
    "surat": "Gujarat", "vadodara": "Gujarat", "jaipur": "Rajasthan", "jodhpur": "Rajasthan",
    "kochi": "Kerala", "cochin": "Kerala", "ernakulam": "Kerala", "thiruvananthapuram": "Kerala",
    "lucknow": "Uttar Pradesh", "noida": "Uttar Pradesh", "gurugram": "Haryana", "gurgaon": "Haryana",
    "chandigarh": "Chandigarh", "bhubaneswar": "Odisha", "indore": "Madhya Pradesh",
    "bhopal": "Madhya Pradesh", "patna": "Bihar", "guwahati": "Assam", "panaji": "Goa",
}

STATE_ABBREVIATIONS = {
    "NCT": "Delhi", "MH": "Maharashtra", "KA": "Karnataka", "GJ": "Gujarat", "RJ": "Rajasthan",
    "TN": "Tamil Nadu", "TS": "Telangana", "WB": "West Bengal", "KL": "Kerala", "UP": "Uttar Pradesh",
}


@dataclass(frozen=True, slots=True)
class LocationMatch:
    state: str | None
    city: str | None


def extract_location(text: str) -> LocationMatch:
    value = clean_text(text)
    for state in sorted(INDIAN_STATES_AND_UTS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(state)}\b", value, re.I):
            city = next((city.title() for city, mapped in CITY_TO_STATE.items()
                         if mapped == state and re.search(rf"\b{re.escape(city)}\b", value, re.I)), None)
            return LocationMatch(state, city)
    for city in sorted(CITY_TO_STATE, key=len, reverse=True):
        if re.search(rf"\b{re.escape(city)}\b", value, re.I):
            return LocationMatch(CITY_TO_STATE[city], city.title())
    for abbreviation, state in STATE_ABBREVIATIONS.items():
        if re.search(rf"(?:,|\s)\s*{abbreviation}\s*(?:-|,|\b\d{{6}}\b)", value):
            return LocationMatch(state, None)
    return LocationMatch(None, None)

