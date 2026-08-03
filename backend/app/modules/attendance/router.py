from fastapi import APIRouter
router = APIRouter(prefix="/attendance", tags=["attendance"])
@router.get("/health")
def health() -> dict[str, str]: return {"module": "attendance", "status": "ok"}

