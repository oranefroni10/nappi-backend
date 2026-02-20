-- Migration: Create alerts table
-- Run this SQL in your PostgreSQL database to create the alerts table

CREATE TABLE IF NOT EXISTS "Nappi"."alerts" (
    id SERIAL PRIMARY KEY,
    baby_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    type VARCHAR(50) NOT NULL,  -- 'awakening', 'temperature', 'humidity', 'noise'
    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    severity VARCHAR(20) DEFAULT 'info',  -- 'info', 'warning', 'critical'
    metadata JSONB,
    read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Create index for faster queries by user and read status
CREATE INDEX IF NOT EXISTS idx_alerts_user_id ON "Nappi"."alerts" (user_id);
CREATE INDEX IF NOT EXISTS idx_alerts_baby_id ON "Nappi"."alerts" (baby_id);
CREATE INDEX IF NOT EXISTS idx_alerts_read ON "Nappi"."alerts" (read);
CREATE INDEX IF NOT EXISTS idx_alerts_created_at ON "Nappi"."alerts" (created_at DESC);

-- Create push_subscriptions table for Web Push notifications
CREATE TABLE IF NOT EXISTS "Nappi"."push_subscriptions" (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL UNIQUE,
    endpoint TEXT NOT NULL,
    p256dh_key TEXT NOT NULL,
    auth_key TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_push_subscriptions_user_id ON "Nappi"."push_subscriptions" (user_id);
