"""Quick test for incomplete annotations logic."""
import asyncio
from sqlalchemy import select, func
from backend.db.database import async_session_factory
from backend.db.models import SharedVariantAnnotation
from backend.api.admin_routes import (
    _get_all_enabled_source_names, _get_enabled_source_names, _build_incomplete_condition
)

async def test():
    async with async_session_factory() as db:
        all_en = await _get_all_enabled_source_names(db)
        print('All enabled:', all_en)
        active = await _get_enabled_source_names(db)
        print('Active (>50%):', active)
        cond = _build_incomplete_condition(active)
        if cond is not None:
            r = await db.execute(select(func.count()).select_from(SharedVariantAnnotation).where(cond))
            count = r.scalar()
            print(f'Incomplete count: {count}')
            r2 = await db.execute(select(SharedVariantAnnotation).where(cond).limit(3))
            for a in r2.scalars().all():
                print(f'  {a.rsid}: gnomad={a.gnomad_data is not None}, cvlocal={a.clinvar_local_data is not None}')
        else:
            print('No condition')

asyncio.run(test())
