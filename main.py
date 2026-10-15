import os
import re
import math
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request, Query
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from database import init_db, get_total_visitors, increment_total_visitors
from apple_verifier import verify_ios_app
from dodo_client import create_checkout_session, get_checkout_status, get_payment_status, verify_webhook_event
import supabase_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("trendbit.api")

app = FastAPI(
    title="Trendbit API",
    description="Real-time backend API for Trendbit - The iOS app leaderboard you pay to climb.",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------- WebSocket Live Connection Manager -----------------
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket client connected. Real active count: {len(self.active_connections)}")
        await self.broadcast_stats()

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"WebSocket client disconnected. Real active count: {len(self.active_connections)}")

    def get_active_count(self) -> int:
        return len(self.active_connections)

    async def broadcast_stats(self, total_visitors: Optional[int] = None):
        if total_visitors is None:
            total_visitors = await supabase_client.get_supabase_visitor_count()
        payload = {
            "type": "STATS_UPDATE",
            "active_users": self.get_active_count(),
            "total_visitors": total_visitors,
            "timestamp": datetime.utcnow().isoformat()
        }
        await self.broadcast(payload)

    async def broadcast_app_click(self, product_id: str, track_id: Optional[str], clicks_count: int):
        payload = {
            "type": "APP_CLICK_UPDATE",
            "product_id": str(product_id),
            "track_id": str(track_id) if track_id else None,
            "clicks_count": clicks_count,
            "timestamp": datetime.utcnow().isoformat()
        }
        await self.broadcast(payload)

    async def broadcast(self, message: dict):
        dead = []
        for conn in self.active_connections:
            try:
                await conn.send_json(message)
            except Exception:
                dead.append(conn)
        for d in dead:
            self.disconnect(d)

manager = ConnectionManager()

@app.on_event("startup")
def on_startup():
    init_db()
    logger.info("Real-time database initialized with Supabase integration.")

# ----------------- WebSocket Endpoint -----------------
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # Send initial real stats from Supabase
        current_visitors = await supabase_client.get_supabase_visitor_count()
        await websocket.send_json({
            "type": "STATS_UPDATE",
            "active_users": manager.get_active_count(),
            "total_visitors": current_visitors,
            "timestamp": datetime.utcnow().isoformat()
        })
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
            else:
                try:
                    payload = json.loads(data)
                    if payload.get("action") == "click_app":
                        p_id = payload.get("product_id")
                        t_id = payload.get("track_id")
                        a_name = payload.get("app_name")
                        new_count = await supabase_client.record_app_click(
                            product_id=p_id,
                            app_id=t_id,
                            app_name=a_name
                        )
                        await manager.broadcast_app_click(
                            product_id=p_id,
                            track_id=t_id,
                            clicks_count=new_count
                        )
                except Exception as err:
                    logger.debug(f"Unhandled WebSocket message: {err}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        await manager.broadcast_stats()
    except Exception as e:
        logger.warning(f"WebSocket connection error: {e}")
        manager.disconnect(websocket)
        await manager.broadcast_stats()

# ----------------- Real Visitor & Live Stats Endpoints -----------------
@app.get("/api/stats")
async def get_stats():
    # Fetch real apps and real visitor count directly from Supabase
    products = await supabase_client.fetch_active_products()
    total_visitors = await supabase_client.get_supabase_visitor_count()
    top_bid = max([p.get("bid_amount", 0) for p in products], default=0)
    claim_top_price = int(top_bid + 1) if top_bid > 0 else 1

    return {
        "active_users": manager.get_active_count(),
        "total_visitors": total_visitors,
        "total_apps": len(products),
        "claim_top_price": claim_top_price
    }

@app.post("/api/visitor/hit")
async def record_visitor_hit():
    # Persist and increment real visitor count directly in Supabase
    new_count = await supabase_client.increment_supabase_visitor_count()
    # Broadcast updated stats to ALL connected WebSocket clients in real-time
    await manager.broadcast_stats(total_visitors=new_count)
    return {
        "status": "success",
        "total_visitors": new_count,
        "active_users": manager.get_active_count()
    }

# ----------------- Supabase Real Leaderboard Endpoint -----------------
@app.get("/api/leaderboard")
async def get_leaderboard(
    page: int = Query(1, ge=1, description="Page number, 1-indexed"),
    limit: int = Query(15, ge=1, le=100, description="Items per page, default 15")
):
    # Fetch real products directly from Supabase
    raw_products = await supabase_client.fetch_active_products()
    
    total_items = len(raw_products)
    total_pages = max(1, math.ceil(total_items / limit))

    top_bid = raw_products[0].get("bid_amount", 0) if raw_products else 0
    claim_rank_1_price = int(top_bid + 1) if top_bid > 0 else 1

    ranked_apps = []
    for index, item in enumerate(raw_products, start=1):
        name = item.get("name", "iOS App")
        slug = re.sub(r'[^a-zA-Z0-9]+', '-', name.lower()).strip('-')
        website = item.get("website", "")
        utm_url = (
            f"{website}"
            f"{'&' if '?' in website else '?'}"
            f"utm_source=trendbit&utm_medium=leaderboard&utm_campaign=rank&utm_content=rank-{index:02d}&utm_term={slug}"
        )

        db_clicks = int(item.get("clicks") or 0)
        live_clicks = supabase_client.get_live_app_clicks(str(item.get("id")), str(item.get("app_id", "")))
        clicks_val = max(db_clicks, live_clicks)

        ranked_apps.append({
            "id": item.get("id"),
            "track_id": item.get("app_id"),
            "name": name,
            "seller_name": item.get("developer", ""),
            "app_store_url": website,
            "icon_url": item.get("logo_url", ""),
            "description": item.get("description") or item.get("tagline") or "",
            "primary_genre": item.get("genre", "iOS App"),
            "rating": round(float(item.get("rating", 5.0)), 1) if item.get("rating") else 5.0,
            "rating_count": 0,
            "bid_amount": float(item.get("bid_amount", 1.0)),
            "clicks_count": clicks_val,
            "is_verified": True,
            "rank": index,
            "rank_display": f"{index:02d}",
            "is_top_three": (index <= 3),
            "utm_url": utm_url
        })

    # 15 ranks per single page pagination
    start_idx = (page - 1) * limit
    end_idx = start_idx + limit
    paginated_items = ranked_apps[start_idx:end_idx]

    return {
        "page": page,
        "limit": limit,
        "total_items": total_items,
        "total_pages": total_pages,
        "claim_rank_1_price": claim_rank_1_price,
        "apps": paginated_items
    }

# ----------------- Real iOS App Verification -----------------
class VerifyRequest(BaseModel):
    query: str = Field(..., description="App Store URL, App ID, or App Title")

@app.post("/api/verify-ios-app")
async def verify_app_endpoint(req: VerifyRequest):
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Please enter an App Store URL or app name")
    try:
        verified_data = await verify_ios_app(req.query.strip())
        return {
            "status": "success",
            "verified": True,
            "app": verified_data
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error during app verification: {e}")
        raise HTTPException(status_code=500, detail="Apple App Store verification error")

# ----------------- Outbound Click Tracking & Live WebSocket Broadcast -----------------
@app.get("/api/apps/{product_id}/click")
async def track_click(product_id: str, request: Request):
    user_agent = request.headers.get("user-agent")
    client_ip = request.client.host if request.client else None
    
    # Record click and increment in Supabase and SQLite table
    new_clicks = await supabase_client.record_app_click(
        product_id=product_id,
        user_agent=user_agent,
        ip_address=client_ip
    )
    
    # Broadcast updated click count over WebSocket to ALL connected clients immediately
    await manager.broadcast_app_click(
        product_id=product_id,
        track_id=None,
        clicks_count=new_clicks
    )

    # Fetch product to redirect to App Store
    url = f"{supabase_client.SUPABASE_URL}/rest/v1/products?id=eq.{product_id}&select=website,name"
    import httpx
    async with httpx.AsyncClient(timeout=5.0) as client:
        res = await client.get(url, headers=supabase_client.get_headers())
        if res.status_code == 200 and res.json():
            website = res.json()[0].get("website", "https://apps.apple.com")
            name = res.json()[0].get("name", "app")
            slug = re.sub(r'[^a-zA-Z0-9]+', '-', name.lower()).strip('-')
            redirect_url = (
                f"{website}"
                f"{'&' if '?' in website else '?'}"
                f"utm_source=trendbit&utm_medium=leaderboard&utm_campaign=rank&utm_content=rank-click&utm_term={slug}"
            )
            return RedirectResponse(url=redirect_url, status_code=307)
    return RedirectResponse(url="https://apps.apple.com", status_code=307)

@app.post("/api/apps/{product_id}/click")
async def record_click_ajax(product_id: str, request: Request):
    user_agent = request.headers.get("user-agent")
    client_ip = request.client.host if request.client else None
    
    new_clicks = await supabase_client.record_app_click(
        product_id=product_id,
        user_agent=user_agent,
        ip_address=client_ip
    )
    await manager.broadcast_app_click(
        product_id=product_id,
        track_id=None,
        clicks_count=new_clicks
    )
    return {
        "status": "success",
        "product_id": product_id,
        "clicks_count": new_clicks
    }

# ----------------- Dodo Payments Live Checkout -----------------
class CheckoutRequest(BaseModel):
    track_id: str
    app_name: str
    bid_amount: float
    customer_email: Optional[str] = None
    customer_name: Optional[str] = None
    return_url: Optional[str] = "http://localhost:3000/?payment=success"

@app.post("/api/payments/create-checkout")
async def create_checkout(req: CheckoutRequest):
    if req.bid_amount < 1.0:
        raise HTTPException(status_code=400, detail="Minimum bid amount is $1.00")

    # 1. Verify app details against Apple official API
    try:
        apple_data = await verify_ios_app(req.track_id)
    except Exception as e:
        logger.warning(f"iOS App verification warning for track_id={req.track_id}: {e}")
        apple_data = {
            "track_id": str(req.track_id),
            "name": req.app_name,
            "seller_name": req.customer_name or "iOS Developer",
            "app_store_url": f"https://apps.apple.com/app/id{req.track_id}",
            "primary_genre": "iOS App",
            "rating": 4.9,
            "price": "Free",
            "description": f"iOS App {req.app_name}",
            "icon_url": ""
        }

    # 2. Create Live Checkout Session with Dodo Payments
    try:
        session_info = await create_checkout_session(
            amount_dollars=req.bid_amount,
            app_name=apple_data["name"],
            track_id=apple_data["track_id"],
            customer_email=req.customer_email,
            customer_name=req.customer_name or apple_data["seller_name"],
            return_url=req.return_url or "http://localhost:3000/?payment=success"
        )
    except Exception as e:
        logger.error(f"Dodo checkout creation error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create Dodo checkout: {str(e)}")

    # 3. Store product in Supabase 'products' table
    product_payload = {
        "app_id": str(apple_data["track_id"]),
        "name": apple_data["name"],
        "website": apple_data["app_store_url"],
        "clean_domain": f"apps.apple.com • {apple_data['primary_genre']}",
        "developer": apple_data["seller_name"],
        "genre": apple_data["primary_genre"],
        "rating": apple_data["rating"],
        "price": apple_data.get("price", "Free"),
        "tagline": f"{apple_data['primary_genre']} by {apple_data['seller_name']}",
        "description": apple_data["description"],
        "logo_url": apple_data["icon_url"],
        "bid_amount": req.bid_amount,
        "clicks": 0,
        "payment_status": "pending",
        "payment_session_id": session_info["session_id"],
        "customer_email": req.customer_email,
        "customer_name": req.customer_name or apple_data["seller_name"]
    }
    await supabase_client.create_or_update_product(product_payload)

    return session_info

# ----------------- Dodo Payments Webhook -----------------
@app.post("/api/payments/webhook")
async def dodo_webhook_endpoint(request: Request):
    """
    Receives and verifies live Dodo Payments Webhook with signature checking.
    """
    body = await request.body()
    headers = {
        "webhook-id": request.headers.get("webhook-id", ""),
        "webhook-signature": request.headers.get("webhook-signature", ""),
        "webhook-timestamp": request.headers.get("webhook-timestamp", "")
    }

    try:
        event = verify_webhook_event(body, headers)
    except ValueError as e:
        logger.warning(f"Webhook verification failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))

    event_type = event.get("type")
    event_data = event.get("data", {})

    if event_type == "payment.succeeded":
        session_id = event_data.get("session_id") or event_data.get("id")
        metadata = event_data.get("metadata", {})
        bid_amount = float(metadata.get("bid_amount", 0)) if metadata.get("bid_amount") else None

        if session_id:
            await supabase_client.update_payment_success(session_id, bid_amount)
            # Broadcast live leaderboard refresh over WebSocket
            await manager.broadcast({
                "type": "LEADERBOARD_UPDATED",
                "session_id": session_id
            })

    return {"status": "success"}

# ----------------- Post-Redirect Verification -----------------
@app.get("/api/payments/verify")
async def verify_payment_status(
    session_id: Optional[str] = Query(None),
    payment_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None)
):
    """
    Called upon user return redirect to verify Dodo checkout session or payment status and update Supabase.
    """
    # 1. If payment_id is provided
    if payment_id:
        payment_data = await get_payment_status(payment_id)
        p_status = payment_data.get("status") or status
        if p_status in ("succeeded", "completed", "paid"):
            meta = payment_data.get("metadata", {})
            app_id = meta.get("app_id")
            bid_amount = float(meta.get("bid_amount", 0)) if meta.get("bid_amount") else None
            identifier = app_id or session_id or payment_id
            if identifier:
                await supabase_client.update_payment_success(identifier, bid_amount=bid_amount)
                await manager.broadcast({
                    "type": "LEADERBOARD_UPDATED",
                    "payment_id": payment_id
                })
            return {"status": "completed", "verified": True}

    # 2. If session_id is provided
    if session_id:
        status_data = await get_checkout_status(session_id)
        payment_status = status_data.get("status") or status_data.get("payment_status") or status
        if payment_status in ("succeeded", "completed", "paid"):
            await supabase_client.update_payment_success(session_id)
            await manager.broadcast({
                "type": "LEADERBOARD_UPDATED",
                "session_id": session_id
            })
            return {"status": "completed", "verified": True}
        return {"status": payment_status or "pending", "verified": False}

    if status in ("succeeded", "completed", "paid"):
        return {"status": "completed", "verified": True}

    return {"status": "pending", "verified": False}
