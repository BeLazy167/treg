"""Organization-scoped views of resources created with platform credentials."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..domain import provider_resources
from ..domain.identity.access import Caller, require_member
from ..infra.db import get_session


router = APIRouter()


@router.get("/orgs/{org_id}/provider-resources")
async def list_provider_resources(
    org_id: int,
    provider: str = Query(default=""),
    kind: str = Query(default=""),
    include_deleted: bool = Query(default=False),
    caller: Caller = Depends(require_member),
    db: AsyncSession = Depends(get_session),
) -> list[dict]:
    if caller.org_id != org_id:
        raise HTTPException(status_code=403, detail="use this team's credential")
    rows = await provider_resources.list_for_org(
        db, org_id, provider=provider.strip().lower(), resource_kind=kind.strip().lower(),
        include_deleted=include_deleted,
    )
    return [provider_resources.view(row) for row in rows]
