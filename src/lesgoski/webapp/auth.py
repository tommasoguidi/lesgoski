# webapp/auth.py
import random

import bcrypt
from fastapi import Depends, Request
from sqlalchemy.orm import Session

from sqlalchemy import or_

from lesgoski.database.engine import get_db
from lesgoski.database.models import User, BroskiRequest

# Word list for generating ntfy topics
_WORDS = [
    "alpine", "autumn", "blaze", "breeze", "bright", "canyon", "cedar",
    "cliff", "cloud", "coral", "crane", "creek", "crystal", "dawn",
    "delta", "drift", "dusk", "ember", "falcon", "fern", "flint",
    "forest", "frost", "glade", "grove", "harbor", "hawk", "haze",
    "island", "jade", "lark", "lunar", "maple", "marsh", "meadow",
    "mist", "north", "oasis", "ocean", "orbit", "peak", "pine",
    "plain", "pond", "prism", "rain", "reef", "ridge", "river",
    "sage", "shore", "sky", "slate", "snow", "solar", "spark",
    "spray", "stone", "storm", "stream", "summit", "swift", "tide",
    "trail", "vale", "wave", "wild", "wind", "winter", "zenith",
]


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def generate_ntfy_topic() -> str:
    """Generate a random ntfy topic like 'lesgoski-bright-forest-42'."""
    w1 = random.choice(_WORDS)
    w2 = random.choice(_WORDS)
    num = random.randint(10, 99)
    return f"lesgoski-{w1}-{w2}-{num}"


class RedirectToLogin(Exception):
    pass


def get_current_user(request: Request, db: Session = Depends(get_db)):
    """Return the logged-in User or None."""
    user_id = request.session.get("user_id")
    if user_id:
        user = db.get(User, user_id)
        if user:
            return user
    request.session.clear()
    return None


def require_user(request: Request, user: User = Depends(get_current_user)):
    """Raise RedirectToLogin if no user is logged in."""
    if user is None:
        raise RedirectToLogin()
    return user


def get_broskis(db: Session, user: User) -> list[User]:
    """Return list of Users who are mutual friends (accepted broski requests)."""
    accepted = (
        db.query(BroskiRequest)
        .filter(
            BroskiRequest.status == "accepted",
            or_(
                BroskiRequest.from_user_id == user.id,
                BroskiRequest.to_user_id == user.id,
            ),
        )
        .all()
    )
    broskis = []
    for req in accepted:
        other_id = req.to_user_id if req.from_user_id == user.id else req.from_user_id
        other = db.get(User, other_id)
        if other:
            broskis.append(other)
    return broskis


def get_pending_broski_requests(db: Session, user: User) -> list[BroskiRequest]:
    """Return incoming pending broski requests for this user."""
    return (
        db.query(BroskiRequest)
        .filter(
            BroskiRequest.to_user_id == user.id,
            BroskiRequest.status == "pending",
        )
        .all()
    )
