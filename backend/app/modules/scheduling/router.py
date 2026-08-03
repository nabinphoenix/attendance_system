from fastapi import APIRouter
router = APIRouter(prefix="/scheduling", tags=["scheduling"])
@router.get("/health")
def health() -> dict[str, str]: return {"module": "scheduling", "status": "ok"}

