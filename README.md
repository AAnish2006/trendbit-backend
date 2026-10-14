# Trendbit Backend API

Real-time backend API for **Trendbit** — the iOS app leaderboard you pay to climb. Built with FastAPI, WebSockets, Supabase, and Dodo Payments.

## Features
- **Real-time WebSockets (`/ws`)**: Streams live active online users, total visitor counters, and instantaneous app click tracking across connected clients.
- **Apple App Store Verification (`/api/verify-ios-app`)**: Validates Apple App Store URLs using Apple iTunes lookup API.
- **Supabase Real-Time Persistence**: Live synchronization with Supabase `products`, `site_stats`, and `app_clicks` tables.
- **Dodo Payments Checkout (`/api/payments/create-checkout`)**: Creates checkout sessions and processes webhook events to rank apps instantly.
- **Outbound Click Tracking (`/api/apps/{product_id}/click`)**: Tracks outbound clicks with semantic SEO backlinks and Trendbit UTM parameters.

## Tech Stack
- **FastAPI**
- **Uvicorn**
- **WebSockets**
- **HTTPX**
- **Supabase**
- **Dodo Payments SDK**
- **SQLAlchemy & SQLite**

## Setup & Running

1. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure Environment:**
   Copy `.env.example` to `.env` and fill in your keys:
   ```env
   SUPABASE_URL=https://your-project.supabase.co
   SUPABASE_KEY=your-supabase-key
   DODO_PAYMENTS_API_KEY=your-dodo-key
   DODO_PAYMENTS_WEBHOOK_KEY=your-dodo-webhook-key
   DODO_PRODUCT_ID=your-dodo-product-id
   ```

3. **Start Server:**
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8000 --reload
   ```
