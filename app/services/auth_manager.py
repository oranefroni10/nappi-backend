"""Auth operations: signup, signin, register-baby, change-password."""

import logging
from typing import Optional, Tuple
from datetime import date
from app.core.database import get_database
from app.db.models import User, Babies
from sqlalchemy import text

logger = logging.getLogger(__name__)


# Used by: auth.py (POST /auth/signup, /auth/register-baby, /auth/signin, /auth/change-password)
class AuthManager:
    def __init__(self):
        self.database = get_database()

    # Used by: auth.py (POST /auth/signup)
    async def signup(
        self,
        username: str,
        password: str,
        first_name: str,
        last_name: str,
        baby_first_name: Optional[str] = None,
        baby_birthdate: Optional[date] = None,
    ) -> Tuple[User, Optional[Babies], bool]:
        """Register user; optionally match existing baby. Returns (user, baby, baby_was_found). Raises ValueError if username exists."""
        async with self.database.session() as session:
            result = await session.execute(
                text('SELECT id FROM "Nappi"."users" WHERE username = :username'),
                {"username": username}
            )
            if result.first():
                raise ValueError("Username already exists")

            baby_row = None
            if baby_first_name and baby_birthdate:
                baby_result = await session.execute(
                    text('''
                        SELECT id, first_name, last_name, birthdate, gender, created_at
                        FROM "Nappi"."babies"
                        WHERE first_name = :first_name
                        AND last_name = :last_name
                        AND birthdate = :birthdate
                    '''),
                    {
                        "first_name": baby_first_name,
                        "last_name": last_name,
                        "birthdate": baby_birthdate
                    }
                )
                baby_row = baby_result.mappings().first()

            baby_id = baby_row["id"] if baby_row else None

            user_result = await session.execute(
                text('''
                    INSERT INTO "Nappi"."users" (username, password, first_name, last_name, baby_id)
                    VALUES (:username, :password, :first_name, :last_name, :baby_id)
                    RETURNING id, username, password, first_name, last_name, baby_id
                '''),
                {
                    "username": username,
                    "password": password,
                    "first_name": first_name,
                    "last_name": last_name,
                    "baby_id": baby_id
                }
            )
            await session.commit()

            user_row = user_result.mappings().first()
            user = User(**user_row)
            baby = Babies(**baby_row) if baby_row else None

            logger.info(f"User registered: {first_name} {last_name}, baby_found={baby is not None}")
            return user, baby, baby is not None

    # Used by: auth.py (POST /auth/register-baby)
    async def register_baby(
        self,
        user_id: int,
        first_name: str,
        birthdate: date,
        gender: Optional[str] = None,
    ) -> Tuple[User, Babies]:
        """Create baby using user's last_name and link to user. Raises ValueError if user not found."""
        async with self.database.session() as session:
            user_result = await session.execute(
                text('SELECT * FROM "Nappi"."users" WHERE id = :id'),
                {"id": user_id}
            )
            user_row = user_result.mappings().first()
            if not user_row:
                raise ValueError("User not found")

            baby_result = await session.execute(
                text('''
                    INSERT INTO "Nappi"."babies" (first_name, last_name, birthdate, gender)
                    VALUES (:first_name, :last_name, :birthdate, :gender)
                    RETURNING id, first_name, last_name, birthdate, gender, created_at
                '''),
                {
                    "first_name": first_name,
                    "last_name": user_row["last_name"],
                    "birthdate": birthdate,
                    "gender": gender,
                }
            )
            baby_row = baby_result.mappings().first()

            await session.execute(
                text('UPDATE "Nappi"."users" SET baby_id = :baby_id WHERE id = :user_id'),
                {"baby_id": baby_row["id"], "user_id": user_id}
            )
            await session.commit()

            user = User(
                id=user_row["id"],
                username=user_row["username"],
                password=user_row["password"],
                first_name=user_row["first_name"],
                last_name=user_row["last_name"],
                baby_id=baby_row["id"]
            )
            baby = Babies(**baby_row)

            logger.info(f"Baby registered: {first_name} {user_row['last_name']} → user_id={user_id}")
            return user, baby

    # Used by: auth.py (POST /auth/signin)
    async def signin(
        self,
        username: str,
        password: str
    ) -> Tuple[User, Optional[Babies]]:
        """Authenticate user. Returns (user, baby). Raises ValueError if credentials invalid."""
        async with self.database.session() as session:
            result = await session.execute(
                text('''
                    SELECT u.id, u.username, u.password, u.first_name, u.last_name, u.baby_id,
                           b.id as b_id, b.first_name as b_first_name, b.last_name as b_last_name,
                           b.birthdate, b.gender, b.created_at
                    FROM "Nappi"."users" u
                    LEFT JOIN "Nappi"."babies" b ON u.baby_id = b.id
                    WHERE u.username = :username AND u.password = :password
                '''),
                {"username": username, "password": password}
            )
            row = result.mappings().first()

            if not row:
                raise ValueError("Invalid username or password")

            user = User(
                id=row["id"],
                username=row["username"],
                password=row["password"],
                first_name=row["first_name"],
                last_name=row["last_name"],
                baby_id=row["baby_id"]
            )

            baby = None
            if row["b_id"]:
                baby = Babies(
                    id=row["b_id"],
                    first_name=row["b_first_name"],
                    last_name=row["b_last_name"],
                    birthdate=row["birthdate"],
                    gender=row["gender"],
                    created_at=row["created_at"]
                )

            logger.info(f"User signed in: {username}")
            return user, baby

    # Used by: auth.py (POST /auth/change-password)
    async def change_password(
            self,
            user_id: int,
            old_password: str,
            new_password: str,
    ) -> bool:
        """Change user password. Returns False if old password incorrect."""
        async with self.database.session() as session:
            result = await session.execute(
                text('''
                    UPDATE "Nappi"."users"
                    SET password = :new_password
                    WHERE id = :user_id AND password = :old_password
                    RETURNING id
                '''),
                {"user_id": user_id, "old_password": old_password, "new_password": new_password}
            )
            await session.commit()
            updated_user = result.fetchone()
            if updated_user:
                logger.info(f"Password updated for user")
                return True
            logger.warning(f"Failed password update attempt for user_id: {user_id}")
            return False
