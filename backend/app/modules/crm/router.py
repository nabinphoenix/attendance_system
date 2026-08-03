from fastapi import APIRouter
router = APIRouter(prefix="/crm", tags=["crm"])
@router.get("/health")
def health() -> dict[str, str]: return {"module": "crm", "status": "ok"}

