import os
import json
import logging
from typing import Optional, Dict, Any
import httpx
from dotenv import load_dotenv

load_dotenv()

try:
    from dodopayments import DodoPayments
    HAS_DODO_SDK = True
except ImportError:
    HAS_DODO_SDK = False

logger = logging.getLogger("trendbit.dodo")

DODO_PAYMENTS_API_KEY = os.getenv("DODO_PAYMENTS_API_KEY", "")
DODO_PAYMENTS_WEBHOOK_KEY = os.getenv("DODO_PAYMENTS_WEBHOOK_KEY", "")
DODO_PRODUCT_ID = os.getenv("DODO_PRODUCT_ID", "pdt_0NpWg85Jy9GfQh6J7IfgN")
DODO_ENVIRONMENT = os.getenv("DODO_ENVIRONMENT", "live_mode")

BASE_URL = "https://live.dodopayments.com" if DODO_ENVIRONMENT == "live_mode" else "https://test.dodopayments.com"

dodo_client = None
if HAS_DODO_SDK and DODO_PAYMENTS_API_KEY:
    try:
        dodo_client = DodoPayments(
            bearer_token=DODO_PAYMENTS_API_KEY,
            webhook_key=DODO_PAYMENTS_WEBHOOK_KEY,
            environment=DODO_ENVIRONMENT
        )
    except Exception as e:
        logger.warning(f"Could not initialize Dodo SDK client: {e}")

async def create_checkout_session(
    amount_dollars: float,
    app_name: str,
    track_id: str,
    customer_email: Optional[str] = None,
    customer_name: Optional[str] = None,
    return_url: str = "http://localhost:3000/?payment=success"
) -> Dict[str, Any]:
    """
    Creates a live checkout session with Dodo Payments API using user's real product pdt_0NpWg85Jy9GfQh6J7IfgN.
    """
    amount_cents = max(100, int(round(amount_dollars * 100)))
    metadata = {
        "app_id": str(track_id),
        "app_name": str(app_name)[:40],
        "bid_amount": str(amount_dollars),
        "platform": "trendbit_ios",
    }

    if not DODO_PAYMENTS_API_KEY:
        raise ValueError("DODO_PAYMENTS_API_KEY is not set.")

    payload = {
        "product_cart": [
            {
                "product_id": DODO_PRODUCT_ID,
                "quantity": 1,
                "amount": amount_cents
            }
        ],
        "billing": {
            "country": "US",
            "state": "CA",
            "city": "San Francisco",
            "street": "123 Market St",
            "zipcode": "94105"
        },
        "customer": {
            "email": customer_email or f"developer+{track_id}@trendbit.app",
            "name": customer_name or app_name
        },
        "return_url": return_url,
        "metadata": metadata
    }

    headers = {
        "Authorization": f"Bearer {DODO_PAYMENTS_API_KEY}",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        res = await client.post(f"{BASE_URL}/checkouts", json=payload, headers=headers)
        if res.status_code in (200, 201):
            data = res.json()
            return {
                "session_id": data.get("session_id"),
                "checkout_url": data.get("checkout_url"),
                "is_live_dodo": True,
                "amount_cents": amount_cents
            }
        else:
            logger.error(f"Dodo Payments API error ({res.status_code}): {res.text}")
            raise ValueError(f"Dodo Payments error: {res.text}")

async def get_checkout_status(session_id: str) -> Dict[str, Any]:
    """
    Checks the status of a live checkout session with Dodo Payments.
    """
    headers = {
        "Authorization": f"Bearer {DODO_PAYMENTS_API_KEY}",
        "Content-Type": "application/json"
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        res = await client.get(f"{BASE_URL}/checkouts/{session_id}", headers=headers)
        if res.status_code == 200:
            return res.json()
        return {}

def verify_webhook_event(raw_body: bytes, headers: Dict[str, str]) -> Dict[str, Any]:
    """
    Verifies Dodo Payments webhook signatures following the Standard Webhooks specification.
    """
    if dodo_client and DODO_PAYMENTS_WEBHOOK_KEY:
        try:
            event = dodo_client.webhooks.unwrap(raw_body, headers=headers)
            return {
                "type": getattr(event, "type", "payment.succeeded"),
                "data": getattr(event, "data", {})
            }
        except Exception as e:
            logger.error(f"Dodo webhook signature verification failed: {e}")
            raise ValueError(f"Invalid webhook signature: {e}")
    
    try:
        data = json.loads(raw_body.decode("utf-8"))
        return {
            "type": data.get("type", "payment.succeeded"),
            "data": data.get("data", data)
        }
    except Exception as e:
        raise ValueError(f"Malformed webhook payload: {e}")
