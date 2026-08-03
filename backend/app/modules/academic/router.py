from fastapi import APIRouter
router = APIRouter(prefix="/academic", tags=["academic"])
@router.get("/health")
def health() -> dict[str, str]: return {"module": "academic", "status": "ok"}

