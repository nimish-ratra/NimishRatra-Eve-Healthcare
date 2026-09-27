"""
Accounts Domain Services:
Encapsulates user registration, password verification, anti-enumeration authentication,
and JWT token generation.
"""

from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import User
from common.exceptions import AuthenticationError


def register_user(email: str, password: str, is_admin: bool = False) -> User:
    """Creates a new patient account with a normalized email and hashed password."""
    normalized_email = email.strip().lower()
    return User.objects.create_user(
        email=normalized_email,
        password=password,
        is_admin=is_admin,
    )


def authenticate_user(email: str, password: str) -> tuple[User, str, str]:
    """Authenticates user credentials, guarding against account enumeration.
    Returns: (User, access_token, refresh_token)
    Raises: AuthenticationError on bad credentials or inactive account.
    """
    normalized_email = email.strip().lower()
    user = User.objects.filter(email=normalized_email).first()

    # Constant-time-like rejection for unknown email or invalid password
    if user is None or not user.check_password(password):
        raise AuthenticationError("Invalid email or password.")

    if not user.is_active:
        raise AuthenticationError("Account is inactive or disabled.")

    # Generate SimpleJWT tokens
    refresh = RefreshToken.for_user(user)
    access_token = str(refresh.access_token)
    refresh_token = str(refresh)

    return user, access_token, refresh_token
