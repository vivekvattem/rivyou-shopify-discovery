"""Multi-signal verification that a merchant is situated in India."""

from __future__ import annotations

import re
from collections.abc import Iterable
from urllib.parse import urlsplit

from rivyou.config import INDIA_SCORE_THRESHOLD
from rivyou.crawler import CrawledPage
from rivyou.extract.location import extract_location
from rivyou.models import Confidence, IndiaVerificationResult, VerificationEvidence
from rivyou.utils.text import visible_text

PIN_RE = re.compile(r"\b[1-9][0-9]{5}\b")
GSTIN_RE = re.compile(r"\b[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b", re.I)
INDIA_RE = re.compile(r"\b(?:India|Bharat)\b", re.I)
PHONE_91_RE = re.compile(r"(?<!\d)(?:\+91|0091)[\s().-]*[6-9](?:[\s().-]*\d){9}(?!\d)")
INR_RE = re.compile(r"(?:₹|\bINR\b|Rs\.?)\s*\d", re.I)
ADDRESS_WORD_RE = re.compile(r"\b(?:address|registered office|corporate office|store|road|street|lane|building|floor)\b", re.I)
SHIPPING_INDIA_RE = re.compile(r"(?:ship|deliver)(?:ping|y)?[^.]{0,80}\b(?:across|within|all over)?\s*India\b", re.I)


def _context(text: str, start: int, end: int, radius: int = 180) -> str:
    return text[max(0, start - radius): min(len(text), end + radius)]


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
        location = extract_location(text)
        detected_state = detected_state or location.state
        detected_city = detected_city or location.city
        gstin_match = GSTIN_RE.search(text)
        if gstin_match:
            add("gstin", 3, page, gstin_match.group(0).upper())
        phone_match = PHONE_91_RE.search(text)
        if phone_match:
            add("india_phone", 2, page, phone_match.group(0))
        india_match = INDIA_RE.search(text)
        if india_match and ADDRESS_WORD_RE.search(_context(text, india_match.start(), india_match.end())):
            add("explicit_india_address", 3, page, india_match.group(0))
        pin_match = PIN_RE.search(text)
        pin_context = _context(text, pin_match.start(), pin_match.end()) if pin_match else ""
        if pin_match and ADDRESS_WORD_RE.search(pin_context):
            add("india_pincode", 2, page, pin_match.group(0))
        if detected_state:
            add("india_state_or_city", 1, page, detected_city or detected_state)
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
