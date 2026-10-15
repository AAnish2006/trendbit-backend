import os
import logging
from typing import List, Dict, Any, Optional
import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("trendbit.supabase")

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

def get_headers() -> Dict[str, str]:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }

async def fetch_active_products() -> List[Dict[str, Any]]:
    """
    Fetches real products from Supabase ordered by bid_amount DESC, clicks DESC.
    Excludes system records.
    """
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []

    url = f"{SUPABASE_URL}/rest/v1/products?payment_status=neq.__system_stats__&select=*&order=bid_amount.desc,clicks.desc,created_at.asc"
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            res = await client.get(url, headers=get_headers())
            if res.status_code == 200:
                return res.json()
            else:
                logger.error(f"Failed to fetch products from Supabase: {res.status_code} {res.text}")
                return []
        except Exception as e:
            logger.error(f"Error connecting to Supabase: {e}")
            return []

async def fetch_product_by_app_id(app_id: str) -> Optional[Dict[str, Any]]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None

    url = f"{SUPABASE_URL}/rest/v1/products?app_id=eq.{app_id}&select=*"
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            res = await client.get(url, headers=get_headers())
            if res.status_code == 200:
                data = res.json()
                return data[0] if data else None
        except Exception as e:
            logger.error(f"Error fetching product by app_id {app_id}: {e}")
    return None

async def create_or_update_product(product_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None

    app_id = product_data.get("app_id")
    existing = await fetch_product_by_app_id(app_id) if app_id else None

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            if existing:
                url = f"{SUPABASE_URL}/rest/v1/products?id=eq.{existing['id']}"
                res = await client.patch(url, headers=get_headers(), json=product_data)
                if res.status_code in (200, 204):
                    data = res.json() if res.text else [product_data]
                    return data[0] if data else product_data
            else:
                url = f"{SUPABASE_URL}/rest/v1/products"
                res = await client.post(url, headers=get_headers(), json=product_data)
                if res.status_code in (200, 201):
                    data = res.json()
                    return data[0] if data else product_data
                else:
                    logger.error(f"Supabase insert failed: {res.status_code} {res.text}")
        except Exception as e:
            logger.error(f"Error creating/updating product in Supabase: {e}")
    return None

async def update_payment_success(identifier: str, bid_amount: Optional[float] = None) -> Optional[Dict[str, Any]]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None

    headers = get_headers()
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            # 1. Match by payment_session_id
            res = await client.get(
                f"{SUPABASE_URL}/rest/v1/products?payment_session_id=eq.{identifier}&select=*",
                headers=headers
            )
            products = res.json() if res.status_code == 200 else []

            # 2. If not found, match by app_id
            if not products:
                res = await client.get(
                    f"{SUPABASE_URL}/rest/v1/products?app_id=eq.{identifier}&select=*",
                    headers=headers
                )
                products = res.json() if res.status_code == 200 else []

            # 3. If not found, match by primary key id
            if not products:
                res = await client.get(
                    f"{SUPABASE_URL}/rest/v1/products?id=eq.{identifier}&select=*",
                    headers=headers
                )
                products = res.json() if res.status_code == 200 else []

            if products:
                product = products[0]
                update_payload = {"payment_status": "completed"}
                if bid_amount and bid_amount > product.get("bid_amount", 0):
                    update_payload["bid_amount"] = bid_amount
                
                patch_url = f"{SUPABASE_URL}/rest/v1/products?id=eq.{product['id']}"
                patch_res = await client.patch(patch_url, headers=headers, json=update_payload)
                if patch_res.status_code in (200, 204):
                    return product
        except Exception as e:
            logger.error(f"Error marking payment completed in Supabase: {e}")
    return None

# In-memory cache + Supabase products table persistence (NO app_clicks logging table)
_in_memory_clicks: Dict[str, int] = {}

def get_live_app_clicks(product_id: str, app_id: Optional[str] = None) -> int:
    pid_count = _in_memory_clicks.get(str(product_id), 0)
    aid_count = _in_memory_clicks.get(str(app_id), 0) if app_id else 0
    return max(pid_count, aid_count)

async def record_app_click(
    product_id: str,
    app_id: Optional[str] = None,
    app_name: Optional[str] = None,
    user_agent: Optional[str] = None,
    ip_address: Optional[str] = None
) -> int:
    """
    Live WebSocket click tracking + products table counter:
    - Increments live in-memory clicks for real-time WebSocket broadcast.
    - Persists counter to Supabase 'products' table.
    - NEVER creates or writes to 'app_clicks' table.
    """
    curr = get_live_app_clicks(product_id, app_id)
    if curr == 0 and SUPABASE_URL and SUPABASE_KEY:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                res = await client.get(
                    f"{SUPABASE_URL}/rest/v1/products?id=eq.{product_id}&select=clicks",
                    headers=get_headers()
                )
                if res.status_code == 200 and res.json():
                    curr = max(curr, int(res.json()[0].get("clicks") or 0))
        except Exception:
            pass

    new_count = curr + 1
    _in_memory_clicks[str(product_id)] = new_count
    if app_id:
        _in_memory_clicks[str(app_id)] = new_count

    # Persist counter directly to Supabase products table (NO app_clicks rows)
    if SUPABASE_URL and SUPABASE_KEY:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.patch(
                    f"{SUPABASE_URL}/rest/v1/products?id=eq.{product_id}",
                    headers=get_headers(),
                    json={"clicks": new_count}
                )
        except Exception as e:
            logger.warning(f"Error persisting product clicks: {e}")

    return new_count

async def increment_clicks(product_id: str) -> int:
    return await record_app_click(product_id=product_id)

# ----------------- Supabase Real Visitor Tracking -----------------
_cached_visitor_count: Optional[int] = None
_has_site_stats_table: Optional[bool] = None

async def init_supabase_visitor_cache() -> int:
    global _cached_visitor_count, _has_site_stats_table
    if not SUPABASE_URL or not SUPABASE_KEY:
        _cached_visitor_count = 0
        return 0

    headers = get_headers()
    async with httpx.AsyncClient(timeout=4.0) as client:
        # Check site_stats table
        if _has_site_stats_table is not False:
            try:
                res = await client.get(
                    f"{SUPABASE_URL}/rest/v1/site_stats?key=eq.total_visitors&select=value",
                    headers=headers
                )
                if res.status_code == 200 and res.json():
                    _has_site_stats_table = True
                    _cached_visitor_count = int(res.json()[0].get("value", 0))
                    return _cached_visitor_count
                elif res.status_code == 404:
                    _has_site_stats_table = False
            except Exception:
                pass

        # Check system record in products table
        try:
            res2 = await client.get(
                f"{SUPABASE_URL}/rest/v1/products?app_id=eq.__trendbit_site_visitors__&select=clicks",
                headers=headers
            )
            if res2.status_code == 200 and res2.json():
                _cached_visitor_count = int(res2.json()[0].get("clicks", 0))
                return _cached_visitor_count
        except Exception:
            pass

    if _cached_visitor_count is None:
        _cached_visitor_count = 0
    return _cached_visitor_count

async def get_supabase_visitor_count() -> int:
    """
    Returns the real visitor count from Supabase.
    """
    global _cached_visitor_count
    if _cached_visitor_count is None:
        return await init_supabase_visitor_cache()
    return _cached_visitor_count

async def _sync_visitor_to_supabase(new_val: int):
    global _has_site_stats_table
    if not SUPABASE_URL or not SUPABASE_KEY:
        return

    headers = get_headers()
    async with httpx.AsyncClient(timeout=5.0) as client:
        # 1. Try site_stats if present
        if _has_site_stats_table:
            try:
                await client.patch(
                    f"{SUPABASE_URL}/rest/v1/site_stats?key=eq.total_visitors",
                    headers=headers,
                    json={"value": new_val}
                )
                return
            except Exception:
                pass

        # 2. Sync to products tracker record
        try:
            res = await client.patch(
                f"{SUPABASE_URL}/rest/v1/products?app_id=eq.__trendbit_site_visitors__",
                headers=headers,
                json={"clicks": new_val}
            )
            if res.status_code not in (200, 204):
                # Insert if missing
                await client.post(
                    f"{SUPABASE_URL}/rest/v1/products",
                    headers=headers,
                    json={
                        "app_id": "__trendbit_site_visitors__",
                        "name": "Trendbit Visitor Stats",
                        "website": "https://trendbit.app",
                        "clean_domain": "trendbit.app",
                        "developer": "System",
                        "genre": "Analytics",
                        "rating": 5.0,
                        "tagline": "Site Visitor Counter",
                        "description": "Persistent visitor counter tracked in Supabase",
                        "logo_url": "https://trendbit.app/logo.png",
                        "payment_status": "__system_stats__",
                        "clicks": new_val,
                        "bid_amount": 1.0
                    }
                )
        except Exception as e:
            logger.error(f"Error syncing visitor count to Supabase: {e}")

async def increment_supabase_visitor_count() -> int:
    """
    Increments and persists the real visitor count directly in Supabase.
    Immediate response with background sync.
    """
    global _cached_visitor_count
    if _cached_visitor_count is None:
        await init_supabase_visitor_cache()

    _cached_visitor_count = (_cached_visitor_count or 0) + 1
    val = _cached_visitor_count

    # Fire and forget background sync to Supabase
    import asyncio
    asyncio.create_task(_sync_visitor_to_supabase(val))
    return val
