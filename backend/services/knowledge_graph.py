"""
Knowledge Graph Service — builds gene→variant→condition→drug relationships.

Traverses the user's genetic analysis data to construct a graph of
interconnected entities for visual exploration.
"""
import logging
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..db.models import (
    GeneticAnalysis, HealthRisk, DrugResponse, CarrierStatus,
    MethylationProfile, DetoxificationProfile, RareMutation, UncommonMutation,
    AnalysisVariant, GeneticMarker, SharedVariantAnnotation,
)

logger = logging.getLogger(__name__)

# Node types and their colours (used by frontend)
NODE_TYPES = {
    "gene": {"color": "#8b5cf6", "size": 28},
    "variant": {"color": "#06b6d4", "size": 18},
    "condition": {"color": "#ef4444", "size": 24},
    "drug": {"color": "#f59e0b", "size": 22},
    "pathway": {"color": "#22c55e", "size": 20},
}


async def build_knowledge_graph(user_id: int, session: AsyncSession) -> dict:
    """
    Build a knowledge graph from the user's latest analysis.
    Returns: { nodes: [...], edges: [...], stats: {...} }
    """
    # Find latest analysis
    result = await session.execute(
        select(GeneticAnalysis)
        .where(
            GeneticAnalysis.user_id == user_id,
            GeneticAnalysis.deleted_at.is_(None),
        )
        .order_by(GeneticAnalysis.upload_date.desc())
        .limit(1)
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        return {"nodes": [], "edges": [], "stats": {}}

    analysis_id = analysis.id
    nodes: dict[str, dict] = {}  # id → node
    edges: list[dict] = []
    edge_set: set[tuple[str, str]] = set()  # dedup

    def add_node(nid: str, label: str, ntype: str, **extra):
        if nid not in nodes:
            meta = NODE_TYPES.get(ntype, {"color": "#94a3b8", "size": 16})
            nodes[nid] = {"id": nid, "label": label, "type": ntype, "color": meta["color"], "size": meta["size"], **extra}

    def add_edge(source: str, target: str, relation: str):
        key = (source, target)
        if key not in edge_set and source in nodes and target in nodes:
            edge_set.add(key)
            edges.append({"source": source, "target": target, "relation": relation})

    # ── Health Risks ────────────────────────────────────────────────
    hr_result = await session.execute(
        select(HealthRisk).where(HealthRisk.analysis_id == analysis_id)
    )
    for risk in hr_result.scalars():
        cond_id = f"cond:{risk.condition}"
        add_node(cond_id, risk.condition, "condition", risk_level=risk.risk_level)
        variants = risk.associated_variants or []
        for v in variants:
            if isinstance(v, str) and v.startswith("rs"):
                var_id = f"var:{v}"
                add_node(var_id, v, "variant")
                add_edge(var_id, cond_id, "contributes_to")

    # ── Drug Responses ──────────────────────────────────────────────
    dr_result = await session.execute(
        select(DrugResponse).where(DrugResponse.analysis_id == analysis_id)
    )
    for drug_resp in dr_result.scalars():
        if drug_resp.drug:
            drug_id = f"drug:{drug_resp.drug}"
            add_node(drug_id, drug_resp.drug, "drug", response_type=drug_resp.response_type)
            if drug_resp.gene:
                gene_id = f"gene:{drug_resp.gene}"
                add_node(gene_id, drug_resp.gene, "gene")
                add_edge(gene_id, drug_id, "metabolizes")
            variants = drug_resp.variants_involved or []
            for v in variants:
                if isinstance(v, str) and v.startswith("rs"):
                    var_id = f"var:{v}"
                    add_node(var_id, v, "variant")
                    if drug_resp.gene:
                        add_edge(f"gene:{drug_resp.gene}", var_id, "contains")
                    add_edge(var_id, drug_id, "affects_response")

    # ── Carrier Status ──────────────────────────────────────────────
    cs_result = await session.execute(
        select(CarrierStatus).where(CarrierStatus.analysis_id == analysis_id)
    )
    for carrier in cs_result.scalars():
        cond_id = f"cond:{carrier.condition}"
        add_node(cond_id, carrier.condition, "condition", carrier_status=carrier.carrier_status)
        variants = carrier.associated_variants or []
        for v in variants:
            if isinstance(v, str) and v.startswith("rs"):
                var_id = f"var:{v}"
                add_node(var_id, v, "variant")
                add_edge(var_id, cond_id, "linked_to")

    # ── Methylation Profiles ────────────────────────────────────────
    mp_result = await session.execute(
        select(MethylationProfile).where(MethylationProfile.analysis_id == analysis_id)
    )
    for prof in mp_result.scalars():
        pathway_id = "pathway:methylation"
        add_node(pathway_id, "Methylation Cycle", "pathway")
        if prof.gene:
            gene_id = f"gene:{prof.gene}"
            add_node(gene_id, prof.gene, "gene")
            add_edge(gene_id, pathway_id, "participates_in")

    # ── Detoxification ──────────────────────────────────────────────
    dp_result = await session.execute(
        select(DetoxificationProfile).where(DetoxificationProfile.analysis_id == analysis_id)
    )
    for prof in dp_result.scalars():
        phase = prof.detox_phase or "unknown"
        pathway_id = f"pathway:detox_{phase}"
        add_node(pathway_id, f"Detox {phase.replace('_', ' ').title()}", "pathway")
        if prof.gene:
            gene_id = f"gene:{prof.gene}"
            add_node(gene_id, prof.gene, "gene")
            add_edge(gene_id, pathway_id, "participates_in")

    # ── Rare / Uncommon Mutations ───────────────────────────────────
    for Model in (RareMutation, UncommonMutation):
        rm_result = await session.execute(
            select(Model).where(Model.analysis_id == analysis_id)
        )
        for mut in rm_result.scalars():
            gene_id = f"gene:{mut.gene}" if mut.gene else None
            if mut.gene:
                add_node(gene_id, mut.gene, "gene")
            # Extract rsids from associated_variants JSON
            variants = mut.associated_variants or []
            for v in variants:
                if isinstance(v, str) and v.startswith("rs"):
                    var_id = f"var:{v}"
                    add_node(var_id, v, "variant")
                    if gene_id:
                        add_edge(gene_id, var_id, "contains")
            # Link gene to disease/condition (skip placeholder texts)
            condition = getattr(mut, 'disease_association', None) or getattr(mut, 'trait_association', None)
            _PLACEHOLDER_CONDITIONS = {'no known disease association', 'not provided', 'not specified', 'under investigation', ''}
            if condition and gene_id and condition.strip().lower() not in _PLACEHOLDER_CONDITIONS:
                cond_id = f"cond:{condition}"
                add_node(cond_id, condition, "condition")
                add_edge(gene_id, cond_id, "associated_with")

    # Build stats
    type_counts = {}
    for n in nodes.values():
        type_counts[n["type"]] = type_counts.get(n["type"], 0) + 1

    return {
        "nodes": list(nodes.values()),
        "edges": edges,
        "stats": {
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "by_type": type_counts,
        },
    }
