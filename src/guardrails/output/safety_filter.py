"""
src/guardrails/output/safety_filter.py
───────────────────────────────────────
Content safety classification for LLM outputs.
Uses pattern matching and optional LLM-based classification to detect
harmful content categories: hate speech, violence, self-harm, etc.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from src.core.config import get_settings
from src.core.exceptions import ContentSafetyError
from src.utils.logger import get_logger
from src.utils.metrics import GUARDRAIL_TRIGGERS

logger = get_logger(__name__)


@dataclass
class SafetyResult:
    """Result of content safety classification."""
    is_safe: bool
    triggered_category: str | None = None
    triggered_score: float = 0.0
    flags: dict[str, float] = field(default_factory=dict)


# ── Pattern-Based Classifier ──────────────────────────────────────────────────

# Lightweight keyword patterns for fast classification
_SAFETY_PATTERNS: dict[str, list[re.Pattern]] = {
    "hate_speech": [
        re.compile(r"\b(?:kill\s+all|death\s+to|exterminate)\s+(?:jews|muslims|christians|blacks|whites|asians|gays)\b", re.IGNORECASE),
        re.compile(r"\b(?:racial|ethnic)\s+slur\b", re.IGNORECASE),
    ],
    "violence": [
        re.compile(r"\bhow\s+to\s+(?:make|build|construct)\s+(?:a\s+)?(?:bomb|explosive|weapon)\b", re.IGNORECASE),
        re.compile(r"\bstep[- ]by[- ]step.{0,30}(?:kill|murder|assault)\b", re.IGNORECASE),
    ],
    "self_harm": [
        re.compile(r"\bhow\s+to\s+(?:commit\s+suicide|self\s+harm|cut\s+yourself)\b", re.IGNORECASE),
        re.compile(r"\b(?:methods|ways)\s+to\s+(?:end\s+your|take\s+your)\s+life\b", re.IGNORECASE),
    ],
    "sexual_content": [
        re.compile(r"\bchild\s+(?:sexual\s+abuse|pornography|exploitation)\b", re.IGNORECASE),
    ],
    "illegal_activities": [
        re.compile(r"\bhow\s+to\s+(?:synthesize|make|produce)\s+(?:meth|cocaine|heroin|fentanyl)\b", re.IGNORECASE),
        re.compile(r"\bhow\s+to\s+(?:hack|bypass|exploit)\s+(?:a\s+)?(?:system|database|network|server)\b", re.IGNORECASE),
        re.compile(r"\bsynthesis\s+of\s+(?:explosives|narcotics|poison)\b", re.IGNORECASE),
    ],
}


def _load_banned_phrases() -> list[str]:
    """Load banned phrases from guardrails.yaml config."""
    config_path = get_settings().configs_dir / "guardrails.yaml"
    if config_path.exists():
        with open(config_path) as f:
            config = yaml.safe_load(f)
        return config.get("safety", {}).get("banned_phrases", [])
    return []


def _pattern_safety_check(text: str) -> SafetyResult:
    """Fast pattern-based safety classification."""
    lowered = text.lower()

    # Check banned phrases
    banned = _load_banned_phrases()
    for phrase in banned:
        if phrase.lower() in lowered:
            return SafetyResult(
                is_safe=False,
                triggered_category="banned_phrase",
                triggered_score=1.0,
                flags={"banned_phrase": 1.0},
            )

    # Check pattern categories
    flags: dict[str, float] = {}
    for category, patterns in _SAFETY_PATTERNS.items():
        for pattern in patterns:
            if pattern.search(text):
                flags[category] = 1.0
                logger.warning(
                    "Content safety pattern triggered",
                    extra={"category": category},
                )
                return SafetyResult(
                    is_safe=False,
                    triggered_category=category,
                    triggered_score=1.0,
                    flags=flags,
                )

    return SafetyResult(is_safe=True, flags={})


# ── LLM-Based Classifier (optional) ──────────────────────────────────────────

_SAFETY_LLM_PROMPT = """You are a content safety classifier.

Classify the following text for harmful content. 
Check for: hate_speech, violence, self_harm, sexual_content, illegal_activities.

Respond ONLY with a JSON object:
{{"is_safe": true/false, "category": "category_name_or_null", "confidence": 0.0-1.0}}

Text to classify:
{text}"""


def _llm_safety_check(text: str, threshold: float = 0.80) -> SafetyResult:
    """LLM-based content safety classification for nuanced cases."""
    import json

    settings = get_settings()

    try:
        if settings.llm_provider == "openai":
            from langchain_openai import ChatOpenAI
            llm = ChatOpenAI(
                model=settings.openai_model,
                temperature=0.0,
                api_key=settings.openai_api_key,
            )
        else:
            from langchain_google_genai import ChatGoogleGenerativeAI
            llm = ChatGoogleGenerativeAI(
                model=settings.gemini_model,
                temperature=0.0,
                google_api_key=settings.gemini_api_key,
            )

        response = llm.invoke(_SAFETY_LLM_PROMPT.format(text=text[:2000]))
        content = re.sub(r"```(?:json)?\s*|\s*```", "", response.content.strip()).strip()
        result = json.loads(content)

        is_safe = result.get("is_safe", True)
        confidence = float(result.get("confidence", 0.0))
        category = result.get("category")

        if not is_safe and confidence >= threshold and category:
            return SafetyResult(
                is_safe=False,
                triggered_category=category,
                triggered_score=confidence,
                flags={category: confidence},
            )

    except Exception as e:
        logger.warning("LLM safety check failed", extra={"error": str(e)})

    return SafetyResult(is_safe=True)


# ── Public API ────────────────────────────────────────────────────────────────

class ContentSafetyFilter:
    """
    Two-stage content safety filter:
      Stage 1: Fast regex/pattern check
      Stage 2: LLM classification fallback (optional)
    """

    def __init__(
        self,
        use_llm_fallback: bool = False,
        category_threshold: float = 0.80,
    ) -> None:
        self.use_llm_fallback = use_llm_fallback
        self.category_threshold = category_threshold

    def check(
        self,
        text: str,
        raise_on_unsafe: bool = True,
    ) -> SafetyResult:
        """
        Run safety classification on the given text.

        Args:
            text: Content to classify.
            raise_on_unsafe: If True, raise ContentSafetyError on detection.

        Returns:
            SafetyResult

        Raises:
            ContentSafetyError: If unsafe content detected and raise_on_unsafe is True.
        """
        # Stage 1: Pattern check
        result = _pattern_safety_check(text)

        if result.is_safe and self.use_llm_fallback:
            # Stage 2: LLM fallback
            result = _llm_safety_check(text, threshold=self.category_threshold)

        if not result.is_safe:
            GUARDRAIL_TRIGGERS.labels(guardrail_type="content_safety", direction="output").inc()
            logger.warning(
                "Content safety triggered",
                extra={
                    "category": result.triggered_category,
                    "score": result.triggered_score,
                },
            )
            if raise_on_unsafe:
                raise ContentSafetyError(
                    category=result.triggered_category or "unknown",
                    score=result.triggered_score,
                )

        return result
