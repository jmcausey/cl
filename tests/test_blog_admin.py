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
