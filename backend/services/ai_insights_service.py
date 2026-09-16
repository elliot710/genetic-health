"""
Smart Insights Service — Gemini-powered genetic analysis insights.

Uses Google Gemini (Vertex AI Express Mode / AI Studio) to generate contextual,
personalized health insights from the user's genetic analysis results.
Results are cached persistently in the DB (ai_insight_cache table).
"""
import os
import json
import logging
from pathlib import Path
from datetime import UTC, datetime

import aiohttp

logger = logging.getLogger(__name__)

# ── Configuration ───────────────────────────────────────────────────
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("LLM_MODEL_GEMINI", "gemini-3-flash-preview")
VERTEX_AI_PROJECT = os.environ.get("VERTEX_AI_PROJECT", "")
VERTEX_AI_LOCATION = os.environ.get("VERTEX_AI_LOCATION", "us-central1")
MAX_TOKENS = 4000

# Global enable/disable toggle — persisted to file so it survives restarts
_STATE_FILE = Path(os.environ.get("DATA_DIR", "/app/data_sources")) / ".insights_state"

def _load_enabled_state() -> bool:
    """Load persisted enabled state. Falls back to AI_INSIGHTS_ENABLED env var, then False."""
    if _STATE_FILE.exists():
        try:
            return _STATE_FILE.read_text().strip() == "1"
        except OSError:
            pass
    return os.environ.get("AI_INSIGHTS_ENABLED", "false").lower() in ("1", "true", "yes")

_insights_enabled: bool = _load_enabled_state()


# ── System prompt ───────────────────────────────────────────────────
_PROMPT_FILE = Path(__file__).resolve().parent.parent / "prompts" / "genetic_analysis_system.md"


def _load_system_prompt() -> str:
    """Load system prompt from the .md file. Falls back to a minimal prompt if missing."""
    try:
        return _PROMPT_FILE.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.warning("System prompt file not found at %s — using fallback", _PROMPT_FILE)
        return (
            "You are a clinical genomics advisor. Provide evidence-based genetic health insights. "
            "Respond as JSON with keys: summary, key_findings, recommendations, confidence."
        )


SYSTEM_PROMPT = _load_system_prompt()


def _build_user_prompt(section: str, data: dict) -> str:
    """Build a section-specific prompt from dashboard data, including all available information."""
    if section == "overview":
        snippet = {
            "summary": data.get("summary", {}),
            "health_risks": data.get("health_risks", []),
            "drug_responses": data.get("drug_responses", []),
            "carrier_status": data.get("carrier_status", []),
            "rare_mutations_count": len(data.get("rare_mutations", [])),
            "uncommon_mutations_count": len(data.get("uncommon_mutations", [])),
        }
        return f"Generate a comprehensive overview insight for this genetic profile:\n{json.dumps(snippet, default=str)}"

    elif section == "health":
        return f"Analyze ALL of these health risk findings in detail. For each risk, consider the gene, risk level, score, variants involved, and recommendations:\n{json.dumps(data.get('health_risks', []), default=str)}"

    elif section == "drug_responses":
        return f"Analyze ALL of these pharmacogenomic drug response findings. For each, consider the gene, drug, response type, variants, and recommendations:\n{json.dumps(data.get('drug_responses', []), default=str)}"

    elif section == "carrier_status":
        return f"Analyze ALL carrier status findings. For each, consider the condition, carrier status, inheritance pattern, variants, and whether genetic counseling is recommended:\n{json.dumps(data.get('carrier_status', []), default=str)}"

    elif section == "ancestry":
        return f"Analyze these ancestry and population composition results:\n{json.dumps(data.get('ancestry_results', []), default=str)}"

    elif section == "personality":
        return f"Analyze these genetic personality trait findings. Consider each trait's score, confidence, gene, and description:\n{json.dumps(data.get('personality_traits', []), default=str)}"

    elif section == "intelligence":
        return f"Analyze these cognitive ability and intelligence-related genetic findings. Consider each ability's genetic advantage, percentile, and enhancement suggestions:\n{json.dumps(data.get('intelligence', []), default=str)}"

    elif section == "wellness":
        return f"Analyze these wellness trait findings. Consider each trait's category, value, gene, confidence, and recommendations:\n{json.dumps(data.get('wellness_traits', []), default=str)}"

    elif section == "methylation":
        return f"Analyze these methylation profile findings. Consider each gene's variant, methylation capacity, and supplement recommendations:\n{json.dumps(data.get('methylation_profiles', []), default=str)}"

    elif section == "detox":
        return f"Analyze these detoxification profile findings. Consider each phase, gene, detox capacity, toxin sensitivity, and support recommendations:\n{json.dumps(data.get('detoxification_profiles', []), default=str)}"

    elif section == "nutrition":
        return f"Analyze these nutrition and food sensitivity findings. Consider each nutrient's metabolism type, dietary recommendations, and sensitivity level:\n{json.dumps(data.get('nutrition_traits', []), default=str)}"

    elif section == "sports":
        return f"Analyze these sports performance genetic findings. Consider each category's genetic advantage, sport recommendations, and training advice:\n{json.dumps(data.get('sports_performance', []), default=str)}"

    elif section == "physical_traits":
        return f"Analyze these physical trait findings. Consider each trait's category, genetic result, confidence, and description:\n{json.dumps(data.get('physical_traits', []), default=str)}"

    elif section == "rare_mutations":
        return f"Analyze these rare mutation findings. Consider each mutation's gene, type, clinical significance, disease association, penetrance, and population frequency:\n{json.dumps(data.get('rare_mutations', []), default=str)}"

    elif section == "uncommon_mutations":
        return f"Analyze these uncommon mutation findings. Consider each mutation's gene, effect, population frequency, effect size, research status, and clinical relevance:\n{json.dumps(data.get('uncommon_mutations', []), default=str)}"

    else:
        # Generic fallback for any unknown section
        section_data = data.get(section, [])
        return f"Generate insights for the '{section}' category of this genetic analysis:\n{json.dumps(section_data, default=str)}"


def _build_variant_prompt(variant_data: dict) -> str:
    """Build a prompt from variant detail dialog data (all fields)."""
    # Emphasize the user's personal genotype context so the LLM doesn't just
    # describe the variant's pathogenicity in the abstract — it must clarify
    # whether the USER actually carries the pathogenic allele(s) or not.
    genotype_context = ""
    user_gt = variant_data.get("user_genotype")
    allele_string = variant_data.get("allele_string", "")
    if user_gt:
        genotype_context = (
            f"\n\nCRITICAL CONTEXT — The user's personal genotype for this variant is: {user_gt}. "
            f"The reference/alternate alleles are: {allele_string}. "
            "You MUST first determine whether the user carries the pathogenic/alternate allele or the reference allele. "
            "If the user is homozygous reference (carries only the reference allele), clearly state upfront that they are NOT affected by this variant — "
            "even if the variant itself is classified as pathogenic. Do not alarm the user about pathogenicity that does not apply to their genotype. "
            "If the user carries one or two copies of the alternate allele, explain the clinical implications for their specific zygosity."
        )
    return f"Analyze this specific genetic variant in detail. Include clinical significance, population frequency interpretation, functional predictions, and any relevant drug interactions or disease associations.{genotype_context}\n{json.dumps(variant_data, default=str)}"


# ── LLM Calls ──────────────────────────────────────────────────────

def _is_express_mode_key(key: str) -> bool:
    """Vertex AI Express Mode keys start with 'AQ.' (not AI Studio 'AIzaSy')."""
    return bool(key) and key.startswith("AQ.")


def _is_standard_vertex_key(key: str) -> bool:
    """Standard Vertex AI API keys: not AI Studio, not Express Mode."""
    return bool(key) and not key.startswith("AIzaSy") and not key.startswith("AQ.")


async def _call_gemini(user_prompt: str) -> dict:
    """Call Google Gemini API — auto-detects AI Studio vs Vertex AI Express Mode vs standard Vertex AI."""
    timeout = aiohttp.ClientTimeout(total=30)

    if _is_express_mode_key(GEMINI_API_KEY):
        # Vertex AI Express Mode: global endpoint, no project/location in path
        url = (
            f"https://aiplatform.googleapis.com/v1beta1"
            f"/publishers/google/models/{GEMINI_MODEL}:generateContent"
        )
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": GEMINI_API_KEY,
        }
        body = {
            "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": {
                "temperature": 0.3,
                "maxOutputTokens": MAX_TOKENS,
                "responseMimeType": "application/json",
            },
        }
    elif _is_standard_vertex_key(GEMINI_API_KEY) and VERTEX_AI_PROJECT:
        # Standard Vertex AI: regional endpoint with project/location
        url = (
            f"https://{VERTEX_AI_LOCATION}-aiplatform.googleapis.com/v1beta1"
            f"/projects/{VERTEX_AI_PROJECT}/locations/{VERTEX_AI_LOCATION}"
            f"/publishers/google/models/{GEMINI_MODEL}:generateContent"
        )
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": GEMINI_API_KEY,
        }
        body = {
            "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": {
                "temperature": 0.3,
                "maxOutputTokens": MAX_TOKENS,
                "responseMimeType": "application/json",
            },
        }
    else:
        # Google AI Studio endpoint — API key in URL
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
        headers = {"Content-Type": "application/json"}
        body = {
            "contents": [
                {"parts": [{"text": f"{SYSTEM_PROMPT}\n\n{user_prompt}"}]}
            ],
            "generationConfig": {
                "temperature": 0.3,
                "maxOutputTokens": MAX_TOKENS,
                "responseMimeType": "application/json",
            },
        }

    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(url, headers=headers, json=body) as resp:
            if resp.status >= 400:
                body_text = await resp.text()
                logger.error(f"Gemini API {resp.status}: {body_text[:500]}")
            resp.raise_for_status()
            data = await resp.json()
            content = data["candidates"][0]["content"]["parts"][0]["text"]
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            return json.loads(content)


async def _call_llm(user_prompt: str) -> dict:
    """Call Gemini. Raises ValueError if key is not configured."""
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not configured.")
    return await _call_gemini(user_prompt)


# ── Public API ──────────────────────────────────────────────────────

async def generate_insight(
    analysis_id: int,
    section: str,
    dashboard_data: dict,
    db=None,
    force_refresh: bool = False,
) -> dict:
    """
    Generate a Gemini insight for a dashboard section.
    Results are cached persistently in the DB (ai_insight_cache).
    Pass force_refresh=True to delete the cached row and regenerate.
    """
    if not _insights_enabled:
        return {
            "summary": "AI Insights are currently disabled by the administrator.",
            "key_findings": [],
            "recommendations": [],
            "confidence": "low",
            "disabled": True,
        }

    db_key = f"panel:{analysis_id}:{section}"

    # Check DB cache
    if db and not force_refresh:
        from sqlalchemy import select
        from ..db.models import AiInsightCache
        row = (await db.execute(select(AiInsightCache).where(AiInsightCache.cache_key == db_key))).scalar_one_or_none()
        if row:
            logger.info(f"DB insight cache hit: {db_key}")
            return {**row.result, "cached": True}

    # Delete stale cache row if force-refreshing
    if db and force_refresh:
        from sqlalchemy import delete
        from ..db.models import AiInsightCache
        await db.execute(delete(AiInsightCache).where(AiInsightCache.cache_key == db_key))
        await db.commit()

    user_prompt = _build_user_prompt(section, dashboard_data)
    try:
        result = await _call_llm(user_prompt)
        result["provider"] = "gemini"
        result["generated_at"] = datetime.now(UTC).isoformat()

        # Persist to DB
        if db:
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            from ..db.models import AiInsightCache
            stmt = pg_insert(AiInsightCache).values(
                cache_key=db_key,
                result=result,
                provider="gemini",
                generated_at=datetime.now(UTC),
            ).on_conflict_do_update(
                index_elements=["cache_key"],
                set_={"result": result, "provider": "gemini", "generated_at": datetime.now(UTC)},
            )
            await db.execute(stmt)
            await db.commit()

        logger.info(f"Generated insight: {db_key}")
        return result
    except Exception as e:
        logger.error(f"Gemini insight generation failed: {e}")
        return {
            "summary": "Insight generation is currently unavailable.",
            "key_findings": [],
            "recommendations": ["Please try again later or check your API key configuration."],
            "confidence": "low",
            "error": str(e),
        }


def get_llm_status() -> dict:
    """Return current Gemini configuration status (no secrets)."""
    return {
        "provider": "gemini",
        "enabled": _insights_enabled,
        "gemini_configured": bool(GEMINI_API_KEY),
        "model": GEMINI_MODEL,
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


async def generate_variant_insight(rsid: str, variant_data: dict, db=None, force_refresh: bool = False) -> dict:
    """
    Generate a Gemini insight for a specific variant (VariantDetailDialog).
    Cached persistently in DB by rsid. force_refresh deletes the cached row.
    """
    if not _insights_enabled:
        return {
            "summary": "AI Insights are currently disabled by the administrator.",
            "key_findings": [],
            "recommendations": [],
            "confidence": "low",
            "disabled": True,
        }

    db_key = f"variant:{rsid}"

    # Check DB cache
    if db and not force_refresh:
        from sqlalchemy import select
        from ..db.models import AiInsightCache
        row = (await db.execute(select(AiInsightCache).where(AiInsightCache.cache_key == db_key))).scalar_one_or_none()
        if row:
            logger.info(f"DB variant insight cache hit: {rsid}")
            return {**row.result, "cached": True}

    # Delete stale row if force-refreshing
    if db and force_refresh:
        from sqlalchemy import delete
        from ..db.models import AiInsightCache
        await db.execute(delete(AiInsightCache).where(AiInsightCache.cache_key == db_key))
        await db.commit()

    user_prompt = _build_variant_prompt(variant_data)
    try:
        result = await _call_llm(user_prompt)
        result["provider"] = "gemini"
        result["generated_at"] = datetime.now(UTC).isoformat()

        # Persist to DB
        if db:
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            from ..db.models import AiInsightCache
            stmt = pg_insert(AiInsightCache).values(
                cache_key=db_key,
                result=result,
                provider="gemini",
                generated_at=datetime.now(UTC),
            ).on_conflict_do_update(
                index_elements=["cache_key"],
                set_={"result": result, "provider": "gemini", "generated_at": datetime.now(UTC)},
            )
            await db.execute(stmt)
            await db.commit()

        logger.info(f"Generated variant insight for {rsid}")
        return result
    except Exception as e:
        logger.error(f"Gemini variant insight generation failed for {rsid}: {e}")
        return {
            "summary": "Insight generation is currently unavailable.",
            "key_findings": [],
            "recommendations": ["Please try again later or check your API key configuration."],
            "confidence": "low",
            "error": str(e),
        }
