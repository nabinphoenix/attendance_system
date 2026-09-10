import os
from sqlalchemy import select
from app.core.database import Base, SessionLocal, engine
from app.core.security import hash_password
from app.modules.academic import models as academic_models
from app.modules.attendance import models as attendance_models
from app.modules.course_completion import models as course_completion_models
from app.modules.crm import models as crm_models
from app.modules.identity.models import User, UserRole
from app.modules.operations import models as operations_models
from app.modules.scheduling import models as scheduling_models
from app.modules.platform.models import College, PlatformConfiguration

ADMIN=("admin@antimbench.example.com","Admin123!")
SUPER_ADMIN_EMAIL = os.getenv("SUPER_ADMIN_EMAIL", "superadmin@antimbench.example.com")
SUPER_ADMIN_PASSWORD = os.getenv("SUPER_ADMIN_PASSWORD")
def ensure_college(db) -> College:
    college = db.scalar(select(College).where(College.slug == "techspire"))
    if college is None:
        college = College(id=1, name="Techspire College", slug="techspire", is_active=True)
        db.add(college)
        db.flush()
    else:
        college.name = "Techspire College"
        college.is_active = True
    if db.get(PlatformConfiguration, 1) is None:
        db.add(PlatformConfiguration(id=1, platform_name="AntimBench", allow_college_creation=True))
    return college

def ensure_super_admin(db) -> User:
    if not SUPER_ADMIN_PASSWORD or len(SUPER_ADMIN_PASSWORD) < 12:
        raise RuntimeError("Set SUPER_ADMIN_PASSWORD to a unique password of at least 12 characters before running the seed")
    user = db.scalar(select(User).where(User.email == SUPER_ADMIN_EMAIL))
    if user is None:
        user = User(name="Platform Super Admin", email=SUPER_ADMIN_EMAIL, password_hash=hash_password(SUPER_ADMIN_PASSWORD), role=UserRole.SUPER_ADMIN, college_id=None)
        db.add(user)
    else:
        user.name = "Platform Super Admin"
        user.role = UserRole.SUPER_ADMIN
        user.college_id = None
        user.password_hash = hash_password(SUPER_ADMIN_PASSWORD)
    db.flush()
    return user
def ensure_admin(db) -> User:
    user = db.scalar(select(User).where(User.email == ADMIN[0]))
    if user is None:
        user = User(name="Administrator", email=ADMIN[0], password_hash=hash_password(ADMIN[1]), role=UserRole.ADMIN)
        db.add(user)
        db.flush()
    else:
        user.name = "Administrator"
        user.role = UserRole.ADMIN
        user.college_id = 1
    return user

def run() -> None:
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        ensure_college(db)
        ensure_admin(db)
        ensure_super_admin(db)
        db.commit()
    print(f"Admin: {ADMIN[0]} / {ADMIN[1]}")
    print(f"Super Admin: {SUPER_ADMIN_EMAIL} (password supplied via SUPER_ADMIN_PASSWORD)")
    print("No academic or attendance sample data was created.")

if __name__=="__main__": run()
