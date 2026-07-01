"""Firebase ID-token verification for protected API routes.

The mobile client signs in with Firebase (phone / email / Google / Apple) and
sends the resulting ID token as ``Authorization: Bearer <token>``. Here we verify
that token with the Firebase Admin SDK and expose the caller's uid.

Graceful degradation (mirrors the Mongo pattern): if no Firebase credentials are
configured, auth is treated as *disabled* and protected routes run without a user
— so local dev works out of the box. Set ``AUTH_REQUIRED=1`` to force 401s even
when credentials are absent (use in any shared/staging deploy).
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import Optional

from fastapi import Depends, HTTPException, Request, status

from api.settings import (
    AUTH_REQUIRED,
    FIREBASE_PROJECT_ID,
    FIREBASE_SERVICE_ACCOUNT_JSON,
)

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _init_firebase() -> bool:
    """Initialize the Firebase Admin app once. Returns True if auth is usable."""
    try:
        import firebase_admin
        from firebase_admin import credentials
    except ImportError:
        logger.warning("firebase-admin not installed; auth disabled.")
        return False

    if firebase_admin._apps:  # already initialized
        return True

    try:
        if FIREBASE_SERVICE_ACCOUNT_JSON:
            cred = credentials.Certificate(json.loads(FIREBASE_SERVICE_ACCOUNT_JSON))
            firebase_admin.initialize_app(cred)
        elif FIREBASE_PROJECT_ID:
            # Application Default Credentials (GOOGLE_APPLICATION_CREDENTIALS path
            # or GCP metadata server).
            firebase_admin.initialize_app(options={"projectId": FIREBASE_PROJECT_ID})
        else:
            logger.info("No Firebase credentials configured; auth disabled.")
            return False
        logger.info("Firebase Admin initialized; token verification enabled.")
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Firebase init failed (%s); auth disabled.", exc)
        return False


def auth_enabled() -> bool:
    # Service-account path uses the Admin SDK (needs init). The project-id path
    # uses google-auth's credential-free verifier, which needs no init/creds.
    if FIREBASE_SERVICE_ACCOUNT_JSON:
        return _init_firebase()
    return bool(FIREBASE_PROJECT_ID)


def _bearer_token(request: Request) -> Optional[str]:
    header = request.headers.get("Authorization") or request.headers.get("authorization")
    if not header:
        return None
    parts = header.split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return None


def _verify(token: str) -> dict:
    # Path A: full Admin SDK when a service-account is configured.
    if FIREBASE_SERVICE_ACCOUNT_JSON:
        from firebase_admin import auth as fb_auth

        try:
            return fb_auth.verify_id_token(token, clock_skew_seconds=60)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ID token verification failed (admin): %s", exc)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired authentication token.",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc

    # Path B: credential-free verification against Google's public certs — needs
    # only the project id (no service account / ADC on the box). clock_skew
    # tolerates small EC2<->Google time drift.
    try:
        from google.auth.transport import requests as google_requests
        from google.oauth2 import id_token as google_id_token

        claims = google_id_token.verify_firebase_token(
            token,
            google_requests.Request(),
            audience=FIREBASE_PROJECT_ID,
            clock_skew_in_seconds=60,
        )
        if not claims:
            raise ValueError("token did not verify")
        claims.setdefault("uid", claims.get("user_id") or claims.get("sub"))
        return claims
    except Exception as exc:  # noqa: BLE001
        logger.warning("ID token verification failed (google): %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired authentication token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def optional_user(request: Request) -> Optional[dict]:
    """Decoded token claims if a valid token is present, else None.

    Never raises on a *missing* token — used for routes that work signed-out but
    want to attribute data when signed in. A *present but invalid* token still 401s.
    """
    token = _bearer_token(request)
    if not token:
        return None
    if not auth_enabled():
        return None
    return _verify(token)


def require_user(request: Request) -> dict:
    """Decoded token claims for the authenticated caller. Raises 401 otherwise.

    When Firebase is not configured and ``AUTH_REQUIRED`` is false, returns a
    synthetic anonymous identity so local dev is frictionless.
    """
    token = _bearer_token(request)
    if not auth_enabled():
        if AUTH_REQUIRED:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication is required but not configured on the server.",
            )
        # Dev mode: accept the token's uid if one decodes, else anonymous.
        return {"uid": "dev-anonymous", "anonymous": True}

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _verify(token)


def current_uid(claims: dict = Depends(require_user)) -> str:
    """Convenience dependency yielding just the Firebase uid string."""
    return str(claims.get("uid") or claims.get("user_id") or "")


def require_designer(uid: str = Depends(current_uid)) -> str:
    """Dependency for designer-only routes.

    A uid is a designer iff it has a registered profile in the ``designers``
    table. Raises 403 otherwise. Returns the designer's uid.
    """
    from api.db.designers import DesignerRepository

    if not uid or not DesignerRepository().is_designer(uid):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Designer profile required for this action.",
        )
    return uid
