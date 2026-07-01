"""Push notifications via Firebase Cloud Messaging (FCM).

Sending FCM requires *real* service-account credentials for the Firebase
project — unlike token verification, the credential-free project-id path cannot
send. Provide credentials one of two ways (see api/settings):
  - ``FIREBASE_SERVICE_ACCOUNT_JSON`` — the service-account JSON, inline, or
  - ``GOOGLE_APPLICATION_CREDENTIALS`` — path to that JSON (Application Default).

If no credentials are configured this module degrades to a no-op (logs a warning
once) so callers — which fire push best-effort — never fail because of it.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import Any

from api.settings import FIREBASE_PROJECT_ID, FIREBASE_SERVICE_ACCOUNT_JSON

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _messaging():
    """Return the firebase_admin.messaging module with an initialized app, or None."""
    try:
        import firebase_admin
        from firebase_admin import credentials, messaging
    except ImportError:
        logger.warning("firebase-admin not installed; push notifications disabled.")
        return None

    try:
        if not firebase_admin._apps:
            if FIREBASE_SERVICE_ACCOUNT_JSON:
                cred = credentials.Certificate(json.loads(FIREBASE_SERVICE_ACCOUNT_JSON))
                firebase_admin.initialize_app(cred)
            else:
                # Application Default Credentials (GOOGLE_APPLICATION_CREDENTIALS).
                # initialize_app() with no arg picks these up; needs a real key.
                opts = {"projectId": FIREBASE_PROJECT_ID} if FIREBASE_PROJECT_ID else None
                firebase_admin.initialize_app(options=opts)
        return messaging
    except Exception as exc:  # noqa: BLE001
        logger.warning("FCM init failed (%s); push notifications disabled.", exc)
        return None


def push_available() -> bool:
    return _messaging() is not None


def send_to_uid(uid: str, *, title: str, body: str, data: dict[str, Any] | None = None) -> int:
    """Send a push to every device registered for ``uid``.

    Best-effort: returns the count delivered. Prunes tokens FCM reports as
    unregistered. Never raises — push is non-critical to the request flow.
    """
    messaging = _messaging()
    if messaging is None or not uid:
        return 0

    # Imported here to avoid a circular import (db.users has no push dependency).
    from api.db.users import UserRepository

    repo = UserRepository()
    tokens = repo.get_fcm_tokens(uid)
    if not tokens:
        return 0

    # All push data values must be strings.
    str_data = {k: str(v) for k, v in (data or {}).items()}

    sent = 0
    stale: list[str] = []
    for token in tokens:
        try:
            messaging.send(
                messaging.Message(
                    token=token,
                    notification=messaging.Notification(title=title, body=body),
                    data=str_data,
                    android=messaging.AndroidConfig(priority="high"),
                    apns=messaging.APNSConfig(
                        payload=messaging.APNSPayload(
                            aps=messaging.Aps(sound="default")
                        )
                    ),
                )
            )
            sent += 1
        except Exception as exc:  # noqa: BLE001
            name = type(exc).__name__
            if "Unregistered" in name or "InvalidArgument" in name or "NotFound" in name:
                stale.append(token)
            logger.warning("FCM send failed for one token (%s): %s", name, exc)

    if stale:
        repo.remove_fcm_tokens(uid, stale)
    return sent
