import sqlite3

from cl import create_app, get_db, init_db


def test_blog_admin_route_exists():
    app = create_app({'TESTING': True})
    routes = {rule.rule for rule in app.url_map.iter_rules()}
    assert '/blog/admin' in routes


def test_admin_can_update_other_users_blog_status(tmp_path):
    db_path = tmp_path / 'test_blog_admin.sqlite'
    app = create_app({
        'TESTING': True,
        'DATABASE': str(db_path),
        'BLOG_ALLOWED_EMAILS': 'admin@example.com',
    })

    with app.app_context():
        init_db()
        db = get_db()
        db.execute("INSERT INTO users (google_sub, email, name) VALUES (?, ?, ?)", ('owner-1', 'owner@example.com', 'Owner'))
        db.execute("INSERT INTO users (google_sub, email, name) VALUES (?, ?, ?)", ('admin-1', 'admin@example.com', 'Admin'))
        db.execute("INSERT INTO blog_posts (user_id, title, body, status) VALUES (?, ?, ?, ?)", (1, 'Needs review', 'Body', 'pending'))
        db.commit()

    client = app.test_client()
    with client.session_transaction() as sess:
        sess['user_id'] = 2

    response = client.post('/blog/1/status', data={'action': 'completed'})

    assert response.status_code == 302
    with app.app_context():
        row = get_db().execute("SELECT status FROM blog_posts WHERE id = 1").fetchone()
        assert row['status'] == 'completed'


def test_admin_can_update_scraped_listing_status(tmp_path):
    app = create_app({
        'TESTING': True,
        'DATABASE': str(tmp_path / 'test_listing_status.sqlite'),
        'BLOG_ALLOWED_EMAILS': 'admin@example.com',
    })

    with app.app_context():
        init_db()
        db = get_db()
        db.execute(
            "INSERT INTO users (google_sub, email, name) VALUES (?, ?, ?)",
            ('admin-1', 'admin@example.com', 'Admin'),
        )
        db.execute(
            "INSERT INTO craigslist_postings (craigslist_id, title, listing_url) VALUES (?, ?, ?)",
            ('scraped-1', 'Scraped listing', 'https://example.com/listing'),
        )
        db.commit()

    client = app.test_client()
    with client.session_transaction() as sess:
        sess['user_id'] = 1

    response = client.post('/listing/1/status', data={'action': 'completed'})

    assert response.status_code == 302
    with app.app_context():
        row = get_db().execute(
            "SELECT status FROM craigslist_postings WHERE id = 1"
        ).fetchone()
        assert row['status'] == 'completed'


def test_listings_nav_opens_posts_not_account_name(tmp_path):
    app = create_app({
        'TESTING': True,
        'DATABASE': str(tmp_path / 'test_nav.sqlite'),
        'BLOG_ALLOWED_EMAILS': 'admin@example.com',
    })

    with app.app_context():
        init_db()
        get_db().execute(
            "INSERT INTO users (google_sub, email, name) VALUES (?, ?, ?)",
            ('admin-1', 'admin@example.com', 'Admin Name'),
        )
        get_db().execute(
            "INSERT INTO blog_posts (user_id, title, body) VALUES (?, ?, ?)",
            (1, 'Blog listing', 'Blog body'),
        )
        get_db().execute(
            "INSERT INTO craigslist_postings (craigslist_id, title, listing_url) VALUES (?, ?, ?)",
            ('scraped-1', 'Scraped listing', 'https://example.com/listing'),
        )
        get_db().commit()

    client = app.test_client()
    with client.session_transaction() as sess:
        sess['user_id'] = 1
        sess['user_name'] = 'Admin Name'

    response = client.get('/blog')
    html = response.get_data(as_text=True)

    assert '<a href="/blog">Listings</a>' in html
    assert 'Craigslist Results' not in html
    assert '<span>Admin Name</span>' in html
    assert '<a href="/auth/logout">Log out</a>' in html
    assert 'Blog listing' in html
    assert 'Scraped listing' in html
    assert 'action="/listing/1/status"' in html


def test_control_persists_post_to_blog_preference(tmp_path):
    app = create_app({
        'TESTING': True,
        'DATABASE': str(tmp_path / 'test_post_to_blog.sqlite'),
    })
    with app.app_context():
        init_db()

    client = app.test_client()
    common = {
        'location': 'https://austin.craigslist.org',
        'term': 'boat',
        'category': 'boa',
        'radius': '0',
        'run_times': '',
    }
    client.post('/control', data={**common, 'name': 'Private search'})
    client.post('/control', data={
        **common,
        'name': 'Public search',
        'post_to_blog': 'on',
    })

    with app.app_context():
        rows = get_db().execute(
            'SELECT name, post_to_blog FROM craigslist_jobs ORDER BY name'
        ).fetchall()
    assert {row['name']: bool(row['post_to_blog']) for row in rows} == {
        'Private search': False,
        'Public search': True,
    }
    html = client.get('/control').get_data(as_text=True)
    assert 'name="post_to_blog" checked' in html
    assert '<td>No</td>' in html
    assert '<td>Yes</td>' in html


def test_existing_database_gets_post_to_blog_column(tmp_path):
    db_path = tmp_path / 'existing.sqlite'
    connection = sqlite3.connect(db_path)
    connection.execute(
        """CREATE TABLE craigslist_jobs (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               job_key TEXT NOT NULL UNIQUE,
               name TEXT NOT NULL,
               location TEXT NOT NULL,
               term TEXT NOT NULL,
               category TEXT NOT NULL DEFAULT 'sss',
               radius INTEGER NOT NULL DEFAULT 0,
               run_times TEXT NOT NULL DEFAULT '06:00',
               enabled INTEGER NOT NULL DEFAULT 1,
               last_run_at TEXT,
               last_status TEXT,
               created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
               updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
           )"""
    )
    connection.commit()
    connection.close()

    app = create_app({'TESTING': True, 'DATABASE': str(db_path)})
    with app.app_context():
        init_db()
        columns = get_db().execute('PRAGMA table_info(craigslist_jobs)').fetchall()
    post_column = next(column for column in columns if column['name'] == 'post_to_blog')
    assert post_column['dflt_value'] == '1'


def test_unpublished_scraped_listings_are_excluded_from_public_pages(tmp_path):
    app = create_app({
        'TESTING': True,
        'DATABASE': str(tmp_path / 'test_unpublished.sqlite'),
    })
    with app.app_context():
        init_db()
        db = get_db()
        for craigslist_id, title, status in (
            ('private-1', 'Private scraped listing', 'unpublished'),
            ('public-1', 'Public scraped listing', 'published'),
            ('hidden-1', 'Hidden scraped listing', 'hidden'),
        ):
            db.execute(
                """INSERT INTO craigslist_postings
                   (craigslist_id, title, listing_url, status)
                   VALUES (?, ?, ?, ?)""",
                (craigslist_id, title, 'https://example.com/' + craigslist_id, status),
            )
        db.commit()

    client = app.test_client()
    for path in ('/', '/blog'):
        html = client.get(path).get_data(as_text=True)
        assert 'Public scraped listing' in html
        assert 'Private scraped listing' not in html
        assert 'Hidden scraped listing' not in html
