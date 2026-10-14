import re
import urllib.parse
from typing import Optional, Dict, Any, List
import httpx

ITUNES_LOOKUP_URL = "https://itunes.apple.com/lookup"

def is_valid_app_store_url(url: str) -> bool:
    """
    Strict validation to ensure only official Apple App Store URLs are accepted.
    E.g. https://apps.apple.com/us/app/duolingo-learn-languages/id570060128
    """
    if not url:
        return False
    url = url.strip()
    # Must be an http or https URL containing apps.apple.com or itunes.apple.com
    if not re.match(r'^https?://(apps|itunes)\.apple\.com/.*', url, re.IGNORECASE):
        return False
    # Must contain a valid Apple App ID (/id123456789)
    if not re.search(r'id(\d{6,14})', url):
        return False
    return True

def extract_app_id_from_url(url: str) -> Optional[str]:
    """
    Extracts the Apple numeric ID from an official Apple App Store URL.
    """
    url = url.strip()
    match = re.search(r'id(\d{6,14})', url)
    if match:
        return match.group(1)
    return None

async def verify_ios_app(url: str, country: str = "us") -> Dict[str, Any]:
    """
    Verifies that the provided input is a valid Apple App Store URL and fetches official metadata.
    Raises ValueError with 'Invalid URL' message if not an App Store URL.
    """
    url = url.strip()
    if not is_valid_app_store_url(url):
        raise ValueError("Invalid URL. Only official Apple App Store URLs (https://apps.apple.com/...) are allowed.")

    app_id = extract_app_id_from_url(url)
    if not app_id:
        raise ValueError("Invalid URL. App ID could not be found in the App Store URL.")

    headers = {
        "User-Agent": "TrendbitAppVerifier/1.0 (Apple App Store Verification Service)"
    }

    async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
        # Direct lookup on Apple's official iTunes API using numeric App ID
        params = {
            "id": app_id,
            "country": country,
            "entity": "software"
        }
        res = await client.get(ITUNES_LOOKUP_URL, params=params)
        if res.status_code == 200:
            data = res.json()
            if data.get("resultCount", 0) > 0:
                return parse_apple_result(data["results"][0])

    raise ValueError("Could not find this app on the Apple App Store. Please check the URL.")

def parse_apple_result(item: Dict[str, Any]) -> Dict[str, Any]:
    icon_url = (
        item.get("artworkUrl512")
        or item.get("artworkUrl100")
        or item.get("artworkUrl60")
        or ""
    )
    
    desc = item.get("description", "").strip()
    tagline = desc.split("\n")[0] if desc else ""
    if len(tagline) > 120:
        tagline = tagline[:117] + "..."
    if not tagline:
        tagline = f"{item.get('primaryGenreName', 'iOS App')} by {item.get('sellerName', 'App Developer')}"

    return {
        "track_id": str(item.get("trackId")),
        "bundle_id": item.get("bundleId", ""),
        "name": item.get("trackName", ""),
        "seller_name": item.get("sellerName", item.get("artistName", "")),
        "app_store_url": item.get("trackViewUrl", ""),
        "icon_url": icon_url,
        "description": tagline,
        "full_description": desc[:500],
        "primary_genre": item.get("primaryGenreName", "iOS App"),
        "genres": item.get("genres", []),
        "rating": round(float(item.get("averageUserRating", 4.9)), 1),
        "rating_count": int(item.get("userRatingCount", 0)),
        "price": item.get("formattedPrice", "Free"),
        "version": item.get("version", "1.0"),
        "is_verified": True
    }
