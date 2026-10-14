-- ==============================================================
-- Trendbit Database Schema for Supabase
-- Run this script in your Supabase Dashboard -> SQL Editor
-- ==============================================================

-- 1. Create table for live site visitors & analytics metrics
CREATE TABLE IF NOT EXISTS public.site_stats (
    key TEXT PRIMARY KEY,
    value BIGINT DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Insert initial visitors counter row if not exists
INSERT INTO public.site_stats (key, value)
VALUES ('total_visitors', 0)
ON CONFLICT (key) DO NOTHING;

-- Enable Row Level Security (RLS) and allow public read access
ALTER TABLE public.site_stats ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow public read access to site_stats"
ON public.site_stats
FOR SELECT
TO public, anon, authenticated
USING (true);

CREATE POLICY "Allow service role full access to site_stats"
ON public.site_stats
FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

-- 2. Verify or create table for iOS apps and bids
CREATE TABLE IF NOT EXISTS public.products (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    app_id TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    website TEXT NOT NULL,
    clean_domain TEXT NOT NULL,
    developer TEXT NOT NULL,
    genre TEXT NOT NULL,
    rating NUMERIC(3, 1) DEFAULT 5.0,
    price TEXT DEFAULT 'Free',
    tagline TEXT,
    description TEXT,
    logo_url TEXT,
    screenshot_url TEXT,
    bid_amount NUMERIC(10, 2) DEFAULT 1.00 CHECK (bid_amount >= 1.00),
    clicks INTEGER DEFAULT 0,
    payment_status TEXT DEFAULT 'pending',
    payment_session_id TEXT,
    customer_email TEXT,
    customer_name TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for instant leaderboard rank sorting
CREATE INDEX IF NOT EXISTS idx_products_bid_rank ON public.products (bid_amount DESC, clicks DESC);
CREATE INDEX IF NOT EXISTS idx_products_payment_status ON public.products (payment_status);

-- Enable RLS for products
ALTER TABLE public.products ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow public read of active products"
ON public.products
FOR SELECT
TO public, anon, authenticated
USING (true);

CREATE POLICY "Allow service role full access to products"
ON public.products
FOR ALL
TO service_role
USING (true)
WITH CHECK (true);
