-- SQL Script to create the app_clicks tracking table in Supabase
-- Run this in your Supabase Dashboard -> SQL Editor

CREATE TABLE IF NOT EXISTS public.app_clicks (
    id BIGSERIAL PRIMARY KEY,
    product_id UUID REFERENCES public.products(id) ON DELETE CASCADE,
    app_id TEXT,
    app_name TEXT,
    user_agent TEXT,
    ip_address TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Enable Row Level Security (RLS)
ALTER TABLE public.app_clicks ENABLE ROW LEVEL SECURITY;

-- Allow public read & insert policies
CREATE POLICY "Allow public read" ON public.app_clicks FOR SELECT USING (true);
CREATE POLICY "Allow public insert" ON public.app_clicks FOR INSERT WITH CHECK (true);
CREATE POLICY "Allow service role all" ON public.app_clicks FOR ALL USING (true);
