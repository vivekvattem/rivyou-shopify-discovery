"""Multi-signal verification that a merchant is situated in India."""

from __future__ import annotations

import re
from collections.abc import Iterable
from urllib.parse import urlsplit

from rivyou.config import INDIA_SCORE_THRESHOLD
from rivyou.crawler import CrawledPage
from rivyou.extract.location import extract_location
from rivyou.models import Confidence, IndiaVerificationResult, VerificationEvidence
from rivyou.utils.text import iter_json_ld, visible_text

PIN_RE = re.compile(r"\b[1-9][0-9]{5}\b")
GSTIN_RE = re.compile(r"\b[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b", re.I)
INDIA_RE = re.compile(r"\b(?:India|Bharat)\b", re.I)
PHONE_91_RE = re.compile(r"(?<!\d)(?:\+91|0091)[\s().-]*[6-9](?:[\s().-]*\d){9}(?!\d)")
INR_RE = re.compile(r"(?:₹|\bINR\b|Rs\.?)\s*\d", re.I)
ADDRESS_WORD_RE = re.compile(r"\b(?:address|registered office|corporate office|store|road|street|lane|building|floor)\b", re.I)
SHIPPING_INDIA_RE = re.compile(r"(?:ship|deliver)(?:ping|y)?[^.]{0,80}\b(?:across|within|all over)?\s*India\b", re.I)


def _context(text: str, start: int, end: int, radius: int = 180) -> str:
    return text[max(0, start - radius): min(len(text), end + radius)]


def _structured_address_text(html: str) -> str:
    values: list[str] = []

    def visit(value: object) -> None:
        if isinstance(value, dict):
            if any(key in value for key in ("addressRegion", "addressLocality", "postalCode", "streetAddress")):
                for key in ("streetAddress", "addressLocality", "addressRegion", "postalCode", "addressCountry"):
                    item = value.get(key)
                    if isinstance(item, str):
                        values.append(item)
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    for item in iter_json_ld(html):
        visit(item)
    return " ".join(values)


def _confidence(score: int, threshold: int) -> Confidence:
    if score >= max(8, threshold + 4):
        return Confidence.HIGH
    if score >= threshold:
        return Confidence.MEDIUM
    return Confidence.LOW


def verify_india(
    pages: Iterable[CrawledPage], threshold: int = INDIA_SCORE_THRESHOLD
) -> IndiaVerificationResult:
    evidence: list[VerificationEvidence] = []
    found: set[str] = set()
    pincodes: set[str] = set()
    detected_state: str | None = None
    detected_city: str | None = None

    def add(signal: str, weight: int, page: CrawledPage, value: str | None = None) -> None:
        if signal not in found:
            found.add(signal)
            evidence.append(VerificationEvidence(signal=signal, weight=weight, source_url=page.final_url, value=value))

    for page in pages:
        if not page.html:
            continue
        text = visible_text(page.html)
        pincodes.update(PIN_RE.findall(text))
        structured_text = _structured_address_text(page.html)
        structured_location = extract_location(structured_text)
        gstin_match = GSTIN_RE.search(text)
        if gstin_match:
            add("gstin", 3, page, gstin_match.group(0).upper())
        phone_match = PHONE_91_RE.search(text)
        if phone_match:
            add("india_phone", 2, page, phone_match.group(0))
        india_match = next((
            match for match in INDIA_RE.finditer(text)
            if ADDRESS_WORD_RE.search(_context(text, match.start(), match.end()))
        ), None)
        if india_match:
            add("explicit_india_address", 3, page, india_match.group(0))
        pin_matches = list(PIN_RE.finditer(text))
        pin_match = next((
            match for match in pin_matches
            if ADDRESS_WORD_RE.search(_context(text, match.start(), match.end()))
            and extract_location(_context(text, match.start(), match.end())).state
        ), pin_matches[0] if pin_matches else None)
        pin_context = _context(text, pin_match.start(), pin_match.end()) if pin_match else ""
        address_match = ADDRESS_WORD_RE.search(text)
        address_context = _context(text, address_match.start(), address_match.end()) if address_match else ""
        contextual_location = structured_location
        if not contextual_location.state:
            contextual_location = extract_location(pin_context or address_context)
        detected_state = detected_state or contextual_location.state
        detected_city = detected_city or contextual_location.city
        if pin_match and ADDRESS_WORD_RE.search(pin_context) and extract_location(pin_context).state:
            add("india_pincode", 2, page, pin_match.group(0))
        supporting_location = contextual_location if contextual_location.state else extract_location(text)
        if supporting_location.state:
            add("india_state_or_city", 1, page, supporting_location.city or supporting_location.state)
        if INR_RE.search(text):
            add("inr_pricing", 1, page, INR_RE.search(text).group(0))
        if SHIPPING_INDIA_RE.search(text):
            add("india_shipping", 1, page, SHIPPING_INDIA_RE.search(text).group(0)[:150])
        if urlsplit(page.final_url).hostname and urlsplit(page.final_url).hostname.lower().endswith(".in"):
            add("dot_in_domain", 1, page, urlsplit(page.final_url).hostname)
        # A postal-looking line with a state/city and PIN is strong physical-location evidence.
        local_location = extract_location(pin_context) if pin_context else None
        if local_location and local_location.state and pin_match and ADDRESS_WORD_RE.search(pin_context):
            add("clear_indian_physical_address", 4, page, f"{detected_city or detected_state} {pin_match.group(0)}")
    score = sum(item.weight for item in evidence)
    return IndiaVerificationResult(
        is_indian=score >= threshold,
        score=score,
        confidence=_confidence(score, threshold),
        evidence=evidence,
        detected_state=detected_state,
        detected_city=detected_city,
        detected_pincodes=sorted(pincodes),
    )
