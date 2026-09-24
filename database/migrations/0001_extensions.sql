-- 0001: PostGIS (supported natively by Neon PostgreSQL).
CREATE EXTENSION IF NOT EXISTS postgis;

-- Shared trigger function maintaining updated_at columns.
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;
