import os
import jwt

from fastapi import HTTPException, status
from dotenv import load_dotenv


# ============================================================
# LOAD ENVIRONMENT VARIABLES
# ============================================================

load_dotenv()


# ============================================================
# JWT CONFIGURATION
# ============================================================

JWT_ALGORITHM = os.getenv("JWT_ALGORITHM")
JWT_ISSUER = os.getenv("JWT_ISSUER")
JWT_AUDIENCE = os.getenv("JWT_AUDIENCE")

JWT_PUBLIC_KEY = os.getenv("JWT_PUBLIC_KEY")

if JWT_PUBLIC_KEY:
    JWT_PUBLIC_KEY = JWT_PUBLIC_KEY.replace("\\n", "\n")


# ============================================================
# VALIDATE JWT TOKEN
# ============================================================

def validate_jwt_token(token: str):
    try:
        payload = jwt.decode(
            token,
            JWT_PUBLIC_KEY,
            algorithms=[JWT_ALGORITHM],
            issuer=JWT_ISSUER,
            audience=JWT_AUDIENCE,
        )

        return payload

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token has expired",
        )

    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token",
        )