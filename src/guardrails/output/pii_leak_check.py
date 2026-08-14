"""
src/guardrails/output/pii_leak_check.py
────────────────────────────────────────
Re-runs Presidio on the generated output to detect PII leakage.
Can redact in-place or block the response entirely.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.core.exceptions import PIIDetectedError
from src.guardrails.input.pii_redactor import PIIRedactor, PIIResult
from src.utils.logger import get_logger
from src.utils.metrics import GUARDRAIL_TRIGGERS

logger = get_logger(__name__)


class PIILeakChecker:
    """
    Post-generation PII scanner.
    Re-uses PIIRedactor infrastructure to scan LLM output.

    Two modes:
      - block:  Raise PIIDetectedError, return generic refusal message
      - redact: Redact PII entities in-place and return sanitized output
    """

    REFUSAL_MESSAGE = (
        "I'm unable to provide that information as it may contain sensitive "
        "personal data. Please rephrase your request without asking for "
        "specific personal information."
    )

    def __init__(
        self,
        block_on_detect: bool = False,
        threshold: float | None = None,
    ) -> None:
        self.block_on_detect = block_on_detect
        self._redactor = PIIRedactor(threshold=threshold)

    def check(
        self,
        text: str,
        raise_on_detect: bool | None = None,
    ) -> tuple[str, PIIResult]:
        """
        Check generated output for PII leakage.

        Args:
            text: The generated answer text to check.
            raise_on_detect: Override block_on_detect for this call.

        Returns:
            Tuple of (safe_text, PIIResult).
            - safe_text is the original if no PII, or redacted if PII found.

        Raises:
            PIIDetectedError: If block mode is active and PII is found.
        """
        should_raise = raise_on_detect if raise_on_detect is not None else self.block_on_detect

        result = self._redactor.redact(text, location="output")

        if not result.has_pii:
            return text, result

        entity_types = [e["entity_type"] for e in result.entities_found]
        logger.warning(
            "PII detected in LLM output",
            extra={
                "entity_types": entity_types,
                "entity_count": len(result.entities_found),
            },
        )

        GUARDRAIL_TRIGGERS.labels(guardrail_type="pii_leak", direction="output").inc()

        if should_raise:
            raise PIIDetectedError(entities=result.entities_found, location="output")

        # Redact in-place and return sanitized text
        logger.info(
            "PII redacted from output",
            extra={"entity_count": len(result.entities_found)},
        )
        return result.redacted_text, result
