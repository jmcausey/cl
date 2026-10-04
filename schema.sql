CREATE TABLE IF NOT EXISTS regions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    subdomain TEXT NOT NULL UNIQUE,
    country_code TEXT NOT NULL CHECK (length(country_code) = 2),
    timezone TEXT NOT NULL DEFAULT 'UTC',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_regions_subdomain ON regions(subdomain);

CREATE TABLE IF NOT EXISTS subregions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    region_id INTEGER NOT NULL REFERENCES regions(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    code TEXT NOT NULL,
    UNIQUE (region_id, code)
);

CREATE TABLE IF NOT EXISTS sections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    route_prefix TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    section_id INTEGER NOT NULL REFERENCES sections(id) ON DELETE RESTRICT,
    name TEXT NOT NULL,
    short_code TEXT NOT NULL,
    allows_images INTEGER NOT NULL DEFAULT 1 CHECK (allows_images IN (0, 1)),
    requires_price INTEGER NOT NULL DEFAULT 0 CHECK (requires_price IN (0, 1)),
    UNIQUE (section_id, short_code)
);
CREATE INDEX IF NOT EXISTS idx_categories_short_code ON categories(short_code);

CREATE TABLE IF NOT EXISTS attribute_definitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    key_name TEXT NOT NULL,
    data_type TEXT NOT NULL,
    is_required INTEGER NOT NULL DEFAULT 0 CHECK (is_required IN (0, 1)),
    UNIQUE (category_id, key_name)
);

CREATE TABLE IF NOT EXISTS postings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uuid TEXT NOT NULL UNIQUE,
    region_id INTEGER NOT NULL REFERENCES regions(id) ON DELETE RESTRICT,
    subregion_id INTEGER REFERENCES subregions(id) ON DELETE SET NULL,
    category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE RESTRICT,
    title TEXT NOT NULL CHECK (length(title) <= 255),
    body TEXT NOT NULL,
    price NUMERIC,
    postal_code TEXT,
    latitude REAL,
    longitude REAL,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('draft', 'active', 'flagged', 'expired', 'deleted')),
    attributes TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(attributes)),
    source TEXT NOT NULL DEFAULT 'craigslist',
    external_id TEXT NOT NULL,
    source_url TEXT NOT NULL,
    search_query TEXT,
    price_text TEXT,
    posted_at TEXT,
    review_status TEXT CHECK (review_status IN ('pending', 'completed')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (source, external_id)
);

CREATE TABLE IF NOT EXISTS post_attributes (
    posting_id INTEGER NOT NULL REFERENCES postings(id) ON DELETE CASCADE,
    attribute_id INTEGER NOT NULL REFERENCES attribute_definitions(id) ON DELETE CASCADE,
    value TEXT NOT NULL,
    PRIMARY KEY (posting_id, attribute_id)
);

CREATE TABLE IF NOT EXISTS media (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    posting_id INTEGER NOT NULL REFERENCES postings(id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    display_order INTEGER NOT NULL DEFAULT 0,
    is_primary INTEGER NOT NULL DEFAULT 0 CHECK (is_primary IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (posting_id, url)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_media_primary ON media(posting_id) WHERE is_primary = 1;

CREATE INDEX IF NOT EXISTS idx_postings_feed ON postings(region_id, category_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_postings_subregion ON postings(subregion_id) WHERE subregion_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_postings_geo ON postings(latitude, longitude)
    WHERE latitude IS NOT NULL AND longitude IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_postings_external_id ON postings(source, external_id);

CREATE VIRTUAL TABLE IF NOT EXISTS postings_fts USING fts5(title, body, content='postings', content_rowid='id');
CREATE TRIGGER IF NOT EXISTS trg_postings_fts_insert AFTER INSERT ON postings BEGIN
    INSERT INTO postings_fts(rowid, title, body) VALUES (new.id, new.title, new.body);
END;
CREATE TRIGGER IF NOT EXISTS trg_postings_fts_delete AFTER DELETE ON postings BEGIN
    INSERT INTO postings_fts(postings_fts, rowid, title, body)
    VALUES ('delete', old.id, old.title, old.body);
END;
CREATE TRIGGER IF NOT EXISTS trg_postings_fts_update AFTER UPDATE OF title, body ON postings BEGIN
    INSERT INTO postings_fts(postings_fts, rowid, title, body)
    VALUES ('delete', old.id, old.title, old.body);
    INSERT INTO postings_fts(rowid, title, body) VALUES (new.id, new.title, new.body);
END;
CREATE TRIGGER IF NOT EXISTS trg_postings_updated_at AFTER UPDATE ON postings
WHEN new.updated_at = old.updated_at BEGIN
    UPDATE postings SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = new.id;
END;

CREATE TABLE IF NOT EXISTS craigslist_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_key TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    location TEXT NOT NULL,
    term TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'sss',
    radius INTEGER NOT NULL DEFAULT 0,
    run_times TEXT NOT NULL DEFAULT '06:00',
    enabled INTEGER NOT NULL DEFAULT 1,
    post_to_blog INTEGER NOT NULL DEFAULT 1,
    last_run_at TEXT,
    last_status TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_cl_jobs_enabled ON craigslist_jobs(enabled);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    google_sub TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL UNIQUE,
    name TEXT,
    picture TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS blog_posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_blog_posts_status ON blog_posts(status, updated_at DESC);
