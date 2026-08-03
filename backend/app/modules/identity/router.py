from fastapi import APIRouter
router = APIRouter(prefix="/identity", tags=["identity"])
@router.get("/health")
def health() -> dict[str, str]: return {"module": "identity", "status": "ok"}

