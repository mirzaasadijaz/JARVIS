"""@tool post_to_instagram, post_to_facebook_page — Meta Graph API.

Plain REST calls to Meta's documented endpoints — not verifiable here
without a real app + page + Instagram Business account, so confirm the
exact API version (v21.0 below) is still current when you wire this up;
Meta bumps these periodically.
"""

import requests
from langchain_core.tools import tool

from config import settings

GRAPH_API_VERSION = "v21.0"
BASE_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}"


@tool
def post_to_instagram(caption: str, image_url: str) -> str:
    """Post an image to Instagram.

    Args:
        caption: The post caption
        image_url: A publicly reachable URL to the image (Instagram's
            API fetches it directly — it can't be a local file path)
    """
    settings.require("meta_page_access_token", "instagram_business_account_id")
    token = settings.meta_page_access_token
    ig_id = settings.instagram_business_account_id

    # Step 1: create a media container
    container = requests.post(
        f"{BASE_URL}/{ig_id}/media",
        data={"image_url": image_url, "caption": caption, "access_token": token},
        timeout=30,
    )
    container.raise_for_status()
    creation_id = container.json()["id"]

    # Step 2: publish it
    publish = requests.post(
        f"{BASE_URL}/{ig_id}/media_publish",
        data={"creation_id": creation_id, "access_token": token},
        timeout=30,
    )
    publish.raise_for_status()
    return f"Posted to Instagram: {publish.json()}"


@tool
def post_to_facebook_page(message: str) -> str:
    """Post a text update to the linked Facebook Page.

    Args:
        message: The post text
    """
    settings.require("meta_page_access_token")
    token = settings.meta_page_access_token

    response = requests.post(
        f"{BASE_URL}/me/feed",
        data={"message": message, "access_token": token},
        timeout=30,
    )
    response.raise_for_status()
    return f"Posted to Facebook Page: {response.json()}"
