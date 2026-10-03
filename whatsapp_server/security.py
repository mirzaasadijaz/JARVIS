"""Webhook signature verification + slowapi rate limiting.

Guards the one thing in this whole project that's exposed to the public
internet — see the Middleware section of the Tech Stack Guide.
"""

import hashlib
import hmac

from fastapi import HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from config import settings

limiter = Limiter(key_func=get_remote_address)


async def verify_webhook_signature(request: Request) -> bytes:
    """FastAPI dependency — reject any request missing a valid signature.

    The WhatsApp bridge (whatsapp_bridge/server.js) sends an
    `X-Webhook-Signature: sha256=<hex>` header computed as
    HMAC-SHA256(body, WEBHOOK_SECRET); WEBHOOK_SECRET must be the same value
    in this project's .env and in the bridge's environment.
    """
    settings.require("webhook_secret")
    body = await request.body()
    signature_header = request.headers.get("x-webhook-signature", "")

    expected = hmac.new(settings.webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    provided = signature_header.replace("sha256=", "")

    # Compare as bytes: comparing str raises TypeError (-> HTTP 500 instead of 401)
    # if the header contains a non-ASCII character.
    if not hmac.compare_digest(expected.encode(), provided.encode()):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    return body
