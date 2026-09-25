"""Email and telephone extraction with conservative normalization."""

from __future__ import annotations

import re
from collections.abc import Iterable

import phonenumbers
from bs4 import BeautifulSoup

from rivyou.crawler import CrawledPage
from rivyou.utils.text import iter_json_ld, visible_text

EMAIL_RE = re.compile(r"(?<![\w.+-])([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})(?![\w.-])", re.I)
JUNK_EMAIL_LOCAL = re.compile(r"^(?:example|test|testing|sample|email|yourname|name|user)$", re.I)
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")
JUNK_EMAIL_DOMAINS = {"example.com", "example.org", "test.com", "yourbrand.com", "shopify.com", "myshopify.com"}
JUNK_PHONE_NUMBERS = {"+911234567890", "+919876543210", "+910000000000", "+919999999999"}


def normalize_email(value: str) -> str | None:
    email = value.strip().strip(".,;:!?()[]{}<>\"'").lower()
    if not EMAIL_RE.fullmatch(email):
        return None
    local, domain = email.rsplit("@", 1)
    if JUNK_EMAIL_LOCAL.match(local) or local in {"noreply", "no-reply", "donotreply", "do-not-reply"}:
        return None
    if domain in JUNK_EMAIL_DOMAINS or domain.endswith(".myshopify.com"):
        return None
    if email.endswith(IMAGE_EXTENSIONS) or ".." in email:
        return None
    return email


def _json_values(value: object) -> list[str]:
    result: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key.lower() in {"email", "telephone", "phone"} and isinstance(item, (str, int)):
                result.append(str(item))
            result.extend(_json_values(item))
    elif isinstance(value, list):
        for item in value:
            result.extend(_json_values(item))
    return result


def _normalize_phone(value: str) -> str | None:
    candidate = re.sub(r"(?i)(?:tel|phone|mobile|whatsapp)\s*[:.-]?", "", value).strip()
    try:
        number = phonenumbers.parse(candidate, "IN")
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_possible_number(number) or not phonenumbers.is_valid_number(number):
        return None
    normalized = phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)
    return None if normalized in JUNK_PHONE_NUMBERS else normalized


def extract_contacts(pages: Iterable[CrawledPage]) -> tuple[list[str], list[str]]:
    email_values: set[str] = set()
    phone_values: set[str] = set()
    for page in pages:
        if not page.html:
            continue
        soup = BeautifulSoup(page.html, "lxml")
        text = visible_text(page.html)
        sources = [text]
        sources.extend(tag.get("href", "")[7:] for tag in soup.select('a[href^="mailto:"]'))
        tel_sources = [tag.get("href", "")[4:] for tag in soup.select('a[href^="tel:"]')]
        for item in iter_json_ld(page.html):
            values = _json_values(item)
            sources.extend(value for value in values if "@" in value)
            tel_sources.extend(value for value in values if "@" not in value)
        for source in sources:
            for match in EMAIL_RE.finditer(source):
                if normalized := normalize_email(match.group(1)):
                    email_values.add(normalized)
        for raw in tel_sources:
            if normalized := _normalize_phone(raw):
                phone_values.add(normalized)
        for match in phonenumbers.PhoneNumberMatcher(text, "IN"):
            if phonenumbers.is_valid_number(match.number):
                normalized = phonenumbers.format_number(match.number, phonenumbers.PhoneNumberFormat.E164)
                if normalized not in JUNK_PHONE_NUMBERS:
                    phone_values.add(normalized)
    return sorted(email_values), sorted(phone_values)
