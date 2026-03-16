"""
Smart Insights Service — LLM-powered genetic analysis insights.

Supports OpenAI, Anthropic, and Google Gemini as providers. Generates contextual,
personalized health insights from the user's genetic analysis results.
"""
import os
import json
import logging
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

# ── Provider configuration ──────────────────────────────────────────
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "gemini")  # "openai" | "anthropic" | "gemini"
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
OPENAI_MODEL = os.environ.get("LLM_MODEL_OPENAI", "gpt-4o-mini")
ANTHROPIC_MODEL = os.environ.get("LLM_MODEL_ANTHROPIC", "claude-sonnet-4-20250514")
GEMINI_MODEL = os.environ.get("LLM_MODEL_GEMINI", "gemini-2.5-flash-lite")
MAX_TOKENS = 1200
CACHE_TTL_HOURS = 24

# Global enable/disable toggle — persisted to file so it survives restarts
_STATE_FILE = Path(__file__).resolve().parent.parent.parent / ".insights_state"

def _load_enabled_state() -> bool:
    """Load persisted enabled state. Falls back to AI_INSIGHTS_ENABLED env var, then False."""
    if _STATE_FILE.exists():
        try:
            return _STATE_FILE.read_text().strip() == "1"
        except OSError:
            pass
    return os.environ.get("AI_INSIGHTS_ENABLED", "false").lower() in ("1", "true", "yes")

_insights_enabled: bool = _load_enabled_state()

# In-memory insight cache  {hash → (timestamp, result)}
_insight_cache: dict[str, tuple[datetime, dict]] = {}


def _cache_key(analysis_id: int, section: str) -> str:
    return hashlib.sha256(f"{analysis_id}:{section}".encode()).hexdigest()[:16]


def _get_cached(analysis_id: int, section: str) -> Optional[dict]:
    key = _cache_key(analysis_id, section)
    if key in _insight_cache:
        ts, data = _insight_cache[key]
        if datetime.utcnow() - ts < timedelta(hours=CACHE_TTL_HOURS):
            return data
        del _insight_cache[key]
    return None


def _set_cached(analysis_id: int, section: str, data: dict) -> None:
    key = _cache_key(analysis_id, section)
    _insight_cache[key] = (datetime.utcnow(), data)


# ── System prompt ───────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a clinical genomics advisor providing clear, evidence-based
genetic health insights. You receive structured genetic analysis data and produce
concise, personalized summaries.

Rules:
- Be factual and cite risk levels when available.
- Use plain language; avoid unnecessary jargon.
- Highlight actionable recommendations when possible.
- Never diagnose or replace professional medical advice — always include a disclaimer.
- Structure your response as JSON with keys: "summary" (1-2 sentences), "key_findings" (array of strings, max 5), "recommendations" (array of strings, max 3), "confidence" ("high"|"medium"|"low").
"""


def _build_user_prompt(section: str, data: dict) -> str:
    """Build a section-specific prompt from dashboard data."""
    if section == "overview":
        snippet = {
            "total_variants": data.get("summary", {}).get("total_variants", 0),
            "analyzed": data.get("summary", {}).get("analyzed_variants", 0),
            "health_risks_count": len(data.get("health_risks", [])),
            "drug_responses_count": len(data.get("drug_responses", [])),
            "carrier_conditions": len(data.get("carrier_status", [])),
            "rare_mutations": len(data.get("rare_mutations", [])),
        }
        # Include top health risks
        risks = data.get("health_risks", [])[:5]
        if risks:
            snippet["top_health_risks"] = [
                {"condition": r.get("condition"), "risk_level": r.get("risk_level")}
                for r in risks
            ]
        return f"Generate an overview insight for this genetic profile:\n{json.dumps(snippet)}"

    elif section == "health":
        risks = data.get("health_risks", [])[:10]
        snippet = [
            {"condition": r.get("condition"), "risk_level": r.get("risk_level"), "gene": r.get("gene")}
            for r in risks
        ]
        return f"Analyze these health risk findings:\n{json.dumps(snippet)}"

    elif section == "drug_responses":
        drugs = data.get("drug_responses", [])[:10]
        snippet = [
            {"drug": d.get("drug"), "gene": d.get("gene"), "response_type": d.get("response_type")}
            for d in drugs
        ]
        return f"Summarize these pharmacogenomic interactions:\n{json.dumps(snippet)}"

    elif section == "carrier_status":
        carriers = data.get("carrier_status", [])[:10]
        snippet = [
            {"condition": c.get("condition"), "carrier_status": c.get("carrier_status"), "gene": c.get("gene")}
            for c in carriers
        ]
        return f"Summarize the carrier status findings:\n{json.dumps(snippet)}"

    else:
        # Generic fallback
        return f"Generate insights for the '{section}' category of this genetic analysis:\n{json.dumps(data.get(section, [])[:8])}"


# ── LLM Calls ──────────────────────────────────────────────────────

async def _call_openai(user_prompt: str) -> dict:
    """Call OpenAI Chat Completions API."""
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": OPENAI_MODEL,
                "max_tokens": MAX_TOKENS,
                "temperature": 0.3,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
            },
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()
            content = data["choices"][0]["message"]["content"]
            return json.loads(content)


async def _call_anthropic(user_prompt: str) -> dict:
    """Call Anthropic Messages API."""
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": ANTHROPIC_MODEL,
                "max_tokens": MAX_TOKENS,
                "system": SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": user_prompt}],
            },
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()
            content = data["content"][0]["text"]
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            return json.loads(content)


async def _call_gemini(user_prompt: str) -> dict:
    """Call Google Gemini API via generativelanguage.googleapis.com (API key auth)."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(
            url,
            headers={"Content-Type": "application/json"},
            json={
                "contents": [
                    {"parts": [{"text": f"{SYSTEM_PROMPT}\n\n{user_prompt}"}]}
                ],
                "generationConfig": {
                    "temperature": 0.3,
                    "maxOutputTokens": MAX_TOKENS,
                    "responseMimeType": "application/json",
                },
            },
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()
            content = data["candidates"][0]["content"]["parts"][0]["text"]
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            return json.loads(content)


async def _call_llm(user_prompt: str) -> dict:
    """Route to configured LLM provider."""
    provider = LLM_PROVIDER.lower()
    if provider == "gemini" and GEMINI_API_KEY:
        return await _call_gemini(user_prompt)
    elif provider == "anthropic" and ANTHROPIC_API_KEY:
        return await _call_anthropic(user_prompt)
    elif provider == "openai" and OPENAI_API_KEY:
        return await _call_openai(user_prompt)
    # Fallback: try whichever key is available
    elif GEMINI_API_KEY:
        return await _call_gemini(user_prompt)
    elif OPENAI_API_KEY:
        return await _call_openai(user_prompt)
    elif ANTHROPIC_API_KEY:
        return await _call_anthropic(user_prompt)
    else:
        raise ValueError("No LLM API key configured. Set GEMINI_API_KEY, OPENAI_API_KEY, or ANTHROPIC_API_KEY.")


# ── Public API ──────────────────────────────────────────────────────

async def generate_insight(analysis_id: int, section: str, dashboard_data: dict) -> dict:
    """
    Generate an LLM-powered insight for a given analysis section.
    Returns: {"summary": str, "key_findings": [str], "recommendations": [str], "confidence": str, "provider": str}
    """
    if not _insights_enabled:
        return {
            "summary": "AI Insights are currently disabled by the administrator.",
            "key_findings": [],
            "recommendations": [],
            "confidence": "low",
            "disabled": True,
        }

    # Check cache
    cached = _get_cached(analysis_id, section)
    if cached:
        logger.info(f"Insights cache hit for analysis {analysis_id} section {section}")
        return cached

    user_prompt = _build_user_prompt(section, dashboard_data)
    try:
        result = await _call_llm(user_prompt)
        result["provider"] = LLM_PROVIDER
        result["generated_at"] = datetime.utcnow().isoformat()
        _set_cached(analysis_id, section, result)
        logger.info(f"Generated insight for analysis {analysis_id} section {section}")
        return result
    except Exception as e:
        logger.error(f"LLM insight generation failed: {e}")
        return {
            "summary": "Insight generation is currently unavailable.",
            "key_findings": [],
            "recommendations": ["Please try again later or check your API key configuration."],
            "confidence": "low",
            "error": str(e),
        }


def get_llm_status() -> dict:
    """Return current LLM configuration status (no secrets)."""
    provider = LLM_PROVIDER.lower()
    if provider == "gemini":
        model = GEMINI_MODEL
    elif provider == "anthropic":
        model = ANTHROPIC_MODEL
    else:
        model = OPENAI_MODEL
    return {
        "provider": provider,
        "enabled": _insights_enabled,
        "openai_configured": bool(OPENAI_API_KEY),
        "anthropic_configured": bool(ANTHROPIC_API_KEY),
        "gemini_configured": bool(GEMINI_API_KEY),
        "model": model,
        "cache_entries": len(_insight_cache),
    }


def set_insights_enabled(enabled: bool) -> dict:
    """Enable or disable AI insights for all users. Persists across restarts."""
    global _insights_enabled
    _insights_enabled = enabled
    try:
        _STATE_FILE.write_text("1" if enabled else "0")
    except OSError:
        logger.warning("Could not persist insights state to file")
    logger.info(f"AI Insights {'enabled' if enabled else 'disabled'} by admin")
    return get_llm_status()
