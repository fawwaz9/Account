from app._database.db import SessionLocal
from app._database.models import UserModel, CourseModel

db = SessionLocal()

print("=== USERS ===")
users = db.query(UserModel).all()
for u in users:
    print(f"{u.id} | {u.name} | {u.email} | {len(u.courses)} course(s)")

print("\n=== COURSES ===")
courses = db.query(CourseModel).all()
for c in courses:
    total = sum(cw.weight for cw in c.category_weight_rows)
    flag = " <-- INVALID (sum > 100)" if total > 100 else ""
    print(f"{c.id} | {c.code} | user_id={c.user_id} | total_weight={total}{flag}")
    for cw in c.category_weight_rows:
        print(f"    {cw.category}: {cw.weight}")

db.close()