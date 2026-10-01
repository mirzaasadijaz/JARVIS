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

    Assumes Evolution API is configured to send an
    `X-Webhook-Signature: sha256=<hex>` header computed as
    HMAC-SHA256(body, WEBHOOK_SECRET). Adjust the header name/scheme to
    match however your Evolution API version actually signs webhooks —
    confirm this against its docs, since this detail varies by version.
    """
    settings.require("webhook_secret")
    body = await request.body()
    signature_header = request.headers.get("x-webhook-signature", "")

    expected = hmac.new(settings.webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    provided = signature_header.replace("sha256=", "")

    if not hmac.compare_digest(expected, provided):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    return body
