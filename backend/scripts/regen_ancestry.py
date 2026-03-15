"""One-off script to regenerate ancestry results for analysis 69 using gnomAD data."""
import asyncio
import math
import json
import sys
sys.path.insert(0, '/app')

from backend.db.database import async_session_factory
from sqlalchemy import text

POP_CODES = ['afr', 'amr', 'eas', 'eur', 'sas']
POP_LABELS = {
    'afr': 'African', 'amr': 'Admixed American', 'eas': 'East Asian',
    'eur': 'European', 'sas': 'South Asian',
}
POP_ORIGINS = {
    'afr': 'Sub-Saharan Africa', 'amr': 'The Americas',
    'eas': 'East & Southeast Asia', 'eur': 'Europe & Western Asia',
    'sas': 'South & Central Asia',
}
GNOMAD_POP_MAP = {
    'afr': 'afr', 'amr': 'amr', 'eas': 'eas',
    'nfe': 'eur', 'fin': 'eur', 'sas': 'sas',
}
NEANDERTHAL_RSIDS = {
    'rs2066827', 'rs10166942', 'rs2298813', 'rs4792887', 'rs1534696',
    'rs3917862', 'rs10490770', 'rs2664280', 'rs12477142', 'rs11209026',
    'rs1800407', 'rs7214986', 'rs2066807', 'rs4988235', 'rs12913832',
    'rs1426654', 'rs16891982', 'rs1805007', 'rs1805008', 'rs6152',
}
FLOOR = 0.001
ANALYSIS_ID = 69


async def regenerate():
    async with async_session_factory() as s:
        # Get all user variant rsids
        r = await s.execute(text(
            "SELECT gm.rsid FROM analysis_variants av "
            "JOIN genetic_markers gm ON gm.id = av.marker_id "
            "WHERE av.analysis_id = :aid AND gm.rsid IS NOT NULL"
        ), {"aid": ANALYSIS_ID})
        user_rsids = {row[0] for row in r.fetchall()}
        print(f"User has {len(user_rsids)} variants with rsids")

        # Get gnomAD pop freq data
        r2 = await s.execute(text(
            "SELECT rsid, gnomad_data FROM shared_variant_annotations "
            "WHERE rsid = ANY(:rsids) AND gnomad_data IS NOT NULL "
            "AND gnomad_data::text LIKE :pat"
        ), {"rsids": list(user_rsids), "pat": "%population_frequencies%"})
        rows = r2.fetchall()
        print(f"Found {len(rows)} variants with gnomAD pop freq data")

        pop_weight_sums = {p: 0.0 for p in POP_CODES}
        informative_count = 0
        contributing_rsids = {p: [] for p in POP_CODES}

        for rsid, gnomad_data in rows:
            if not isinstance(gnomad_data, dict) or not gnomad_data.get("found"):
                continue
            pop_freqs = gnomad_data.get("population_frequencies", {})
            if not pop_freqs:
                continue

            afs = {}
            for gnomad_code, canonical in GNOMAD_POP_MAP.items():
                pf = pop_freqs.get(gnomad_code, {})
                af = pf.get("af") if isinstance(pf, dict) else None
                if af is not None and 0 <= af <= 1:
                    if canonical in afs:
                        afs[canonical] = (afs[canonical] + af) / 2
                    else:
                        afs[canonical] = af

            if len(afs) < 2:
                continue
            af_vals = list(afs.values())
            if min(af_vals) > 0.95:
                continue
            if max(af_vals) < 0.01:
                continue
            if max(af_vals) - min(af_vals) < 0.03:
                continue

            informative_count += 1

            clamped = {p: max(afs.get(p, FLOOR), FLOOR) for p in POP_CODES}
            total_af = sum(clamped.values())
            for pc in POP_CODES:
                w = clamped[pc] / total_af
                pop_weight_sums[pc] += w
                if afs.get(pc, 0) > 0.3:
                    contributing_rsids[pc].append(rsid)

        print(f"Informative variants: {informative_count}")
        if informative_count < 5:
            print("NOT ENOUGH DATA — aborting")
            return

        total_weight = sum(pop_weight_sums.values()) or 1.0
        percentages = {p: round((pop_weight_sums[p] / total_weight) * 100, 1) for p in POP_CODES}
        print(f"Percentages: {percentages}")

        dominant_pop = max(percentages, key=lambda p: percentages[p])
        confidence = "high" if percentages[dominant_pop] > 60 else "moderate" if percentages[dominant_pop] > 35 else "low"

        composition = sorted(
            [{"region": POP_LABELS[p], "percentage": percentages[p]} for p in POP_CODES if percentages[p] >= 1.0],
            key=lambda x: x["percentage"], reverse=True,
        )
        print(f"Composition: {json.dumps(composition, indent=2)}")

        neanderthal_hits = user_rsids & NEANDERTHAL_RSIDS
        neanderthal_pct = round(len(neanderthal_hits) / max(len(NEANDERTHAL_RSIDS), 1) * 3.5, 1)
        neanderthal_pct = min(neanderthal_pct, 4.0)
        neanderthal_data = {
            "percentage": neanderthal_pct,
            "variants": len(neanderthal_hits),
            "moreOrLess": "more" if neanderthal_pct > 2.0 else "less" if neanderthal_pct < 1.5 else "about average",
            "comparison": f"than the average of ~2% for non-African populations ({informative_count} variants analyzed)",
        }
        print(f"Neanderthal: {json.dumps(neanderthal_data)}")

        # Delete old + insert new
        await s.execute(text("DELETE FROM ancestry_results WHERE analysis_id = :aid"), {"aid": ANALYSIS_ID})
        await s.execute(text(
            "INSERT INTO ancestry_results "
            "(analysis_id, population, percentage, confidence, geographic_origin, associated_variants, composition, neanderthal_variants) "
            "VALUES (:aid, :pop, :pct, :conf, :geo, CAST(:assoc AS json), CAST(:comp AS json), CAST(:nean AS json))"
        ), {
            "aid": ANALYSIS_ID,
            "pop": POP_LABELS[dominant_pop],
            "pct": str(percentages[dominant_pop]),
            "conf": confidence,
            "geo": POP_ORIGINS[dominant_pop],
            "assoc": json.dumps(contributing_rsids.get(dominant_pop, [])[:20]),
            "comp": json.dumps(composition),
            "nean": json.dumps(neanderthal_data),
        })
        await s.commit()
        print("DONE - ancestry regenerated!")


asyncio.run(regenerate())
