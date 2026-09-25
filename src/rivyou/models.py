"""Pydantic models shared across crawling, verification, and output."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Confidence(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class StoreCandidate(BaseModel):
    original_url: str
    normalized_domain: str


class VerificationEvidence(BaseModel):
    signal: str
    weight: int
    source_url: str
    value: str | None = None


class ShopifyVerificationResult(BaseModel):
    is_shopify: bool
    score: int
    confidence: Confidence
    evidence: list[VerificationEvidence] = Field(default_factory=list)


class IndiaVerificationResult(BaseModel):
    is_indian: bool
    score: int
    confidence: Confidence
    evidence: list[VerificationEvidence] = Field(default_factory=list)
    detected_state: str | None = None
    detected_city: str | None = None
    detected_pincodes: list[str] = Field(default_factory=list)


def empty_socials() -> dict[str, str | None]:
    return {key: None for key in ("instagram", "facebook", "twitter", "linkedin", "youtube")}


class StoreRecord(BaseModel):
    domain_url: str
    emails: list[str] = Field(default_factory=list)
    phones: list[str] = Field(default_factory=list)
    socials: dict[str, str | None] = Field(default_factory=empty_socials)
    category: str | None = None
    tagline_or_description: str | None = None
    logo_url: str | None = None
    state: str | None = None

    shopify_score: int = 0
    india_score: int = 0
    shopify_confidence: Confidence = Confidence.LOW
    india_confidence: Confidence = Confidence.LOW
    shopify_evidence: list[VerificationEvidence] = Field(default_factory=list)
    india_evidence: list[VerificationEvidence] = Field(default_factory=list)
    crawled_pages: list[str] = Field(default_factory=list)
    redirect_history: list[str] = Field(default_factory=list)
    extraction_errors: list[str] = Field(default_factory=list)

