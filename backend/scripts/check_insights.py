"""Check actual insight counts from latest analysis."""
import asyncio
from backend.db.database import async_session_factory
from sqlalchemy import text


async def q():
    async with async_session_factory() as s:
        tables = [
            "health_risks", "drug_responses", "physical_traits", "nutrition_traits",
            "sports_performance", "cognitive_profiles", "personality_traits",
            "ancestry_results", "carrier_status", "wellness_metrics",
            "methylation_profiles", "detoxification_profiles", "rare_mutations", "uncommon_mutations"
        ]
        aid_r = await s.execute(text("SELECT MAX(id) FROM genetic_analyses WHERE analysis_status = 'completed'"))
        aid = aid_r.scalar()
        print(f"Latest completed analysis: {aid}")
        total = 0
        for t in tables:
            r = await s.execute(text(f"SELECT COUNT(*) FROM {t} WHERE analysis_id = {aid}"))
            cnt = r.scalar()
            total += cnt
            print(f"  {t:30s}: {cnt}")
        print(f"  {'TOTAL':30s}: {total}")

        # Sample health risks
        r2 = await s.execute(text(f"SELECT condition, risk_level, risk_score FROM health_risks WHERE analysis_id = {aid} LIMIT 10"))
        print("\nSample health risks:")
        for row in r2.fetchall():
            print(f"  {row[0]:40s} | {row[1]:10s} | {row[2]}")

        # Sample drug responses
        r3 = await s.execute(text(f"SELECT gene, drug, response_type FROM drug_responses WHERE analysis_id = {aid} LIMIT 10"))
        print("\nSample drug responses:")
        for row in r3.fetchall():
            print(f"  {row[0]:15s} | {row[1]:30s} | {row[2]}")

        # Sample carrier status
        r4 = await s.execute(text(f"SELECT condition, carrier_status, inheritance_pattern FROM carrier_status WHERE analysis_id = {aid} LIMIT 10"))
        print("\nSample carrier status:")
        for row in r4.fetchall():
            print(f"  {row[0]:40s} | {row[1]:10s} | {row[2]}")

asyncio.run(q())
