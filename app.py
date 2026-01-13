import os
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
from functools import wraps
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('SESSION_SECRET', 'dev-secret-key')

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

def get_site_settings():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT setting_key, setting_value FROM site_settings')
    rows = cur.fetchall()
    cur.close()
    conn.close()
    settings = {}
    for row in rows:
        settings[row['setting_key']] = row['setting_value']
    return settings

def get_db():
    return psycopg2.connect(os.environ.get('DATABASE_URL'), cursor_factory=RealDictCursor)

def get_sidebar_data():
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute('''
        SELECT s.id, s.series_name, s.year, COUNT(m.id) as match_count 
        FROM series s 
        LEFT JOIN matches m ON s.id = m.series_id 
        GROUP BY s.id, s.series_name, s.year 
        ORDER BY s.year DESC, s.series_name ASC 
        LIMIT 50
    ''')
    recent_series = cur.fetchall()
    
    cur.execute('SELECT COUNT(*) as total FROM series')
    total_series = cur.fetchone()['total']
    
    cur.execute('SELECT COUNT(*) as total FROM matches')
    total_matches = cur.fetchone()['total']
    
    cur.close()
    conn.close()
    
    return {
        'recent_series': recent_series,
        'total_series': total_series,
        'total_matches': total_matches
    }

def init_db():
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS series (
            id SERIAL PRIMARY KEY,
            series_id VARCHAR(50),
            month VARCHAR(20),
            year VARCHAR(10),
            series_name TEXT,
            date_range VARCHAR(100),
            series_url TEXT UNIQUE
        )
    ''')
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS matches (
            id SERIAL PRIMARY KEY,
            series_id INTEGER REFERENCES series(id),
            match_id VARCHAR(50),
            match_title TEXT,
            match_url TEXT,
            match_date VARCHAR(50)
        )
    ''')
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS scorecards (
            id SERIAL PRIMARY KEY,
            match_id VARCHAR(50) UNIQUE,
            match_title TEXT,
            match_status TEXT,
            scorecard_html TEXT,
            scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(50) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            role VARCHAR(20) DEFAULT 'admin',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP
        )
    ''')
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS site_settings (
            id SERIAL PRIMARY KEY,
            setting_key VARCHAR(100) UNIQUE NOT NULL,
            setting_value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS pages (
            id SERIAL PRIMARY KEY,
            slug VARCHAR(100) UNIQUE NOT NULL,
            title VARCHAR(255) NOT NULL,
            content TEXT,
            meta_title VARCHAR(255),
            meta_description TEXT,
            is_published BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS keyword_pages (
            id SERIAL PRIMARY KEY,
            keyword VARCHAR(100) NOT NULL,
            short_keyword VARCHAR(50),
            slug VARCHAR(100) UNIQUE NOT NULL,
            hero_title VARCHAR(255),
            hero_description TEXT,
            content TEXT,
            meta_title VARCHAR(255),
            meta_description TEXT,
            is_published BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS teams (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            short_name VARCHAR(20),
            slug VARCHAR(100) UNIQUE NOT NULL,
            country VARCHAR(100),
            flag_color VARCHAR(20) DEFAULT '#046A38',
            flag_url TEXT,
            team_type VARCHAR(50) DEFAULT 'international',
            description TEXT,
            is_published BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    try:
        cur.execute('ALTER TABLE teams ADD COLUMN IF NOT EXISTS team_type VARCHAR(50) DEFAULT \'international\'')
        cur.execute('ALTER TABLE teams ADD COLUMN IF NOT EXISTS flag_url TEXT')
    except:
        pass
    
    conn.commit()
    cur.close()
    conn.close()

def seed_defaults():
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute('SELECT COUNT(*) as cnt FROM users')
    if cur.fetchone()['cnt'] == 0:
        default_password = generate_password_hash('admin123')
        cur.execute('''
            INSERT INTO users (username, password_hash, role) 
            VALUES (%s, %s, %s)
        ''', ('admin', default_password, 'admin'))
    
    default_settings = {
        'site_name': 'Cricbuzz Live Score',
        'site_url': 'https://cricbuzz-live-score.com',
        'site_tagline': 'Live Cricket Scores, Match Updates & News',
        'theme_primary': '#046A38',
        'theme_secondary': '#FF6B00',
        'theme_accent': '#1A1A2E',
        'header_logo': 'Cricbuzz Live Score',
        'footer_text': '© 2026 Cricbuzz Live Score. All Rights Reserved.',
        'meta_keywords': 'cricket, live score, India vs Pakistan, Ind vs Pak, Cricbuzz, cricket match, IPL, T20, ODI, Test match'
    }
    
    for key, value in default_settings.items():
        cur.execute('''
            INSERT INTO site_settings (setting_key, setting_value)
            VALUES (%s, %s)
            ON CONFLICT (setting_key) DO NOTHING
        ''', (key, value))
    
    adsense_pages = [
        ('about', 'About Us', 'Learn about Cricbuzz Live Score - your trusted source for live cricket scores and updates.'),
        ('contact', 'Contact Us', 'Get in touch with Cricbuzz Live Score team for queries and feedback.'),
        ('privacy-policy', 'Privacy Policy', 'Privacy Policy for Cricbuzz Live Score website.'),
        ('disclaimer', 'Disclaimer', 'Disclaimer for Cricbuzz Live Score website.'),
        ('terms', 'Terms of Service', 'Terms and conditions for using Cricbuzz Live Score website.')
    ]
    
    for slug, title, desc in adsense_pages:
        cur.execute('''
            INSERT INTO pages (slug, title, meta_description, content)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (slug) DO NOTHING
        ''', (slug, title, desc, f'<h1>{title}</h1><p>{desc}</p>'))
    
    keywords = [
        ('India vs Pakistan', 'Ind vs Pak', 'india-vs-pakistan'),
        ('India vs England', 'Ind vs Eng', 'india-vs-england'),
        ('India vs Australia', 'Ind vs Aus', 'india-vs-australia'),
        ('India vs New Zealand', 'Ind vs NZ', 'india-vs-new-zealand'),
        ('India vs South Africa', 'Ind vs SA', 'india-vs-south-africa'),
        ('India vs Sri Lanka', 'Ind vs SL', 'india-vs-sri-lanka'),
        ('India vs Bangladesh', 'Ind vs Ban', 'india-vs-bangladesh'),
        ('India vs Afghanistan', 'Ind vs Afg', 'india-vs-afghanistan'),
        ('India vs West Indies', 'Ind vs WI', 'india-vs-west-indies')
    ]
    
    for keyword, short, slug in keywords:
        cur.execute('''
            INSERT INTO keyword_pages (keyword, short_keyword, slug, hero_title, meta_title, meta_description)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (slug) DO NOTHING
        ''', (keyword, short, slug, 
              f'{keyword} Live Score & Match Updates',
              f'{keyword} Live Score, Schedule, Results | Cricbuzz Live Score',
              f'Get live {keyword} cricket score, match schedule, results, highlights and news. Watch {short} live updates on Cricbuzz Live Score.'))
    
    default_teams = [
        ('India', 'IND', 'india', 'India', '#FF9933'),
        ('Pakistan', 'PAK', 'pakistan', 'Pakistan', '#01411C'),
        ('Australia', 'AUS', 'australia', 'Australia', '#FFCD00'),
        ('England', 'ENG', 'england', 'England', '#002366'),
        ('New Zealand', 'NZ', 'new-zealand', 'New Zealand', '#000000'),
        ('South Africa', 'SA', 'south-africa', 'South Africa', '#007A4D'),
        ('Sri Lanka', 'SL', 'sri-lanka', 'Sri Lanka', '#0033A0'),
        ('Bangladesh', 'BAN', 'bangladesh', 'Bangladesh', '#006A4E'),
        ('Afghanistan', 'AFG', 'afghanistan', 'Afghanistan', '#000000'),
        ('West Indies', 'WI', 'west-indies', 'West Indies', '#7B0041')
    ]
    
    for name, short, slug, country, color in default_teams:
        cur.execute('''
            INSERT INTO teams (name, short_name, slug, country, flag_color)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (slug) DO NOTHING
        ''', (name, short, slug, country, color))
    
    conn.commit()
    cur.close()
    conn.close()

@app.route('/')
def index():
    settings = get_site_settings()
    return render_template('frontend/home.html', settings=settings)

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        conn = get_db()
        cur = conn.cursor()
        cur.execute('SELECT * FROM users WHERE username = %s', (username,))
        user = cur.fetchone()
        cur.close()
        conn.close()
        
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            cur = get_db().cursor()
            cur.execute('UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = %s', (user['id'],))
            cur.connection.commit()
            cur.close()
            return redirect(url_for('admin'))
        else:
            flash('Invalid username or password', 'error')
    
    return render_template('admin/login.html')

@app.route('/admin/logout')
def admin_logout():
    session.clear()
    return redirect(url_for('admin_login'))

@app.route('/admin')
@login_required
def admin():
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute('''
        SELECT * FROM series ORDER BY year ASC, 
        CASE month 
            WHEN 'January' THEN 1 WHEN 'February' THEN 2 WHEN 'March' THEN 3 
            WHEN 'April' THEN 4 WHEN 'May' THEN 5 WHEN 'June' THEN 6 
            WHEN 'July' THEN 7 WHEN 'August' THEN 8 WHEN 'September' THEN 9 
            WHEN 'October' THEN 10 WHEN 'November' THEN 11 WHEN 'December' THEN 12 
        END ASC, series_name ASC
    ''')
    
    series = cur.fetchall()
    cur.close()
    conn.close()
    
    sidebar = get_sidebar_data()
    return render_template('admin.html', series=series, sidebar=sidebar)

@app.route('/live-score')
def live_score():
    sidebar = get_sidebar_data()
    return render_template('live_score.html', sidebar=sidebar)

@app.route('/scorecard')
def scorecard():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT id, series_name FROM series ORDER BY year DESC, series_name ASC')
    all_series = cur.fetchall()
    cur.close()
    conn.close()
    sidebar = get_sidebar_data()
    return render_template('scorecard.html', all_series=all_series, sidebar=sidebar)

@app.route('/api/scrape-scorecard', methods=['POST'])
def api_scrape_scorecard():
    from scraper import scrape_scorecard
    import re
    
    data = request.get_json()
    url = data.get('url', '')
    result = scrape_scorecard(url)
    
    if result.get('success') and result.get('html'):
        match_id_match = re.search(r'/live-cricket-scorecard/(\d+)', url)
        if match_id_match:
            match_id = match_id_match.group(1)
            
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(result['html'], 'html.parser')
            
            title_el = soup.find('h2')
            match_title = title_el.get_text(strip=True) if title_el else ''
            
            status_el = soup.find('div', class_='match-status')
            match_status = status_el.get_text(strip=True) if status_el else ''
            
            conn = get_db()
            cur = conn.cursor()
            
            cur.execute('''
                INSERT INTO scorecards (match_id, match_title, match_status, scorecard_html)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (match_id) DO UPDATE SET
                    match_title = EXCLUDED.match_title,
                    match_status = EXCLUDED.match_status,
                    scorecard_html = EXCLUDED.scorecard_html,
                    scraped_at = CURRENT_TIMESTAMP
            ''', (match_id, match_title, match_status, result['html']))
            
            conn.commit()
            cur.close()
            conn.close()
            
            result['saved'] = True
            result['match_id'] = match_id
    
    return jsonify(result)

@app.route('/matches')
def matches_page():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT id, series_name FROM series ORDER BY year DESC, series_name ASC')
    all_series = cur.fetchall()
    cur.close()
    conn.close()
    sidebar = get_sidebar_data()
    return render_template('matches_page.html', all_series=all_series, sidebar=sidebar)

@app.route('/api/get-matches/<int:series_id>')
def api_get_matches(series_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM series WHERE id = %s', (series_id,))
    series = cur.fetchone()
    cur.execute('SELECT * FROM matches WHERE series_id = %s ORDER BY match_id', (series_id,))
    matches = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify({'series': dict(series) if series else None, 'matches': [dict(m) for m in matches]})

@app.route('/admin/matches/<int:series_id>')
def view_matches(series_id):
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute('SELECT * FROM series WHERE id = %s', (series_id,))
    series = cur.fetchone()
    
    cur.execute('SELECT * FROM matches WHERE series_id = %s ORDER BY match_id', (series_id,))
    matches = cur.fetchall()
    
    cur.close()
    conn.close()
    
    sidebar = get_sidebar_data()
    return render_template('matches.html', series=series, matches=matches, sidebar=sidebar)

@app.route('/api/scrape-series', methods=['POST'])
def api_scrape_series():
    from scraper import scrape_series_data
    result = scrape_series_data()
    return jsonify(result)

@app.route('/api/scrape-matches/<int:series_id>', methods=['POST'])
def api_scrape_matches(series_id):
    from scraper import scrape_matches_from_series
    result = scrape_matches_from_series(series_id)
    return jsonify(result)

@app.route('/api/scrape-all-matches', methods=['POST'])
def api_scrape_all_matches():
    from scraper import scrape_all_matches
    result = scrape_all_matches()
    return jsonify(result)

@app.route('/api/clear-all-matches', methods=['POST'])
def api_clear_all_matches():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('DELETE FROM matches')
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'success': True, 'message': 'All matches cleared successfully'})

@app.route('/api/clear-all-series', methods=['POST'])
def api_clear_all_series():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('DELETE FROM matches')
    cur.execute('DELETE FROM series')
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'success': True, 'message': 'All series and matches cleared successfully'})

@app.route('/api/scrape-teams/<team_type>', methods=['POST'])
def api_scrape_teams(team_type):
    from scraper import scrape_teams
    if team_type not in ['international', 'domestic', 'league', 'women']:
        return jsonify({'success': False, 'message': 'Invalid team type'})
    result = scrape_teams(team_type)
    return jsonify(result)

@app.route('/api/get-scorecard/<match_id>')
def api_get_scorecard(match_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM scorecards WHERE match_id = %s', (match_id,))
    scorecard = cur.fetchone()
    cur.close()
    conn.close()
    
    if scorecard:
        return jsonify({
            'success': True,
            'scorecard': {
                'match_id': scorecard['match_id'],
                'match_title': scorecard['match_title'],
                'match_status': scorecard['match_status'],
                'html': scorecard['scorecard_html'],
                'scraped_at': str(scorecard['scraped_at'])
            }
        })
    return jsonify({'success': False, 'message': 'Scorecard not found'})

@app.route('/api/saved-scorecards')
def api_saved_scorecards():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT match_id, match_title, match_status, scraped_at FROM scorecards ORDER BY scraped_at DESC')
    scorecards = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify({'success': True, 'scorecards': [dict(s) for s in scorecards]})

@app.route('/page/<slug>')
def view_page(slug):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM pages WHERE slug = %s AND is_published = TRUE', (slug,))
    page = cur.fetchone()
    cur.close()
    conn.close()
    
    if not page:
        return 'Page not found', 404
    
    settings = get_site_settings()
    return render_template('frontend/page.html', page=page, settings=settings)

@app.route('/match/<slug>')
def keyword_page(slug):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM keyword_pages WHERE slug = %s AND is_published = TRUE', (slug,))
    keyword_page = cur.fetchone()
    cur.close()
    conn.close()
    
    if not keyword_page:
        return 'Page not found', 404
    
    settings = get_site_settings()
    return render_template('frontend/keyword_page.html', keyword_page=keyword_page, settings=settings)

@app.route('/admin/settings', methods=['GET', 'POST'])
@login_required
def admin_settings():
    conn = get_db()
    cur = conn.cursor()
    
    if request.method == 'POST':
        settings_to_update = ['site_name', 'site_url', 'site_tagline', 'theme_primary', 
                             'theme_secondary', 'theme_accent', 'header_logo', 'footer_text', 'meta_keywords']
        for key in settings_to_update:
            value = request.form.get(key, '')
            cur.execute('''
                INSERT INTO site_settings (setting_key, setting_value)
                VALUES (%s, %s)
                ON CONFLICT (setting_key) DO UPDATE SET setting_value = EXCLUDED.setting_value, updated_at = CURRENT_TIMESTAMP
            ''', (key, value))
        conn.commit()
        flash('Settings updated successfully', 'success')
    
    cur.execute('SELECT setting_key, setting_value FROM site_settings')
    rows = cur.fetchall()
    settings = {row['setting_key']: row['setting_value'] for row in rows}
    cur.close()
    conn.close()
    
    sidebar = get_sidebar_data()
    return render_template('admin/settings.html', settings=settings, sidebar=sidebar)

@app.route('/admin/change-password', methods=['GET', 'POST'])
@login_required
def admin_change_password():
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        conn = get_db()
        cur = conn.cursor()
        cur.execute('SELECT * FROM users WHERE id = %s', (session['user_id'],))
        user = cur.fetchone()
        
        if not check_password_hash(user['password_hash'], current_password):
            flash('Current password is incorrect', 'error')
        elif new_password != confirm_password:
            flash('New passwords do not match', 'error')
        elif len(new_password) < 8:
            flash('Password must be at least 8 characters', 'error')
        else:
            new_hash = generate_password_hash(new_password)
            cur.execute('UPDATE users SET password_hash = %s WHERE id = %s', (new_hash, session['user_id']))
            conn.commit()
            flash('Password changed successfully', 'success')
        
        cur.close()
        conn.close()
    
    sidebar = get_sidebar_data()
    return render_template('admin/change_password.html', sidebar=sidebar)

@app.route('/admin/pages')
@login_required
def admin_pages():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM pages ORDER BY title')
    pages = cur.fetchall()
    cur.close()
    conn.close()
    sidebar = get_sidebar_data()
    return render_template('admin/pages.html', pages=pages, sidebar=sidebar)

@app.route('/admin/pages/edit/<int:page_id>', methods=['GET', 'POST'])
@login_required
def admin_edit_page(page_id):
    conn = get_db()
    cur = conn.cursor()
    
    if request.method == 'POST':
        title = request.form.get('title')
        content = request.form.get('content')
        meta_title = request.form.get('meta_title')
        meta_description = request.form.get('meta_description')
        
        cur.execute('''
            UPDATE pages SET title=%s, content=%s, meta_title=%s, meta_description=%s, updated_at=CURRENT_TIMESTAMP
            WHERE id=%s
        ''', (title, content, meta_title, meta_description, page_id))
        conn.commit()
        flash('Page updated successfully', 'success')
    
    cur.execute('SELECT * FROM pages WHERE id = %s', (page_id,))
    page = cur.fetchone()
    cur.close()
    conn.close()
    
    sidebar = get_sidebar_data()
    return render_template('admin/edit_page.html', page=page, sidebar=sidebar)

@app.route('/admin/teams')
@login_required
def admin_teams():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM teams ORDER BY name')
    teams = cur.fetchall()
    cur.close()
    conn.close()
    sidebar = get_sidebar_data()
    return render_template('admin/teams.html', teams=teams, sidebar=sidebar)

@app.route('/admin/teams/add', methods=['GET', 'POST'])
@login_required
def admin_add_team():
    if request.method == 'POST':
        name = request.form.get('name')
        short_name = request.form.get('short_name')
        slug = request.form.get('slug')
        country = request.form.get('country')
        flag_color = request.form.get('flag_color', '#046A38')
        description = request.form.get('description')
        
        conn = get_db()
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO teams (name, short_name, slug, country, flag_color, description)
            VALUES (%s, %s, %s, %s, %s, %s)
        ''', (name, short_name, slug, country, flag_color, description))
        conn.commit()
        cur.close()
        conn.close()
        flash('Team added successfully', 'success')
        return redirect(url_for('admin_teams'))
    
    sidebar = get_sidebar_data()
    return render_template('admin/add_team.html', sidebar=sidebar)

@app.route('/admin/teams/edit/<int:team_id>', methods=['GET', 'POST'])
@login_required
def admin_edit_team(team_id):
    conn = get_db()
    cur = conn.cursor()
    
    if request.method == 'POST':
        name = request.form.get('name')
        short_name = request.form.get('short_name')
        country = request.form.get('country')
        flag_color = request.form.get('flag_color')
        description = request.form.get('description')
        
        cur.execute('''
            UPDATE teams SET name=%s, short_name=%s, country=%s, flag_color=%s, description=%s
            WHERE id=%s
        ''', (name, short_name, country, flag_color, description, team_id))
        conn.commit()
        flash('Team updated successfully', 'success')
    
    cur.execute('SELECT * FROM teams WHERE id = %s', (team_id,))
    team = cur.fetchone()
    cur.close()
    conn.close()
    
    sidebar = get_sidebar_data()
    return render_template('admin/edit_team.html', team=team, sidebar=sidebar)

@app.route('/admin/teams/delete/<int:team_id>', methods=['POST'])
@login_required
def admin_delete_team(team_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('DELETE FROM teams WHERE id = %s', (team_id,))
    conn.commit()
    cur.close()
    conn.close()
    flash('Team deleted successfully', 'success')
    return redirect(url_for('admin_teams'))

@app.route('/teams')
def teams_page():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('''SELECT * FROM teams WHERE is_published = TRUE 
                   ORDER BY team_type, rank, name''')
    all_teams = cur.fetchall()
    cur.close()
    conn.close()
    
    teams_by_type = {
        'international': [],
        'domestic': [],
        'league': [],
        'women': []
    }
    for team in all_teams:
        team_type = team.get('team_type') or 'international'
        if team_type in teams_by_type:
            teams_by_type[team_type].append(team)
        else:
            teams_by_type['international'].append(team)
    
    settings = get_site_settings()
    return render_template('frontend/teams.html', teams_by_type=teams_by_type, settings=settings)

@app.route('/series')
def series_page():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM series ORDER BY year DESC, month DESC, series_name')
    all_series = cur.fetchall()
    cur.close()
    conn.close()
    
    series_by_year = {}
    for s in all_series:
        year = s.get('year', 'Other')
        if year not in series_by_year:
            series_by_year[year] = []
        series_by_year[year].append(s)
    
    settings = get_site_settings()
    return render_template('frontend/series.html', series_by_year=series_by_year, settings=settings)

@app.route('/series/<int:series_id>')
def series_detail_page(series_id):
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute('SELECT * FROM series WHERE id = %s', (series_id,))
    series = cur.fetchone()
    
    if not series:
        cur.close()
        conn.close()
        return "Series not found", 404
    
    cur.execute('SELECT * FROM matches WHERE series_id = %s ORDER BY id ASC', (series_id,))
    matches = cur.fetchall()
    
    cur.close()
    conn.close()
    
    settings = get_site_settings()
    return render_template('frontend/series_detail.html', series=series, matches=matches, settings=settings)

@app.route('/match-score/<int:match_id>')
def match_score_page(match_id):
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute('SELECT * FROM scorecards WHERE match_id = %s', (str(match_id),))
    scorecard = cur.fetchone()
    
    cur.execute('SELECT * FROM matches WHERE match_id = %s', (str(match_id),))
    match = cur.fetchone()
    
    cur.close()
    conn.close()
    
    settings = get_site_settings()
    return render_template('frontend/match_score.html', scorecard=scorecard, match=match, settings=settings)

@app.route('/robots.txt')
def robots():
    content = """User-agent: *
Allow: /
Sitemap: https://cricbuzz-live-score.com/sitemap.xml

User-agent: Googlebot
Allow: /

User-agent: Bingbot
Allow: /
"""
    return content, 200, {'Content-Type': 'text/plain'}

@app.route('/sitemap.xml')
def sitemap():
    from datetime import datetime
    
    pages = [
        ('/', '1.0', 'daily'),
        ('/page/about', '0.8', 'monthly'),
        ('/page/contact', '0.8', 'monthly'),
        ('/page/privacy-policy', '0.6', 'monthly'),
        ('/page/disclaimer', '0.6', 'monthly'),
        ('/page/terms', '0.6', 'monthly'),
        ('/match/india-vs-pakistan', '0.9', 'daily'),
        ('/match/india-vs-australia', '0.9', 'daily'),
        ('/match/india-vs-england', '0.9', 'daily'),
        ('/match/india-vs-new-zealand', '0.9', 'daily'),
        ('/match/india-vs-south-africa', '0.9', 'daily'),
        ('/match/india-vs-sri-lanka', '0.9', 'daily'),
        ('/match/india-vs-bangladesh', '0.9', 'daily'),
        ('/match/india-vs-afghanistan', '0.9', 'daily'),
        ('/match/india-vs-west-indies', '0.9', 'daily'),
    ]
    
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    
    base_url = 'https://cricbuzz-live-score.com'
    today = datetime.now().strftime('%Y-%m-%d')
    
    for url, priority, freq in pages:
        xml += f'''  <url>
    <loc>{base_url}{url}</loc>
    <lastmod>{today}</lastmod>
    <changefreq>{freq}</changefreq>
    <priority>{priority}</priority>
  </url>\n'''
    
    xml += '</urlset>'
    return xml, 200, {'Content-Type': 'application/xml'}

with app.app_context():
    init_db()
    seed_defaults()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
