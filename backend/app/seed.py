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

ADMIN=("admin@antimbench.example.com","Admin123!")
def ensure_admin(db) -> User:
    user = db.scalar(select(User).where(User.email == ADMIN[0]))
    if user is None:
        user = User(name="Administrator", email=ADMIN[0], password_hash=hash_password(ADMIN[1]), role=UserRole.ADMIN)
        db.add(user)
        db.flush()
    else:
        user.name = "Administrator"
        user.role = UserRole.ADMIN
    return user

def run() -> None:
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        ensure_admin(db)
        db.commit()
    print(f"Admin: {ADMIN[0]} / {ADMIN[1]}")
    print("No academic or attendance sample data was created.")

if __name__=="__main__": run()
