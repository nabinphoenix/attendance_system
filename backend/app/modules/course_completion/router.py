from fastapi import APIRouter
router = APIRouter(prefix="/course-completion", tags=["course completion"])
@router.get("/health")
def health() -> dict[str, str]: return {"module": "course_completion", "status": "ok"}

