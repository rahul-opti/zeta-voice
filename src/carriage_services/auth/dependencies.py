import secrets
from typing import Literal

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader

from carriage_services.settings import settings

API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


class APIKeyValidator:
    """Validates API keys for different access levels."""

    def __init__(self, key_type: Literal["admin", "user"]):
        """
        Initializes the validator for a specific key type.

        Args:
            key_type: The type of key to validate ('admin' or 'user').
        """
        if key_type == "admin":
            self.required_key = settings.auth.ADMIN_API_KEY
        elif key_type == "user":
            self.required_key = settings.auth.USER_API_KEY
        else:
            raise ValueError("Invalid key_type specified for APIKeyValidator")

    async def __call__(self, api_key: str = Depends(api_key_header)) -> None:
        """
        Dependency function to validate the API key.
        """
        if not self.required_key:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="API key not configured on server.",
            )
        if not api_key or not secrets.compare_digest(api_key, self.required_key):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing API Key.",
            )


admin_api_key_auth = APIKeyValidator(key_type="admin")
user_api_key_auth = APIKeyValidator(key_type="user")
