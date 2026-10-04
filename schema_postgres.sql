CREATE TABLE IF NOT EXISTS craigslist_postings (
    id BIGSERIAL PRIMARY KEY,
    craigslist_id TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    price_text TEXT,
    price_amount DOUBLE PRECISION,
    location TEXT,
    listing_url TEXT NOT NULL,
    category TEXT,
    search_query TEXT,
    posted_at TIMESTAMP,
    scraped_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    image_url TEXT,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'published'
);
CREATE INDEX IF NOT EXISTS idx_cl_postings_posted ON craigslist_postings (posted_at DESC);

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
    last_run_at TIMESTAMP,
    last_status TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_cl_jobs_enabled ON craigslist_jobs (enabled);

CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    google_sub TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL UNIQUE,
    name TEXT,
    picture TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS blog_posts (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_blog_posts_status ON blog_posts (status, updated_at DESC);
