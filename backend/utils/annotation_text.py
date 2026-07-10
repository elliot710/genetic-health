import re
from typing import Dict, Any, Optional, List


def clean_snpedia_text(wiki_text: str) -> str:
    if not wiki_text:
        return ""
    m = re.search(r'\|Summary\s*=\s*([^\n|]+)', wiki_text)
    rsnum_summary = m.group(1).strip() if m else ""

    cleaned = wiki_text
    for _ in range(10):
        prev = cleaned
        cleaned = re.sub(r'\{\{[^{}]*\}\}', ' ', cleaned)
        if cleaned == prev:
            break
    cleaned = re.sub(r'\{\{[^}]*$', '', cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r'\[\[([^|\]]+)\|([^\]]+)\]\]', r'\2', cleaned)
    cleaned = re.sub(r'\[\[([^\]]+)\]\]', r'\1', cleaned)
    cleaned = re.sub(r'\[https?://[^\]\s]+\s+([^\]]+)\]', r'\1', cleaned)
    cleaned = re.sub(r'\[https?://[^\]\s]+\]', '', cleaned)
    cleaned = re.sub(r'\[\[Category:[^\]]*\]\]', '', cleaned)
    cleaned = re.sub(r'<[^>]+>', '', cleaned)
    cleaned = re.sub(r"'{2,}", '', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()

    if len(cleaned) > 20:
        return cleaned[:800]
    return rsnum_summary or cleaned[:800]


def is_noise_condition(s: str) -> bool:
    return s.lower().strip() in ("not provided", "not specified", "see cases", "")


def split_condition_string(raw: str) -> list:
    parts = []
    for chunk in raw.split("|"):
        for sub in chunk.split(";"):
            cleaned = sub.strip()
            if cleaned and not is_noise_condition(cleaned):
                parts.append(cleaned)
    return parts


def is_hgvs_name(title: str) -> bool:
    return bool(title) and (":c." in title or ":p." in title or ":g." in title
                            or title.startswith("NM_") or title.startswith("NC_")
                            or title.startswith("NR_"))


def build_variant_description(rsid: str, response: Dict[str, Any]) -> str:
    parts = []
    consequence = response.get("most_severe_consequence", "")
    variant_type_label = consequence if consequence else "variant"

    gene = None
    transcripts = response.get("transcripts", [])
    if transcripts:
        gene = transcripts[0].get("gene_symbol")

    hgvs_name = None
    all_conditions: list = []
    clinvar_variation_type = None
    for entry in response.get("clinvar", {}).get("entries", []):
        title = entry.get("title", "")
        if title and not hgvs_name and is_hgvs_name(title):
            hgvs_name = title
        vt = entry.get("variation_type", "")
        if vt and not clinvar_variation_type:
            clinvar_variation_type = vt
        for cond_str in entry.get("conditions", []):
            all_conditions.extend(split_condition_string(cond_str))

    all_conditions = list(dict.fromkeys(all_conditions))
    if clinvar_variation_type:
        variant_type_label = clinvar_variation_type

    if gene and gene != "Unknown" and not gene.startswith("rs"):
        parts.append(f"{rsid} is a {variant_type_label} in the {gene} gene")
    else:
        parts.append(f"{rsid} is a {variant_type_label}")

    parts[-1] += f", specifically identified as {hgvs_name}." if hgvs_name else "."
    if all_conditions:
        joined = ", ".join(all_conditions[:-1]) + " and " + all_conditions[-1] if len(all_conditions) > 1 else all_conditions[0]
        parts.append(f"This variant is associated with {joined}.")

    clin_sigs = response.get("clinical_significance", [])
    if clin_sigs:
        parts.append(f"Clinical assessments classify it as {', '.join(s.replace('_', ' ') for s in clin_sigs)}.")
    if response.get("pharmacogenomics", {}).get("found"):
        parts.append("It has known pharmacogenomic associations that may affect drug response.")
    return " ".join(parts) if len(parts) > 1 else parts[0] if parts else ""
