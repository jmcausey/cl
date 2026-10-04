CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

DO $$
BEGIN
    CREATE TYPE posting_status AS ENUM ('draft', 'active', 'flagged', 'expired', 'deleted');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END
$$;

CREATE TABLE IF NOT EXISTS regions (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    subdomain VARCHAR(63) NOT NULL UNIQUE,
    country_code VARCHAR(2) NOT NULL,
    timezone VARCHAR(50) NOT NULL DEFAULT 'UTC',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_regions_subdomain ON regions(subdomain);

CREATE TABLE IF NOT EXISTS subregions (
    id SERIAL PRIMARY KEY,
    region_id INT NOT NULL REFERENCES regions(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    code VARCHAR(20) NOT NULL,
    CONSTRAINT uq_region_subregion UNIQUE (region_id, code)
);

CREATE TABLE IF NOT EXISTS sections (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    route_prefix VARCHAR(10) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS categories (
    id SERIAL PRIMARY KEY,
    section_id INT NOT NULL REFERENCES sections(id) ON DELETE RESTRICT,
    name VARCHAR(100) NOT NULL,
    short_code VARCHAR(10) NOT NULL,
    allows_images BOOLEAN NOT NULL DEFAULT TRUE,
    requires_price BOOLEAN NOT NULL DEFAULT FALSE,
    CONSTRAINT uq_section_shortcode UNIQUE (section_id, short_code)
);
CREATE INDEX IF NOT EXISTS idx_categories_short_code ON categories(short_code);

CREATE TABLE IF NOT EXISTS attribute_definitions (
    id SERIAL PRIMARY KEY,
    category_id INT NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    key_name VARCHAR(50) NOT NULL,
    data_type VARCHAR(20) NOT NULL,
    is_required BOOLEAN NOT NULL DEFAULT FALSE,
    CONSTRAINT uq_category_key UNIQUE (category_id, key_name)
);

CREATE TABLE IF NOT EXISTS postings (
    id BIGSERIAL PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT uuid_generate_v4() UNIQUE,
    region_id INT NOT NULL REFERENCES regions(id) ON DELETE RESTRICT,
    subregion_id INT REFERENCES subregions(id) ON DELETE SET NULL,
    category_id INT NOT NULL REFERENCES categories(id) ON DELETE RESTRICT,
    title VARCHAR(255) NOT NULL,
    body TEXT NOT NULL,
    price NUMERIC(12, 2),
    postal_code VARCHAR(20),
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    status posting_status NOT NULL DEFAULT 'active',
    attributes JSONB NOT NULL DEFAULT '{}'::jsonb,
    source VARCHAR(40) NOT NULL DEFAULT 'craigslist',
    external_id TEXT NOT NULL,
    source_url TEXT NOT NULL,
    search_query TEXT,
    price_text TEXT,
    posted_at TIMESTAMPTZ,
    review_status VARCHAR(20) CHECK (review_status IN ('pending', 'completed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_posting_source_external UNIQUE (source, external_id)
);

CREATE TABLE IF NOT EXISTS post_attributes (
    posting_id BIGINT NOT NULL REFERENCES postings(id) ON DELETE CASCADE,
    attribute_id INT NOT NULL REFERENCES attribute_definitions(id) ON DELETE CASCADE,
    value TEXT NOT NULL,
    PRIMARY KEY (posting_id, attribute_id)
);

CREATE TABLE IF NOT EXISTS media (
    id BIGSERIAL PRIMARY KEY,
    posting_id BIGINT NOT NULL REFERENCES postings(id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    display_order INT NOT NULL DEFAULT 0,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (posting_id, url)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_media_primary ON media(posting_id) WHERE is_primary;

CREATE INDEX IF NOT EXISTS idx_postings_feed ON postings(region_id, category_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_postings_subregion ON postings(subregion_id) WHERE subregion_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_postings_geo ON postings(latitude, longitude)
    WHERE latitude IS NOT NULL AND longitude IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_postings_attributes_gin ON postings USING GIN (attributes);
CREATE INDEX IF NOT EXISTS idx_postings_fts ON postings USING GIN (to_tsvector('english', title || ' ' || body));
CREATE INDEX IF NOT EXISTS idx_postings_external_id ON postings(source, external_id);

CREATE OR REPLACE FUNCTION update_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_postings_updated_at ON postings;
CREATE TRIGGER trg_postings_updated_at
    BEFORE UPDATE ON postings
    FOR EACH ROW
    EXECUTE FUNCTION update_timestamp();

CREATE TABLE IF NOT EXISTS craigslist_jobs (
    id BIGSERIAL PRIMARY KEY,
    job_key TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    location TEXT NOT NULL,
    term TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'sss',
    radius INTEGER NOT NULL DEFAULT 0,
    run_times TEXT NOT NULL DEFAULT '06:00',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    post_to_blog BOOLEAN NOT NULL DEFAULT TRUE,
    last_run_at TIMESTAMPTZ,
    last_status TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_cl_jobs_enabled ON craigslist_jobs(enabled);

CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    google_sub TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL UNIQUE,
    name TEXT,
    picture TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS blog_posts (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_blog_posts_status ON blog_posts(status, updated_at DESC);
