from typing import Dict, Any
from ..utils.annotation_text import clean_snpedia_text, split_condition_string
from ..utils.alpha_missense import AlphaMissenseService


def extract_ensembl(annotation, response: Dict[str, Any]) -> None:
    ensembl = annotation.ensembl_data
    if not (ensembl and isinstance(ensembl, dict) and ensembl.get("found")):
        return
    data = ensembl.get("data", [])
    entry = data[0] if isinstance(data, list) and data else data if isinstance(data, dict) else None
    if not entry:
        return
    response["most_severe_consequence"] = (entry.get("most_severe_consequence") or "").replace("_", " ")
    response["allele_string"] = entry.get("allele_string")
    response["chromosome"] = entry.get("seq_region_name")
    response["position"] = entry.get("start")
    response["transcripts"] = _extract_transcripts(entry)
    response["total_transcripts"] = len(entry.get("transcript_consequences", []))
    _extract_colocated(entry, response)


def _extract_transcripts(entry: dict) -> list:
    tc_list = entry.get("transcript_consequences", [])
    seen, transcripts = set(), []
    for tc in tc_list:
        if tc.get("biotype") != "protein_coding":
            continue
        key = (tc.get("gene_symbol"), tuple(tc.get("consequence_terms", [])))
        if key in seen:
            continue
        seen.add(key)
        transcripts.append({
            "gene_symbol": tc.get("gene_symbol"),
            "gene_id": tc.get("gene_id"),
            "transcript_id": tc.get("transcript_id"),
            "consequence_terms": [t.replace("_", " ") for t in tc.get("consequence_terms", [])],
            "impact": tc.get("impact"),
            "amino_acids": tc.get("amino_acids"),
            "codons": tc.get("codons"),
            "sift_prediction": tc.get("sift_prediction"),
            "sift_score": tc.get("sift_score"),
            "polyphen_prediction": tc.get("polyphen_prediction"),
            "polyphen_score": tc.get("polyphen_score"),
            "protein_position": str(tc.get("protein_start", "")) if tc.get("protein_start") else None,
        })
        if len(transcripts) >= 6:
            break
    return transcripts


def _extract_colocated(entry: dict, response: Dict[str, Any]) -> None:
    colocated = entry.get("colocated_variants", [])
    clin_sigs, clinvar_ids, frequencies = [], [], {}
    for cv in colocated:
        if cv.get("clin_sig"):
            clin_sigs.extend(cv["clin_sig"])
        if cv.get("var_synonyms", {}).get("ClinVar"):
            clinvar_ids.extend(cv["var_synonyms"]["ClinVar"])
        _extract_population_freqs(cv, frequencies)
    response["clinical_significance"] = list(set(clin_sigs))
    response["clinvar_ids"] = list(set(clinvar_ids))
    response["population_frequencies"] = frequencies


def _extract_population_freqs(cv: dict, frequencies: Dict) -> None:
    freqs = cv.get("frequencies", {})
    pop_name_map = {
        "gnomade": "gnomAD exomes (global)", "gnomadg": "gnomAD genomes (global)",
        "af": "1000 Genomes (global)",
    }
    for allele, pops in freqs.items():
        for pop, freq in pops.items():
            if pop in pop_name_map or pop.startswith("gnomade_") or pop.startswith("gnomadg_"):
                clean_pop = pop_name_map.get(pop, pop.replace("gnomade_", "gnomAD exomes: ").replace("gnomadg_", "gnomAD genomes: "))
                if clean_pop not in frequencies or freq > frequencies[clean_pop]["frequency"]:
                    frequencies[clean_pop] = {"allele": allele, "frequency": freq}


def extract_clinvar(annotation, response: Dict[str, Any], db_session=None) -> None:
    clinvar = annotation.clinvar_data
    if not (clinvar and isinstance(clinvar, dict) and clinvar.get("found")):
        return
    entries = clinvar.get("entries", [])
    _clean_clinvar_conditions(entries)
    response["clinvar"] = {
        "found": True, "count": clinvar.get("count", 0),
        "ids": clinvar.get("ids", []), "entries": entries,
    }


def _clean_clinvar_conditions(entries: list) -> None:
    for entry in entries:
        raw_conds = entry.get("conditions", [])
        cleaned = []
        for c in raw_conds:
            cleaned.extend(split_condition_string(c))
        entry["conditions"] = list(dict.fromkeys(cleaned))


def extract_clinvar_local(annotation, response: Dict[str, Any]) -> None:
    cv_local = annotation.clinvar_local_data
    if not (cv_local and isinstance(cv_local, dict) and cv_local.get("found")):
        return
    cv_local_resp: Dict[str, Any] = {
        "found": True,
        "genes": cv_local.get("genes", []),
        "clinical_significances": cv_local.get("clinical_significances", []),
        "gene_conditions": cv_local.get("gene_conditions", []),
        "review_statuses": cv_local.get("review_statuses", []),
        "has_conflicting_interpretations": cv_local.get("has_conflicting_interpretations", False),
    }
    vcf = cv_local.get("vcf_data", {})
    if vcf:
        cv_local_resp["molecular_consequences"] = vcf.get("molecular_consequences", [])
        cv_local_resp["conflicting_classifications"] = vcf.get("conflicting_classifications", [])
        cv_local_resp["allele_frequencies"] = vcf.get("allele_frequencies", {})
    if cv_local.get("gene_stats"):
        cv_local_resp["gene_stats"] = cv_local["gene_stats"]
    response["clinvar_local"] = cv_local_resp

    if "clinvar" not in response or not response.get("clinvar", {}).get("entries"):
        entries = cv_local.get("entries", [])
        if entries:
            _clean_clinvar_conditions(entries)
            response["clinvar"] = {
                "found": True, "count": cv_local.get("count", len(entries)),
                "ids": cv_local.get("ids", []), "entries": entries,
            }


def extract_pharmacogenomics(annotation, response: Dict[str, Any]) -> None:
    raw = annotation.pharmgkb_data
    if raw and isinstance(raw, dict) and raw.get("found"):
        response["pharmacogenomics"] = {"found": True, "data": raw.get("data", {})}


def extract_snpedia(annotation, response: Dict[str, Any]) -> None:
    snpedia = annotation.snpedia_data
    if not (snpedia and isinstance(snpedia, dict) and snpedia.get("found")):
        return
    wiki_data = snpedia.get("data", {})
    revisions = wiki_data.get("revisions", [])
    wiki_text = revisions[0].get("*", "") if revisions else ""
    response["snpedia"] = {
        "found": True, "title": wiki_data.get("title", ""),
        "summary": clean_snpedia_text(wiki_text),
    }


def extract_publications(annotation, response: Dict[str, Any]) -> None:
    litvar = annotation.litvar_data
    if not (litvar and isinstance(litvar, dict) and litvar.get("found")):
        return
    pubs = litvar.get("publications", [])
    response["publications"] = {
        "count": len(pubs),
        "items": [{"pmid": p.get("pmid"), "title": p.get("title"),
                    "journal": p.get("journal"), "year": p.get("year")} for p in pubs[:20]],
    }


def extract_alpha_missense(annotation, response: Dict[str, Any]) -> None:
    am_raw = annotation.alpha_missense_data
    if am_raw and isinstance(am_raw, dict) and am_raw.get("found"):
        formatted = AlphaMissenseService.format_result_for_display(am_raw)
        if formatted:
            response["alpha_missense"] = formatted


def extract_gnomad(annotation, response: Dict[str, Any]) -> None:
    raw = annotation.gnomad_data
    if not (raw and isinstance(raw, dict) and raw.get("found")):
        return
    resp: Dict[str, Any] = {
        "found": True, "source": raw.get("source", "gnomad"),
        "variant_id": raw.get("variant_id"), "variant_type": raw.get("variant_type"),
        "af": raw.get("af"), "ac": raw.get("ac"), "an": raw.get("an"),
        "nhomalt": raw.get("nhomalt"), "filter_status": raw.get("filter_status"),
        "gene": raw.get("gene"), "consequence": raw.get("consequence"),
        "impact": raw.get("impact"), "hgvsc": raw.get("hgvsc"), "hgvsp": raw.get("hgvsp"),
    }
    for key in ("population_frequencies", "cadd", "predictions", "conservation", "splice_ai"):
        if raw.get(key):
            resp[key] = raw[key]
    response["gnomad"] = resp


def extract_gnomad_tx(annotation, response: Dict[str, Any]) -> None:
    raw = annotation.gnomad_tx_data
    if not (raw and isinstance(raw, dict) and raw.get("found")):
        return
    resp: Dict[str, Any] = {
        "found": True, "source": "gnomad_tx",
        "gene": raw.get("gene"), "consequence": raw.get("consequence"),
        "lof": raw.get("lof"), "mean_expression": raw.get("mean_expression"),
        "transcript_count": raw.get("transcript_count", 0),
    }
    transcripts = raw.get("transcripts", [])
    if transcripts:
        primary = transcripts[0]
        if primary.get("top_tissues"):
            resp["top_tissues"] = primary["top_tissues"]
        resp["transcripts"] = transcripts
    response["gnomad_tx"] = resp


def extract_thousand_genomes(annotation, response: Dict[str, Any]) -> None:
    raw = annotation.thousand_genomes_data
    if not (raw and isinstance(raw, dict) and raw.get("found")):
        return
    resp: Dict[str, Any] = {
        "found": True, "source": raw.get("source", "1000genomes_local"),
        "variant_type": raw.get("variant_type"),
        "minor_allele": raw.get("minor_allele"), "maf": raw.get("maf"),
        "mac": raw.get("mac"), "ancestral_allele": raw.get("ancestral_allele"),
    }
    if raw.get("population_frequencies"):
        resp["population_frequencies"] = raw["population_frequencies"]
    response["thousand_genomes"] = resp


def extract_gwas_clingen(annotation, response: Dict[str, Any]) -> None:
    gwas_raw = annotation.gwas_catalog_data
    if gwas_raw and isinstance(gwas_raw, dict) and gwas_raw.get("found"):
        response["gwas_catalog"] = {
            "found": True, "source": "gwas_catalog",
            "associations": gwas_raw.get("associations", [])[:10],
            "top_trait": gwas_raw.get("top_trait"),
            "top_p_value": gwas_raw.get("top_p_value"),
            "genome_wide_significant": gwas_raw.get("genome_wide_significant", False),
        }
    clingen_raw = annotation.clingen_data
    if clingen_raw and isinstance(clingen_raw, dict) and clingen_raw.get("found"):
        response["clingen"] = {
            "found": True, "source": "clingen",
            "gene_symbol": clingen_raw.get("gene_symbol"),
            "strongest_classification": clingen_raw.get("strongest_classification"),
            "is_definitive": clingen_raw.get("is_definitive", False),
            "is_disputed": clingen_raw.get("is_disputed", False),
            "disease_count": clingen_raw.get("disease_count", 0),
            "curations": clingen_raw.get("curations", [])[:8],
        }


def backfill_clinical_significance(annotation, response: Dict[str, Any]) -> None:
    if response.get("clinical_significance"):
        return
    sigs = []
    for entry in response.get("clinvar", {}).get("entries", []):
        for sig in entry.get("clinical_significance", []):
            if sig and sig not in sigs:
                sigs.append(sig)
    if not sigs:
        cv_local = annotation.clinvar_local_data
        if cv_local and isinstance(cv_local, dict):
            for sig in cv_local.get("clinical_significances", []):
                if sig and sig not in sigs:
                    sigs.append(sig)
    if sigs:
        response["clinical_significance"] = sigs


def compute_pathogenicity_score(annotation, response: Dict[str, Any]) -> dict:
    from ..services.scoring_engine import get_scoring_engine
    scoring_annotations = {}
    source_attrs = [
        ("ensembl", "ensembl_data"), ("clinvar", "clinvar_data"),
        ("clinvar_local", "clinvar_local_data"), ("alpha_missense", "alpha_missense_data"),
        ("gnomad", "gnomad_data"), ("thousand_genomes", "thousand_genomes_data"),
        ("gwas_catalog", "gwas_catalog_data"), ("clingen", "clingen_data"),
        ("open_targets", "open_targets_data"), ("alphafold", "alphafold_data"),
        ("litvar", "litvar_data"), ("chembl", "chembl_data"),
        ("fda_drug", "fda_drug_data"), ("gnomad_tx", "gnomad_tx_data"),
    ]
    for key, attr in source_attrs:
        val = getattr(annotation, attr, None)
        if val:
            scoring_annotations[key] = val
    return scoring_annotations, get_scoring_engine().score_variant(scoring_annotations)
