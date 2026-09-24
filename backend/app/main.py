from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.modules.platform.router import router as platform_router
from app.modules.academic.router import router as academic_router
from app.modules.attendance.router import router as attendance_router
from app.modules.course_completion.router import router as course_completion_router
from app.modules.crm.router import router as crm_router
from app.modules.identity.router import router as identity_router
from app.modules.operations.router import router as operations_router
from app.modules.scheduling.router import router as scheduling_router
from app.modules.analytics.router import router as analytics_router
from app.modules.academic.guardian_router import router as guardian_router
from app.modules.academic.routine_router import router as routine_router, student_router as student_routine_router
from app.modules.academic.onboarding_router import router as onboarding_router
from app.modules.academic.promotion_router import router as promotion_router
from app.modules.agent.router import router as agent_router
from app.modules.academic.semester_resource_router import router as semester_resource_router
from app.modules.google_workspace.router import router as google_workspace_router

app = FastAPI(title=settings.app_name, version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in (
    platform_router,
    identity_router,
    academic_router,
    scheduling_router,
    attendance_router,
    course_completion_router,
    crm_router,
    operations_router,
    analytics_router,
    guardian_router,
    student_routine_router,
    routine_router,
    onboarding_router,
    promotion_router,
    semester_resource_router,
    google_workspace_router,
    agent_router,
):
    app.include_router(router, prefix="/api/v1")


@app.get("/health", tags=["system"])
def health_check() -> dict[str, str]:
    return {"status": "healthy", "service": settings.app_name}
