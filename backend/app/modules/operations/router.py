from fastapi import APIRouter
router = APIRouter(prefix="/operations", tags=["operations"])
@router.get("/health")
def health() -> dict[str, str]: return {"module": "operations", "status": "ok"}

