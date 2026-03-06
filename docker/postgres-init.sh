#!/bin/bash
set -e

# Create additional databases
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-EOSQL
    CREATE DATABASE vulcan_scheduler;
EOSQL

# Create social_accounts table (multi-platform: facebook, instagram, tiktok, etc.)
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE TABLE IF NOT EXISTS social_accounts (
        id SERIAL PRIMARY KEY,
        platform VARCHAR(30) NOT NULL,
        email VARCHAR(255) NOT NULL,
        password VARCHAR(255) NOT NULL,
        status VARCHAR(20) DEFAULT 'active',
        last_used TIMESTAMP,
        last_login TIMESTAMP,
        cookies_json TEXT,
        user_agent TEXT,
        fail_count INT DEFAULT 0,
        cooldown_until TIMESTAMP,
        notes TEXT,
        created_at TIMESTAMP DEFAULT NOW(),
        UNIQUE(platform, email)
    );

    CREATE INDEX IF NOT EXISTS idx_social_accounts_platform ON social_accounts(platform);
    CREATE INDEX IF NOT EXISTS idx_social_accounts_status ON social_accounts(platform, status);

    -- Legacy view for backward compatibility
    CREATE OR REPLACE VIEW fb_accounts AS
        SELECT * FROM social_accounts WHERE platform = 'facebook';

    -- Seed initial test account across platforms
    INSERT INTO social_accounts (platform, email, password, notes) VALUES
        ('facebook', 'analytics360@yopmail.com', 'Ultra64#.', 'Cuenta de prueba Analytics 360'),
        ('instagram', 'analytics360@yopmail.com', 'Ultra64#.', 'Cuenta de prueba Analytics 360'),
        ('tiktok', 'analytics360@yopmail.com', 'Ultra64#.', 'Cuenta de prueba Analytics 360')
    ON CONFLICT (platform, email) DO NOTHING;
EOSQL
