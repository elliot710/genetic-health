"""Quick script to check per-source NULL counts in shared_variant_annotations."""
import asyncio
from sqlalchemy import text
from backend.db.database import async_session_factory

async def check():
    async with async_session_factory() as db:
        r = await db.execute(text(
            "SELECT COUNT(*) total,"
            " COUNT(*) FILTER (WHERE ensembl_data IS NULL) ensembl_null,"
            " COUNT(*) FILTER (WHERE clinvar_data IS NULL) clinvar_null,"
            " COUNT(*) FILTER (WHERE pharmgkb_data IS NULL) clinpgx_null,"
            " COUNT(*) FILTER (WHERE snpedia_data IS NULL) snpedia_null,"
            " COUNT(*) FILTER (WHERE alpha_missense_data IS NULL) am_null,"
            " COUNT(*) FILTER (WHERE clinvar_local_data IS NULL) cvlocal_null,"
            " COUNT(*) FILTER (WHERE gnomad_data IS NULL) gnomad_null,"
            " COUNT(*) FILTER (WHERE chembl_data IS NULL) chembl_null,"
            " COUNT(*) FILTER (WHERE fda_drug_data IS NULL) fda_null,"
            " COUNT(*) FILTER (WHERE alphafold_data IS NULL) af_null"
            " FROM shared_variant_annotations"
        ))
        row = r.one()
        labels = ['total','ensembl_null','clinvar_null','clinpgx_null','snpedia_null',
                   'am_null','cvlocal_null','gnomad_null','chembl_null','fda_null','af_null']
        for l, v in zip(labels, row):
            print(f'{l}: {v}')

asyncio.run(check())
