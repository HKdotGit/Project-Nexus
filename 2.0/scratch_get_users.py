from database import get_db
from models import User

db = next(get_db())
users = db.query(User).all()
for u in users:
    print(f"User: {u.id}, {u.username}")
