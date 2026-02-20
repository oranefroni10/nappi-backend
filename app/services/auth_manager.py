"""Authentication Manager - handles all auth operations"""

import logging
from typing import Optional, Tuple
from datetime import date
from app.core.database import get_database
from app.db.models import User, Babies
from sqlalchemy import text

logger = logging.getLogger(__name__)


class AuthManager:
    """
    Manager class for authentication operations.
    Provides type-safe methods using Pydantic models.
    """

    def __init__(self):
        self.database = get_database()

    async def signup(
        self,
        username: str,
        password: str,
        first_name: str,
        last_name: str,
        baby_first_name: str,
        baby_birthdate: date
    ) -> Tuple[User, Optional[Babies], bool]:
        """
        Register user and check for existing baby.
        Searches for baby using: baby_first_name + user's last_name + baby_birthdate
        Returns: (user, baby, baby_was_found)
        Raises: ValueError if username exists
        """
        async with self.database.session() as session:
            # Check username
            result = await session.execute(
                text('SELECT id FROM "Nappi"."users" WHERE username = :username'),
                {"username": username}
            )
            if result.first():
                raise ValueError("Username already exists")
            
            # Search for baby using baby's first name + user's last name + birthdate
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
            
            # Create user with first_name and last_name
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

    async def register_baby(
        self,
        user_id: int,
        first_name: str,
        birthdate: date,
        gender: Optional[str] = None,
        notes: Optional[str] = None
    ) -> Tuple[User, Babies]:
        """
        Create baby using user's last_name and link to user.
        Returns: (user, baby)
        Raises: ValueError if user not found
        """
        async with self.database.session() as session:
            # Verify user and get their last_name
            user_result = await session.execute(
                text('SELECT * FROM "Nappi"."users" WHERE id = :id'),
                {"id": user_id}
            )
            user_row = user_result.mappings().first()
            if not user_row:
                raise ValueError("User not found")
            
            # Create baby using user's last_name (include notes)
            baby_result = await session.execute(
                text('''
                    INSERT INTO "Nappi"."babies" (first_name, last_name, birthdate, gender, notes)
                    VALUES (:first_name, :last_name, :birthdate, :gender, :notes)
                    RETURNING id, first_name, last_name, birthdate, gender, notes, created_at
                '''),
                {
                    "first_name": first_name,
                    "last_name": user_row["last_name"],
                    "birthdate": birthdate,
                    "gender": gender,
                    "notes": notes
                }
            )
            baby_row = baby_result.mappings().first()
            
            # Link baby to user
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

    async def signin(
        self,
        username: str,
        password: str
    ) -> Tuple[User, Optional[Babies]]:
        """
        Authenticate user.
        Returns: (user, baby)
        Raises: ValueError if credentials invalid
        """
        async with self.database.session() as session:
            result = await session.execute(
                text('''
                    SELECT u.id, u.username, u.password, u.first_name, u.last_name, u.baby_id,
                           b.id as b_id, b.first_name as b_first_name, b.last_name as b_last_name, 
                           b.birthdate, b.gender, b.notes, b.created_at
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
                    notes=row.get("notes"),
                    created_at=row["created_at"]
                )
            
            logger.info(f"User signed in: {username}")
            return user, baby

    async def change_password(
            self,
            user_id: int,
            old_password: str,
            new_password: str,
    ) -> bool:
        """
        Change user password.
        Returns: boolean
        Raises: ValueError if old password incorrect
        """
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
