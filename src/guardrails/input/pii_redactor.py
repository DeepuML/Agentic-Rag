"""
src/guardrails/input/pii_redactor.py
─────────────────────────────────────
PII detection and redaction using Microsoft Presidio.
Integrates presidio-analyzer for detection and presidio-anonymizer for redaction.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from src.core.config import get_settings
from src.core.exceptions import PIIDetectedError
from src.utils.logger import get_logger
from src.utils.metrics import GUARDRAIL_TRIGGERS, PII_REDACTIONS

logger = get_logger(__name__)


@dataclass
class PIIResult:
    """Result of a PII scan."""
    original_text: str
    redacted_text: str
    entities_found: list[dict[str, Any]] = field(default_factory=list)
    has_pii: bool = False
    max_score: float = 0.0


# ── Presidio Singleton Initialization ─────────────────────────────────────────

@lru_cache(maxsize=1)
def _get_analyzer():
    """Lazy-initialize and cache the Presidio AnalyzerEngine."""
    try:
        from presidio_analyzer import AnalyzerEngine
        from presidio_analyzer.nlp_engine import NlpEngineProvider

        # Use spaCy en_core_web_lg as the NLP engine
        provider = NlpEngineProvider(
            nlp_configuration={
                "nlp_engine_name": "spacy",
                "models": [{"lang_code": "en", "model_name": "en_core_web_lg"}],
            }
        )
        engine = AnalyzerEngine(nlp_engine=provider.create_engine())
        logger.info("Presidio AnalyzerEngine initialized")
        return engine
    except Exception as e:
        logger.warning(
            "Presidio AnalyzerEngine failed to initialize, using simple fallback",
            extra={"error": str(e)},
        )
        return None


@lru_cache(maxsize=1)
def _get_anonymizer():
    """Lazy-initialize and cache the Presidio AnonymizerEngine."""
    try:
        from presidio_anonymizer import AnonymizerEngine
        engine = AnonymizerEngine()
        logger.info("Presidio AnonymizerEngine initialized")
        return engine
    except Exception as e:
        logger.warning("Presidio AnonymizerEngine failed to initialize", extra={"error": str(e)})
        return None


# ── Fallback Regex Redactor ───────────────────────────────────────────────────

import re

_FALLBACK_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("EMAIL_ADDRESS", re.compile(r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b")),
    ("PHONE_NUMBER", re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")),
    ("US_SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("CREDIT_CARD", re.compile(r"\b(?:\d{4}[- ]){3}\d{4}\b")),
    ("IP_ADDRESS", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
]


def _fallback_redact(text: str, replacement: str = "[REDACTED]") -> PIIResult:
    """Simple regex-based PII redaction when Presidio is unavailable."""
    redacted = text
    entities_found: list[dict] = []
    for entity_type, pattern in _FALLBACK_PATTERNS:
        matches = pattern.findall(text)
        if matches:
            for match in matches:
                entities_found.append({
                    "entity_type": entity_type,
                    "text": match,
                    "score": 0.9,
                })
                redacted = redacted.replace(match, replacement)

    return PIIResult(
        original_text=text,
        redacted_text=redacted,
        entities_found=entities_found,
        has_pii=bool(entities_found),
        max_score=max((e["score"] for e in entities_found), default=0.0),
    )


# ── Public API ────────────────────────────────────────────────────────────────

class PIIRedactor:
    """
    Detects and redacts PII from text using Microsoft Presidio.
    Falls back to regex patterns if Presidio is unavailable.

    Supported entity types:
        PERSON, EMAIL_ADDRESS, PHONE_NUMBER, CREDIT_CARD, US_SSN,
        US_BANK_NUMBER, IP_ADDRESS, URL, LOCATION, DATE_TIME
    """

    DEFAULT_ENTITIES = [
        "PERSON",
        "EMAIL_ADDRESS",
        "PHONE_NUMBER",
        "CREDIT_CARD",
        "US_SSN",
        "US_BANK_NUMBER",
        "IP_ADDRESS",
        "URL",
        "LOCATION",
    ]

    def __init__(
        self,
        entities: list[str] | None = None,
        threshold: float | None = None,
        replacement_token: str = "[REDACTED]",
    ) -> None:
        settings = get_settings()
        self.entities = entities or self.DEFAULT_ENTITIES
        self.threshold = threshold or settings.pii_threshold
        self.replacement_token = replacement_token

    def analyze(self, text: str) -> PIIResult:
        """
        Analyze text for PII. Returns a PIIResult with detected entities.
        Does NOT modify the text.
        """
        analyzer = _get_analyzer()

        if analyzer is None:
            return _fallback_redact(text, self.replacement_token)

        try:
            from presidio_analyzer import RecognizerResult

            results: list[RecognizerResult] = analyzer.analyze(
                text=text,
                entities=self.entities,
                language="en",
                score_threshold=self.threshold,
            )

            entities_found = [
                {
                    "entity_type": r.entity_type,
                    "start": r.start,
                    "end": r.end,
                    "score": r.score,
                    "text": text[r.start:r.end],
                }
                for r in results
            ]

            return PIIResult(
                original_text=text,
                redacted_text=text,  # Not yet redacted; call redact() for that
                entities_found=entities_found,
                has_pii=bool(entities_found),
                max_score=max((e["score"] for e in entities_found), default=0.0),
            )

        except Exception as e:
            logger.warning("Presidio analysis failed, using fallback", extra={"error": str(e)})
            return _fallback_redact(text, self.replacement_token)

    def redact(self, text: str, location: str = "input") -> PIIResult:
        """
        Analyze and redact PII from the given text.

        Args:
            text: Input text to redact.
            location: 'input' or 'output' (for metrics labeling).

        Returns:
            PIIResult with redacted_text populated.
        """
        analyzer = _get_analyzer()
        anonymizer = _get_anonymizer()

        if analyzer is None or anonymizer is None:
            result = _fallback_redact(text, self.replacement_token)
            if result.has_pii:
                for entity in result.entities_found:
                    PII_REDACTIONS.labels(
                        entity_type=entity["entity_type"], location=location
                    ).inc()
                GUARDRAIL_TRIGGERS.labels(
                    guardrail_type="pii_redaction", direction=location
                ).inc()
            return result

        try:
            from presidio_analyzer import RecognizerResult
            from presidio_anonymizer.entities import OperatorConfig

            analyzer_results: list[RecognizerResult] = analyzer.analyze(
                text=text,
                entities=self.entities,
                language="en",
                score_threshold=self.threshold,
            )

            if not analyzer_results:
                return PIIResult(
                    original_text=text,
                    redacted_text=text,
                    entities_found=[],
                    has_pii=False,
                    max_score=0.0,
                )

            # Redact each detected entity with replacement token
            operators = {
                entity_type: OperatorConfig("replace", {"new_value": self.replacement_token})
                for entity_type in self.entities
            }

            anonymized = anonymizer.anonymize(
                text=text,
                analyzer_results=analyzer_results,
                operators=operators,
            )

            entities_found = [
                {
                    "entity_type": r.entity_type,
                    "start": r.start,
                    "end": r.end,
                    "score": r.score,
                    "text": text[r.start:r.end],
                }
                for r in analyzer_results
            ]

            # Record metrics
            for entity in entities_found:
                PII_REDACTIONS.labels(
                    entity_type=entity["entity_type"], location=location
                ).inc()
            GUARDRAIL_TRIGGERS.labels(
                guardrail_type="pii_redaction", direction=location
            ).inc()

            logger.info(
                "PII redacted",
                extra={
                    "location": location,
                    "entity_count": len(entities_found),
                    "entity_types": [e["entity_type"] for e in entities_found],
                },
            )

            return PIIResult(
                original_text=text,
                redacted_text=anonymized.text,
                entities_found=entities_found,
                has_pii=True,
                max_score=max(r.score for r in analyzer_results),
            )

        except Exception as e:
            logger.warning("Presidio redaction failed, using fallback", extra={"error": str(e)})
            return _fallback_redact(text, self.replacement_token)

    def check_output(self, text: str, raise_on_detect: bool = False) -> PIIResult:
        """
        Check generated output for PII leakage.
        Optionally raises PIIDetectedError if PII is found.
        """
        result = self.analyze(text)
        if result.has_pii:
            GUARDRAIL_TRIGGERS.labels(guardrail_type="pii_leak", direction="output").inc()
            logger.warning(
                "PII detected in output",
                extra={"entity_types": [e["entity_type"] for e in result.entities_found]},
            )
            if raise_on_detect:
                raise PIIDetectedError(entities=result.entities_found, location="output")
        return result
