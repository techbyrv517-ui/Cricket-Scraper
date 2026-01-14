import os
import re
import uuid
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
from functools import wraps
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

load_dotenv()

scheduler_started = False

def refresh_live_matches():
    """Background job to refresh live match scores"""
    try:
        from scraper import scrape_scorecard
        
        with psycopg2.connect(os.environ.get('DATABASE_URL'), cursor_factory=RealDictCursor) as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    SELECT sc.match_id, m.match_url 
                    FROM scorecards sc
                    LEFT JOIN matches m ON sc.match_id::text = m.match_id::text
                    WHERE sc.is_live = TRUE
                ''')
                live_matches = cur.fetchall()
                
                for match in live_matches:
                    match_url = match.get('match_url')
                    if match_url:
                        scorecard_url = match_url.replace('/live-cricket-scores/', '/live-cricket-scorecard/')
                        if '/cricket-match/' in match_url:
                            scorecard_url = f"https://www.cricbuzz.com/live-cricket-scorecard/{match.get('match_id')}"
                        
                        result = scrape_scorecard(scorecard_url)
                        
                        if result.get('success'):
                            is_live = result.get('is_live', False)
                            final_score = result.get('final_score', '')
                            status_text = result.get('status_text', '')
                            
                            cur.execute('''
                                UPDATE scorecards 
                                SET scorecard_html = %s, 
                                    final_score = %s, 
                                    match_status = %s,
                                    is_live = %s, 
                                    last_updated = CURRENT_TIMESTAMP
                                WHERE match_id = %s
                            ''', (result['html'], final_score, status_text, is_live, match.get('match_id')))
                        else:
                            cur.execute('''
                                UPDATE scorecards SET is_live = FALSE WHERE match_id = %s
                            ''', (match.get('match_id'),))
                
                conn.commit()
                print(f"Refreshed {len(live_matches)} live matches")
    except Exception as e:
        print(f"Error refreshing live matches: {e}")

def start_scheduler():
    global scheduler_started
    if scheduler_started:
        return
    
    import atexit
    from apscheduler.schedulers.background import BackgroundScheduler
    
    scheduler = BackgroundScheduler()
    scheduler.add_job(func=refresh_live_matches, trigger="interval", seconds=90, id='refresh_live_matches', replace_existing=True)
    scheduler.start()
    scheduler_started = True
    atexit.register(lambda: scheduler.shutdown(wait=False))

def slugify(text):
    if not text:
        return ''
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_]+', '-', text)
    text = re.sub(r'-+', '-', text)
    text = text.strip('-')
    return text[:200]

app = Flask(__name__)
app.secret_key = os.environ.get('SESSION_SECRET', 'dev-secret-key')

UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

@app.context_processor
def inject_nav_categories():
    try:
        conn = psycopg2.connect(os.environ.get('DATABASE_URL'), cursor_factory=RealDictCursor)
        cur = conn.cursor()
        cur.execute('SELECT id, name, slug FROM post_categories WHERE is_published = TRUE AND show_in_nav = TRUE ORDER BY nav_order ASC, name ASC')
        categories = cur.fetchall()
        cur.close()
        conn.close()
        return dict(nav_categories=categories)
    except:
        return dict(nav_categories=[])
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

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

def get_nav_categories():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT id, name, slug FROM post_categories WHERE is_published = TRUE AND show_in_nav = TRUE ORDER BY nav_order ASC, name ASC')
    categories = cur.fetchall()
    cur.close()
    conn.close()
    return categories

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
        CREATE TABLE IF NOT EXISTS live_matches (
            id SERIAL PRIMARY KEY,
            match_id VARCHAR(50),
            series_name VARCHAR(255),
            match_info VARCHAR(255),
            match_date VARCHAR(100),
            team1_name VARCHAR(100),
            team1_score VARCHAR(50),
            team2_name VARCHAR(100),
            team2_score VARCHAR(50),
            status VARCHAR(100),
            is_live BOOLEAN DEFAULT TRUE,
            display_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS posts (
            id SERIAL PRIMARY KEY,
            title VARCHAR(255) NOT NULL,
            slug VARCHAR(255) UNIQUE NOT NULL,
            featured_image TEXT,
            excerpt TEXT,
            content TEXT,
            category VARCHAR(100),
            meta_title VARCHAR(255),
            meta_description TEXT,
            is_published BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS players (
            id SERIAL PRIMARY KEY,
            team_id INTEGER REFERENCES teams(id) ON DELETE CASCADE,
            cricbuzz_id VARCHAR(50),
            name VARCHAR(255) NOT NULL,
            slug VARCHAR(255),
            image_url TEXT,
            role VARCHAR(100),
            batting_style VARCHAR(100),
            bowling_style VARCHAR(100),
            is_published BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    try:
        cur.execute('ALTER TABLE teams ADD COLUMN IF NOT EXISTS team_type VARCHAR(50) DEFAULT \'international\'')
        cur.execute('ALTER TABLE teams ADD COLUMN IF NOT EXISTS flag_url TEXT')
        cur.execute('ALTER TABLE teams ADD COLUMN IF NOT EXISTS cricbuzz_team_id VARCHAR(20)')
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

def parse_match_scores(scorecard_html):
    """Parse scorecard HTML to extract team scores"""
    if not scorecard_html:
        return None, None, None, None
    
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(scorecard_html, 'html.parser')
    
    innings = soup.find_all('div', class_='innings-header')
    teams = []
    for inn in innings[:2]:
        text = inn.get_text(strip=True)
        parts = text.split()
        if parts:
            team_code = parts[0]
            score = ' '.join(parts[1:]) if len(parts) > 1 else ''
            teams.append({'code': team_code, 'score': score})
    
    team1 = teams[0] if len(teams) > 0 else {'code': '', 'score': ''}
    team2 = teams[1] if len(teams) > 1 else {'code': '', 'score': ''}
    
    return team1['code'], team1['score'], team2['code'], team2['score']

def parse_match_date(date_str):
    """Parse match date string to datetime"""
    from datetime import datetime
    if not date_str:
        return None
    try:
        clean_date = date_str.replace(',', '').strip()
        parts = clean_date.split()
        if len(parts) >= 4:
            month_day_year = ' '.join(parts[1:])
            return datetime.strptime(month_day_year, '%b %d %Y')
        elif len(parts) >= 3:
            month_day = ' '.join(parts[1:])
            current_year = datetime.now().year
            return datetime.strptime(f"{month_day} {current_year}", '%b %d %Y')
    except:
        pass
    return None

def parse_team_names(match_title):
    """Extract team names from match title like 'Sri Lanka vs Pakistan, 3rd T20I'"""
    if not match_title:
        return None, None, None
    
    parts = match_title.split(',')
    teams_part = parts[0].strip()
    match_info = parts[1].strip() if len(parts) > 1 else ''
    
    if ' vs ' in teams_part:
        teams = teams_part.split(' vs ')
        team1 = teams[0].strip()
        team2 = teams[1].strip()
        return team1, team2, match_info
    return None, None, match_info

@app.route('/')
def index():
    from datetime import datetime
    settings = get_site_settings()
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute('''SELECT m.*, s.series_name, sc.match_status as result, sc.scorecard_html, sc.final_score
                   FROM matches m 
                   LEFT JOIN series s ON m.series_id = s.id 
                   LEFT JOIN scorecards sc ON m.match_id = sc.match_id
                   ORDER BY m.id DESC''')
    all_matches = cur.fetchall()
    
    recent_matches = []
    upcoming_matches = []
    
    for row in all_matches:
        match = dict(row)
        match_date = parse_match_date(row.get('match_date'))
        match['parsed_date'] = match_date
        
        final_score = row.get('final_score', '')
        if final_score and ' vs ' in final_score:
            score_parts = final_score.split(' vs ')
            if len(score_parts) >= 2:
                t1_parts = score_parts[0].strip().rsplit(' ', 1)
                t2_parts = score_parts[1].strip().rsplit(' ', 1)
                match['team1_score'] = t1_parts[1] if len(t1_parts) > 1 else ''
                match['team2_score'] = t2_parts[1] if len(t2_parts) > 1 else ''
            else:
                match['team1_score'] = ''
                match['team2_score'] = ''
        else:
            t1_code, t1_score, t2_code, t2_score = parse_match_scores(row.get('scorecard_html'))
            match['team1_score'] = t1_score
            match['team2_score'] = t2_score
        
        team1_name, team2_name, match_info = parse_team_names(row.get('match_title'))
        match['team1_name'] = team1_name
        match['team2_name'] = team2_name
        match['match_info'] = match_info
        match['team1_flag'] = get_team_flag(team1_name, cur)
        match['team2_flag'] = get_team_flag(team2_name, cur)
        
        if match_date and match_date < today:
            recent_matches.append(match)
        elif match_date and match_date >= today:
            upcoming_matches.append(match)
    
    recent_matches.sort(key=lambda x: (x.get('result') is None, -(x['parsed_date'] or datetime.min).timestamp()))
    upcoming_matches.sort(key=lambda x: x['parsed_date'] or datetime.max)
    
    initial_recent = recent_matches[:10]
    upcoming_matches = upcoming_matches[:15]
    has_more_recent = len(recent_matches) > 10
    
    cur.execute('SELECT id, title, slug, featured_image, excerpt FROM posts WHERE is_published = TRUE ORDER BY created_at DESC LIMIT 10')
    sidebar_posts = cur.fetchall()
    
    cur.execute('SELECT * FROM live_matches WHERE is_live = TRUE ORDER BY display_order ASC, id DESC')
    live_matches = cur.fetchall()
    
    cur.execute('SELECT * FROM matchups WHERE is_published = TRUE ORDER BY display_order ASC, id ASC')
    matchups = cur.fetchall()
    
    cur.close()
    conn.close()
    
    return render_template('frontend/home.html', 
                          settings=settings,
                          live_matches=live_matches,
                          matchups=matchups,
                          recent_matches=initial_recent,
                          upcoming_matches=upcoming_matches,
                          has_more_recent=has_more_recent,
                          sidebar_posts=sidebar_posts)

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
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM live_matches ORDER BY display_order ASC, id DESC')
    live_matches = cur.fetchall()
    cur.close()
    conn.close()
    sidebar = get_sidebar_data()
    return render_template('live_score.html', live_matches=live_matches, sidebar=sidebar)

@app.route('/admin/live-match/add', methods=['POST'])
@login_required
def admin_add_live_match():
    series_name = request.form.get('series_name', '')
    match_info = request.form.get('match_info', '')
    match_date = request.form.get('match_date', '')
    team1_name = request.form.get('team1_name', '')
    team1_score = request.form.get('team1_score', '')
    team2_name = request.form.get('team2_name', '')
    team2_score = request.form.get('team2_score', '')
    status = request.form.get('status', '')
    is_live = request.form.get('is_live') == 'on'
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO live_matches (series_name, match_info, match_date, team1_name, team1_score, team2_name, team2_score, status, is_live)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    ''', (series_name, match_info, match_date, team1_name, team1_score, team2_name, team2_score, status, is_live))
    conn.commit()
    cur.close()
    conn.close()
    flash('Live match added successfully!', 'success')
    return redirect(url_for('live_score'))

@app.route('/admin/live-match/edit/<int:match_id>', methods=['POST'])
@login_required
def admin_edit_live_match(match_id):
    series_name = request.form.get('series_name', '')
    match_info = request.form.get('match_info', '')
    match_date = request.form.get('match_date', '')
    team1_name = request.form.get('team1_name', '')
    team1_score = request.form.get('team1_score', '')
    team2_name = request.form.get('team2_name', '')
    team2_score = request.form.get('team2_score', '')
    status = request.form.get('status', '')
    is_live = request.form.get('is_live') == 'on'
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute('''
        UPDATE live_matches SET series_name=%s, match_info=%s, match_date=%s, team1_name=%s, team1_score=%s, team2_name=%s, team2_score=%s, status=%s, is_live=%s, updated_at=CURRENT_TIMESTAMP
        WHERE id=%s
    ''', (series_name, match_info, match_date, team1_name, team1_score, team2_name, team2_score, status, is_live, match_id))
    conn.commit()
    cur.close()
    conn.close()
    flash('Live match updated successfully!', 'success')
    return redirect(url_for('live_score'))

@app.route('/admin/live-match/delete/<int:match_id>', methods=['POST'])
@login_required
def admin_delete_live_match(match_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('DELETE FROM live_matches WHERE id = %s', (match_id,))
    conn.commit()
    cur.close()
    conn.close()
    flash('Live match deleted successfully!', 'success')
    return redirect(url_for('live_score'))

@app.route('/api/clear-all-live-matches', methods=['POST'])
def api_clear_all_live_matches():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('DELETE FROM live_matches')
    deleted_count = cur.rowcount
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'success': True, 'message': f'{deleted_count} live matches cleared successfully'})

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

def get_team_flag(team_name, cur):
    """Get team flag URL from database"""
    if not team_name:
        return ''
    cur.execute('SELECT flag_url FROM teams WHERE LOWER(name) = LOWER(%s) LIMIT 1', (team_name,))
    result = cur.fetchone()
    return result['flag_url'] if result and result.get('flag_url') else ''

@app.route('/api/live-matches')
def api_live_matches():
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute('SELECT * FROM live_matches WHERE is_live = TRUE ORDER BY display_order ASC, id DESC')
    live_matches_data = cur.fetchall()
    
    matches_data = []
    for row in live_matches_data:
        match = dict(row)
        team1_flag = get_team_flag(match.get('team1_name'), cur)
        team2_flag = get_team_flag(match.get('team2_name'), cur)
        
        matches_data.append({
            'match_id': match.get('match_id'),
            'match_title': f"{match.get('team1_name', '')} vs {match.get('team2_name', '')}",
            'series_name': match.get('series_name', 'LIVE MATCH'),
            'match_info': match.get('match_info', ''),
            'team1_name': match.get('team1_name', ''),
            'team2_name': match.get('team2_name', ''),
            'team1_flag': team1_flag,
            'team2_flag': team2_flag,
            'team1_score': match.get('team1_score', ''),
            'team2_score': match.get('team2_score', ''),
            'match_status': match.get('status', ''),
            'last_updated': match.get('updated_at').isoformat() if match.get('updated_at') else ''
        })
    
    cur.close()
    conn.close()
    return jsonify({'matches': matches_data, 'count': len(matches_data)})

@app.route('/api/recent-matches')
def api_recent_matches():
    from datetime import datetime
    offset = request.args.get('offset', 0, type=int)
    limit = request.args.get('limit', 10, type=int)
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute('''SELECT m.*, s.series_name, sc.match_status as result, sc.scorecard_html, sc.final_score
                   FROM matches m 
                   LEFT JOIN series s ON m.series_id = s.id 
                   LEFT JOIN scorecards sc ON m.match_id = sc.match_id
                   ORDER BY m.id DESC''')
    all_matches = cur.fetchall()
    cur.close()
    conn.close()
    
    recent_matches = []
    for row in all_matches:
        match = dict(row)
        match_date = parse_match_date(row.get('match_date'))
        match['parsed_date'] = match_date
        
        final_score = row.get('final_score', '')
        if final_score and ' vs ' in final_score:
            score_parts = final_score.split(' vs ')
            if len(score_parts) >= 2:
                t1_parts = score_parts[0].strip().rsplit(' ', 1)
                t2_parts = score_parts[1].strip().rsplit(' ', 1)
                match['team1_score'] = t1_parts[1] if len(t1_parts) > 1 else ''
                match['team2_score'] = t2_parts[1] if len(t2_parts) > 1 else ''
            else:
                match['team1_score'] = ''
                match['team2_score'] = ''
        else:
            t1_code, t1_score, t2_code, t2_score = parse_match_scores(row.get('scorecard_html'))
            match['team1_score'] = t1_score
            match['team2_score'] = t2_score
        
        team1_name, team2_name, match_info = parse_team_names(row.get('match_title'))
        match['team1_name'] = team1_name
        match['team2_name'] = team2_name
        match['match_info'] = match_info
        match['team1_flag'] = get_team_flag(team1_name, cur)
        match['team2_flag'] = get_team_flag(team2_name, cur)
        
        if match_date and match_date < today:
            recent_matches.append(match)
    
    recent_matches.sort(key=lambda x: (x.get('result') is None, -(x['parsed_date'] or datetime.min).timestamp()))
    
    paginated = recent_matches[offset:offset + limit]
    has_more = len(recent_matches) > offset + limit
    
    matches_data = []
    for m in paginated:
        matches_data.append({
            'match_id': m.get('match_id'),
            'match_title': m.get('match_title'),
            'series_name': m.get('series_name', 'CRICKET MATCH'),
            'match_info': m.get('match_info', ''),
            'match_date': m.get('match_date', ''),
            'team1_name': m.get('team1_name', ''),
            'team2_name': m.get('team2_name', ''),
            'team1_score': m.get('team1_score', ''),
            'team2_score': m.get('team2_score', ''),
            'team1_flag': m.get('team1_flag', ''),
            'team2_flag': m.get('team2_flag', ''),
            'result': m.get('result', '')
        })
    
    return jsonify({'matches': matches_data, 'has_more': has_more})

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
            match_status = result.get('status_text', '') or (status_el.get_text(strip=True) if status_el else '')
            
            final_score = result.get('final_score', '')
            is_live = result.get('is_live', False)
            
            conn = get_db()
            cur = conn.cursor()
            
            cur.execute('''
                INSERT INTO scorecards (match_id, match_title, match_status, scorecard_html, final_score, is_live, last_updated)
                VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (match_id) DO UPDATE SET
                    match_title = EXCLUDED.match_title,
                    match_status = EXCLUDED.match_status,
                    scorecard_html = EXCLUDED.scorecard_html,
                    final_score = EXCLUDED.final_score,
                    is_live = EXCLUDED.is_live,
                    last_updated = CURRENT_TIMESTAMP,
                    scraped_at = CURRENT_TIMESTAMP
            ''', (match_id, match_title, match_status, result['html'], final_score, is_live))
            
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

@app.route('/api/upload-image', methods=['POST'])
@login_required
def api_upload_image():
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file uploaded'})
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'})
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4().hex}_{filename}"
        
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        file.save(filepath)
        
        file_url = f"/static/uploads/{unique_filename}"
        return jsonify({'success': True, 'url': file_url, 'filename': unique_filename})
    
    return jsonify({'success': False, 'error': 'File type not allowed. Use PNG, JPG, GIF, or WebP.'})

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

@app.route('/api/clear-series-matches/<int:series_id>', methods=['POST'])
def api_clear_series_matches(series_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT series_name FROM series WHERE id = %s', (series_id,))
    series = cur.fetchone()
    if not series:
        cur.close()
        conn.close()
        return jsonify({'success': False, 'message': 'Series not found'})
    
    cur.execute('DELETE FROM matches WHERE series_id = %s', (series_id,))
    deleted_count = cur.rowcount
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'success': True, 'message': f'Cleared {deleted_count} matches from {series["series_name"]}'})

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

@app.route('/api/clear-all-scorecards', methods=['POST'])
def api_clear_all_scorecards():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('DELETE FROM scorecards')
    deleted_count = cur.rowcount
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'success': True, 'message': f'{deleted_count} scorecards cleared successfully'})

@app.route('/api/clear-all-data', methods=['POST'])
@login_required
def api_clear_all_data():
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute('DELETE FROM scorecards')
        scorecards_count = cur.rowcount
        cur.execute('DELETE FROM matches')
        matches_count = cur.rowcount
        cur.execute('DELETE FROM series')
        series_count = cur.rowcount
        cur.execute('DELETE FROM live_matches')
        live_count = cur.rowcount
        conn.commit()
        message = f'All data cleared: {series_count} series, {matches_count} matches, {scorecards_count} scorecards, {live_count} live matches'
        return jsonify({'success': True, 'message': message})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})
    finally:
        cur.close()
        conn.close()

@app.route('/api/scrape-live-scores', methods=['POST'])
@login_required
def api_scrape_live_scores():
    from scraper import scrape_live_scores
    result = scrape_live_scores()
    return jsonify(result)

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
        settings_to_update = [
            'site_name', 'site_url', 'site_tagline', 'theme_primary', 
            'theme_secondary', 'theme_accent', 'header_logo', 'footer_text', 'meta_keywords',
            'google_analytics_id', 'google_analytics_enabled',
            'adsense_publisher_id', 'adsense_auto_ads', 'adsense_enabled',
            'ad_slot_header', 'ad_slot_sidebar', 'ad_slot_content', 'ad_slot_footer',
            'ad_header_enabled', 'ad_sidebar_enabled', 'ad_content_enabled', 'ad_footer_enabled'
        ]
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

@app.route('/admin/posts')
@login_required
def admin_posts():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('''
        SELECT p.*, pc.name as category_name 
        FROM posts p 
        LEFT JOIN post_categories pc ON p.category_id = pc.id 
        ORDER BY p.created_at DESC
    ''')
    posts = cur.fetchall()
    cur.close()
    conn.close()
    sidebar = get_sidebar_data()
    return render_template('admin/posts.html', posts=posts, sidebar=sidebar)

@app.route('/admin/posts/add', methods=['GET', 'POST'])
@login_required
def admin_add_post():
    conn = get_db()
    cur = conn.cursor()
    
    if request.method == 'POST':
        title = request.form.get('title')
        base_slug = slugify(title)
        featured_image = request.form.get('featured_image')
        excerpt = request.form.get('excerpt')
        content = request.form.get('content')
        category_id = request.form.get('category_id')
        focus_keyword = request.form.get('focus_keyword')
        meta_title = request.form.get('meta_title')
        meta_description = request.form.get('meta_description')
        canonical_url = request.form.get('canonical_url')
        og_image = request.form.get('og_image')
        is_published = request.form.get('is_published') == 'on'
        
        if 'featured_image_file' in request.files:
            file = request.files['featured_image_file']
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                unique_filename = f"{uuid.uuid4().hex}_{filename}"
                os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                file.save(filepath)
                featured_image = f"/static/uploads/{unique_filename}"
        
        slug = base_slug
        counter = 1
        while True:
            cur.execute('SELECT id FROM posts WHERE slug = %s', (slug,))
            if not cur.fetchone():
                break
            slug = f"{base_slug}-{counter}"
            counter += 1
        
        cur.execute('''
            INSERT INTO posts (title, slug, featured_image, excerpt, content, category_id, focus_keyword, meta_title, meta_description, canonical_url, og_image, is_published)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (title, slug, featured_image, excerpt, content, category_id or None, focus_keyword, meta_title, meta_description, canonical_url, og_image, is_published))
        conn.commit()
        cur.close()
        conn.close()
        flash('Post created successfully', 'success')
        return redirect(url_for('admin_posts'))
    
    cur.execute('SELECT * FROM post_categories ORDER BY name')
    categories = cur.fetchall()
    cur.close()
    conn.close()
    sidebar = get_sidebar_data()
    return render_template('admin/add_post.html', categories=categories, sidebar=sidebar)

@app.route('/admin/posts/edit/<int:post_id>', methods=['GET', 'POST'])
@login_required
def admin_edit_post(post_id):
    conn = get_db()
    cur = conn.cursor()
    
    if request.method == 'POST':
        title = request.form.get('title')
        featured_image = request.form.get('featured_image')
        excerpt = request.form.get('excerpt')
        content = request.form.get('content')
        category_id = request.form.get('category_id')
        focus_keyword = request.form.get('focus_keyword')
        meta_title = request.form.get('meta_title')
        meta_description = request.form.get('meta_description')
        canonical_url = request.form.get('canonical_url')
        og_image = request.form.get('og_image')
        is_published = request.form.get('is_published') == 'on'
        
        if 'featured_image_file' in request.files:
            file = request.files['featured_image_file']
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                unique_filename = f"{uuid.uuid4().hex}_{filename}"
                os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                file.save(filepath)
                featured_image = f"/static/uploads/{unique_filename}"
        
        cur.execute('''
            UPDATE posts SET title=%s, featured_image=%s, excerpt=%s, content=%s, category_id=%s, 
            focus_keyword=%s, meta_title=%s, meta_description=%s, canonical_url=%s, og_image=%s,
            is_published=%s, updated_at=CURRENT_TIMESTAMP
            WHERE id=%s
        ''', (title, featured_image, excerpt, content, category_id or None, focus_keyword, meta_title, meta_description, canonical_url, og_image, is_published, post_id))
        conn.commit()
        flash('Post updated successfully', 'success')
    
    cur.execute('SELECT * FROM posts WHERE id = %s', (post_id,))
    post = cur.fetchone()
    cur.execute('SELECT * FROM post_categories ORDER BY name')
    categories = cur.fetchall()
    cur.close()
    conn.close()
    
    sidebar = get_sidebar_data()
    return render_template('admin/edit_post.html', post=post, categories=categories, sidebar=sidebar)

@app.route('/admin/posts/delete/<int:post_id>', methods=['POST'])
@login_required
def admin_delete_post(post_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('DELETE FROM posts WHERE id = %s', (post_id,))
    conn.commit()
    cur.close()
    conn.close()
    flash('Post deleted successfully', 'success')
    return redirect(url_for('admin_posts'))

@app.route('/admin/posts/categories')
@login_required
def admin_post_categories():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('''
        SELECT pc.*, COUNT(p.id) as post_count 
        FROM post_categories pc 
        LEFT JOIN posts p ON pc.id = p.category_id 
        GROUP BY pc.id 
        ORDER BY pc.name
    ''')
    categories = cur.fetchall()
    cur.close()
    conn.close()
    sidebar = get_sidebar_data()
    return render_template('admin/post_categories.html', categories=categories, sidebar=sidebar)

@app.route('/admin/posts/categories/edit/<int:cat_id>', methods=['GET', 'POST'])
@login_required
def admin_edit_category(cat_id):
    conn = get_db()
    cur = conn.cursor()
    
    if request.method == 'POST':
        name = request.form.get('name')
        short_name = request.form.get('short_name')
        description = request.form.get('description')
        hero_title = request.form.get('hero_title')
        hero_description = request.form.get('hero_description')
        content = request.form.get('content')
        focus_keyword = request.form.get('focus_keyword')
        meta_title = request.form.get('meta_title')
        meta_description = request.form.get('meta_description')
        canonical_url = request.form.get('canonical_url')
        og_image = request.form.get('og_image')
        is_published = request.form.get('is_published') == 'on'
        show_in_nav = request.form.get('show_in_nav') == 'on'
        nav_order = int(request.form.get('nav_order', 0) or 0)
        
        cur.execute('''
            UPDATE post_categories SET name=%s, short_name=%s, description=%s, hero_title=%s,
            hero_description=%s, content=%s, focus_keyword=%s, meta_title=%s, meta_description=%s,
            canonical_url=%s, og_image=%s, is_published=%s, show_in_nav=%s, nav_order=%s, updated_at=CURRENT_TIMESTAMP
            WHERE id=%s
        ''', (name, short_name, description, hero_title, hero_description, content, focus_keyword, 
              meta_title, meta_description, canonical_url, og_image, is_published, show_in_nav, nav_order, cat_id))
        conn.commit()
        flash('Category updated successfully', 'success')
    
    cur.execute('SELECT * FROM post_categories WHERE id = %s', (cat_id,))
    category = cur.fetchone()
    cur.close()
    conn.close()
    
    sidebar = get_sidebar_data()
    return render_template('admin/edit_category.html', category=category, sidebar=sidebar)

@app.route('/admin/posts/categories/add', methods=['GET', 'POST'])
@login_required
def admin_add_category():
    conn = get_db()
    cur = conn.cursor()
    
    if request.method == 'POST':
        name = request.form.get('name')
        short_name = request.form.get('short_name')
        slug = slugify(name)
        description = request.form.get('description')
        hero_title = request.form.get('hero_title')
        hero_description = request.form.get('hero_description')
        content = request.form.get('content')
        focus_keyword = request.form.get('focus_keyword')
        meta_title = request.form.get('meta_title')
        meta_description = request.form.get('meta_description')
        canonical_url = request.form.get('canonical_url')
        og_image = request.form.get('og_image')
        is_published = request.form.get('is_published') == 'on'
        show_in_nav = request.form.get('show_in_nav') == 'on'
        nav_order = int(request.form.get('nav_order', 0) or 0)
        
        cur.execute('''
            INSERT INTO post_categories (name, short_name, slug, description, hero_title, hero_description, 
            content, focus_keyword, meta_title, meta_description, canonical_url, og_image, is_published, 
            show_in_nav, nav_order, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ''', (name, short_name, slug, description, hero_title, hero_description, content, focus_keyword, 
              meta_title, meta_description, canonical_url, og_image, is_published, show_in_nav, nav_order))
        conn.commit()
        cur.close()
        conn.close()
        flash('Category added successfully', 'success')
        return redirect(url_for('admin_post_categories'))
    
    cur.close()
    conn.close()
    sidebar = get_sidebar_data()
    return render_template('admin/add_category.html', sidebar=sidebar)

@app.route('/admin/posts/categories/delete/<int:cat_id>', methods=['POST'])
@login_required
def admin_delete_category(cat_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('DELETE FROM post_categories WHERE id = %s', (cat_id,))
    conn.commit()
    cur.close()
    conn.close()
    flash('Category deleted successfully', 'success')
    return redirect(url_for('admin_post_categories'))

@app.route('/admin/matchups')
@login_required
def admin_matchups():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM matchups ORDER BY display_order ASC, id ASC')
    matchups = cur.fetchall()
    cur.close()
    conn.close()
    sidebar = get_sidebar_data()
    return render_template('admin/matchups.html', matchups=matchups, sidebar=sidebar)

@app.route('/admin/matchups/add', methods=['GET', 'POST'])
@login_required
def admin_add_matchup():
    conn = get_db()
    cur = conn.cursor()
    
    if request.method == 'POST':
        title = request.form.get('title')
        slug = slugify(title)
        short_description = request.form.get('short_description')
        content = request.form.get('content')
        link_url = request.form.get('link_url')
        image_url = request.form.get('image_url')
        color1 = request.form.get('color1', '#FF9933')
        color2 = request.form.get('color2', '#046A38')
        display_order = int(request.form.get('display_order', 0) or 0)
        focus_keyword = request.form.get('focus_keyword')
        meta_title = request.form.get('meta_title')
        meta_description = request.form.get('meta_description')
        is_published = request.form.get('is_published') == 'on'
        
        cur.execute('''
            INSERT INTO matchups (title, slug, short_description, content, link_url, image_url, 
            color1, color2, display_order, focus_keyword, meta_title, meta_description, is_published)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (title, slug, short_description, content, link_url, image_url, color1, color2,
              display_order, focus_keyword, meta_title, meta_description, is_published))
        conn.commit()
        cur.close()
        conn.close()
        flash('Matchup added successfully', 'success')
        return redirect(url_for('admin_matchups'))
    
    cur.close()
    conn.close()
    sidebar = get_sidebar_data()
    return render_template('admin/add_matchup.html', sidebar=sidebar)

@app.route('/admin/matchups/edit/<int:matchup_id>', methods=['GET', 'POST'])
@login_required
def admin_edit_matchup(matchup_id):
    conn = get_db()
    cur = conn.cursor()
    
    if request.method == 'POST':
        title = request.form.get('title')
        short_description = request.form.get('short_description')
        content = request.form.get('content')
        link_url = request.form.get('link_url')
        image_url = request.form.get('image_url')
        color1 = request.form.get('color1', '#FF9933')
        color2 = request.form.get('color2', '#046A38')
        display_order = int(request.form.get('display_order', 0) or 0)
        focus_keyword = request.form.get('focus_keyword')
        meta_title = request.form.get('meta_title')
        meta_description = request.form.get('meta_description')
        is_published = request.form.get('is_published') == 'on'
        
        cur.execute('''
            UPDATE matchups SET title=%s, short_description=%s, content=%s, link_url=%s, 
            image_url=%s, color1=%s, color2=%s, display_order=%s, focus_keyword=%s, 
            meta_title=%s, meta_description=%s, is_published=%s, updated_at=CURRENT_TIMESTAMP
            WHERE id=%s
        ''', (title, short_description, content, link_url, image_url, color1, color2,
              display_order, focus_keyword, meta_title, meta_description, is_published, matchup_id))
        conn.commit()
        flash('Matchup updated successfully', 'success')
    
    cur.execute('SELECT * FROM matchups WHERE id = %s', (matchup_id,))
    matchup = cur.fetchone()
    cur.close()
    conn.close()
    
    sidebar = get_sidebar_data()
    return render_template('admin/edit_matchup.html', matchup=matchup, sidebar=sidebar)

@app.route('/admin/matchups/delete/<int:matchup_id>', methods=['POST'])
@login_required
def admin_delete_matchup(matchup_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('DELETE FROM matchups WHERE id = %s', (matchup_id,))
    conn.commit()
    cur.close()
    conn.close()
    flash('Matchup deleted successfully', 'success')
    return redirect(url_for('admin_matchups'))

@app.route('/category/<slug>')
def view_category(slug):
    settings = get_site_settings()
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute('SELECT * FROM post_categories WHERE slug = %s AND is_published = TRUE', (slug,))
    category = cur.fetchone()
    
    if not category:
        cur.close()
        conn.close()
        return "Category not found", 404
    
    cur.execute('''
        SELECT * FROM posts 
        WHERE category_id = %s AND is_published = TRUE 
        ORDER BY created_at DESC
    ''', (category['id'],))
    posts = cur.fetchall()
    
    cur.execute('SELECT * FROM post_categories WHERE is_published = TRUE ORDER BY name')
    all_categories = cur.fetchall()
    
    cur.execute('SELECT id, title, slug, featured_image FROM posts WHERE is_published = TRUE ORDER BY created_at DESC LIMIT 10')
    sidebar_posts = cur.fetchall()
    
    cur.close()
    conn.close()
    
    return render_template('frontend/category.html', category=category, posts=posts, all_categories=all_categories, sidebar_posts=sidebar_posts, settings=settings)

@app.route('/post/<slug>')
def view_post(slug):
    settings = get_site_settings()
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT p.*, pc.name as category, pc.slug as category_slug FROM posts p LEFT JOIN post_categories pc ON p.category_id = pc.id WHERE p.slug = %s AND p.is_published = TRUE', (slug,))
    post = cur.fetchone()
    
    if not post:
        cur.close()
        conn.close()
        return "Post not found", 404
    
    cur.execute('SELECT id, title, slug, featured_image FROM posts WHERE is_published = TRUE ORDER BY created_at DESC LIMIT 10')
    sidebar_posts = cur.fetchall()
    cur.close()
    conn.close()
    
    return render_template('frontend/post.html', post=post, sidebar_posts=sidebar_posts, settings=settings)

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

@app.route('/admin/players')
@login_required
def admin_players():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM teams ORDER BY name')
    teams = cur.fetchall()
    cur.execute('SELECT p.*, t.name as team_name FROM players p LEFT JOIN teams t ON p.team_id = t.id ORDER BY t.name, p.role, p.name')
    players = cur.fetchall()
    cur.close()
    conn.close()
    sidebar = get_sidebar_data()
    return render_template('admin/players.html', teams=teams, players=players, sidebar=sidebar)

@app.route('/api/scrape-players/<int:team_id>', methods=['POST'])
@login_required
def api_scrape_players(team_id):
    from scraper import scrape_players_from_team
    result = scrape_players_from_team(team_id)
    return jsonify(result)

@app.route('/api/delete-player/<int:player_id>', methods=['POST'])
@login_required
def api_delete_player(player_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('DELETE FROM players WHERE id = %s', (player_id,))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'success': True, 'message': 'Player deleted'})

@app.route('/api/scrape-player-profile/<int:player_id>', methods=['POST'])
@login_required
def api_scrape_player_profile(player_id):
    from scraper import scrape_player_profile
    result = scrape_player_profile(player_id)
    return jsonify(result)

@app.route('/api/get-players/<int:team_id>')
@login_required
def api_get_players(team_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM players WHERE team_id = %s ORDER BY role, name', (team_id,))
    players = cur.fetchall()
    cur.close()
    conn.close()
    players_list = []
    for p in players:
        players_list.append({
            'id': p['id'],
            'name': p['name'],
            'role': p['role'],
            'image_url': p['image_url'],
            'profile_url': p.get('profile_url', ''),
            'profile_scraped': p.get('profile_scraped', False)
        })
    return jsonify({'success': True, 'players': players_list})

@app.route('/team/<slug>')
def team_detail_page(slug):
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute('SELECT * FROM teams WHERE slug = %s AND is_published = TRUE', (slug,))
    team = cur.fetchone()
    
    if not team:
        cur.close()
        conn.close()
        return "Team not found", 404
    
    cur.execute('SELECT * FROM players WHERE team_id = %s ORDER BY role, name', (team['id'],))
    all_players = cur.fetchall()
    
    players_by_role = {
        'Batsmen': [],
        'All Rounder': [],
        'Wicket Keeper': [],
        'Bowler': [],
        'Unknown': []
    }
    role_mapping = {
        'Batter': 'Batsmen',
        'Bowler': 'Bowler',
        'All-Rounder': 'All Rounder',
        'Wicket-Keeper': 'Wicket Keeper'
    }
    for player in all_players:
        role = player.get('role') or 'Unknown'
        mapped_role = role_mapping.get(role, 'Unknown')
        if mapped_role in players_by_role:
            players_by_role[mapped_role].append(player)
        else:
            players_by_role['Unknown'].append(player)
    
    cur.close()
    conn.close()
    
    settings = get_site_settings()
    return render_template('frontend/team_detail.html', team=team, players_by_role=players_by_role, settings=settings)

@app.route('/player/<slug>')
def player_detail_page(slug):
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute('SELECT p.*, t.name as team_name, t.slug as team_slug FROM players p LEFT JOIN teams t ON p.team_id = t.id WHERE p.slug = %s', (slug,))
    player = cur.fetchone()
    
    if not player:
        cur.close()
        conn.close()
        return "Player not found", 404
    
    cur.close()
    conn.close()
    
    settings = get_site_settings()
    return render_template('frontend/player_detail.html', player=player, settings=settings)

@app.route('/cricket-teams')
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

@app.route('/cricket-series')
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

@app.route('/cricket-series/<slug>')
@app.route('/series/<slug>')
def series_detail_page(slug):
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute('SELECT * FROM series WHERE slug = %s', (slug,))
    series = cur.fetchone()
    
    if not series:
        cur.close()
        conn.close()
        return "Series not found", 404
    
    cur.execute('SELECT * FROM matches WHERE series_id = %s ORDER BY match_id ASC', (series['id'],))
    matches = cur.fetchall()
    
    cur.close()
    conn.close()
    
    settings = get_site_settings()
    return render_template('frontend/series_detail.html', series=series, matches=matches, settings=settings)

@app.route('/series/<int:series_id>')
def series_detail_redirect(series_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT slug FROM series WHERE id = %s', (series_id,))
    series = cur.fetchone()
    cur.close()
    conn.close()
    if series and series.get('slug'):
        return redirect(f"/cricket-series/{series['slug']}", code=301)
    return "Series not found", 404

@app.route('/cricket-match/<slug>')
def match_score_page(slug):
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute('SELECT * FROM matches WHERE slug = %s', (slug,))
    match = cur.fetchone()
    
    scorecard = None
    if match:
        cur.execute('SELECT * FROM scorecards WHERE match_id = %s', (str(match.get('match_id', '')),))
        scorecard = cur.fetchone()
    
    cur.close()
    conn.close()
    
    settings = get_site_settings()
    return render_template('frontend/match_score.html', scorecard=scorecard, match=match, settings=settings)

@app.route('/match-score/<int:match_id>')
def match_score_by_id(match_id):
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute('SELECT * FROM matches WHERE match_id = %s', (str(match_id),))
    match = cur.fetchone()
    
    scorecard = None
    if match:
        cur.execute('SELECT * FROM scorecards WHERE match_id = %s', (str(match_id),))
        scorecard = cur.fetchone()
    
    cur.close()
    conn.close()
    
    if not match:
        return "Match not found", 404
    
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
    
    conn = get_db()
    cur = conn.cursor()
    
    pages = [
        ('/', '1.0', 'daily'),
        ('/cricket-series', '0.9', 'daily'),
        ('/cricket-teams', '0.9', 'weekly'),
        ('/players', '0.9', 'daily'),
        ('/page/about', '0.8', 'monthly'),
        ('/page/contact', '0.8', 'monthly'),
        ('/page/privacy-policy', '0.6', 'monthly'),
        ('/page/disclaimer', '0.6', 'monthly'),
        ('/page/terms', '0.6', 'monthly'),
    ]
    
    try:
        cur.execute('SELECT slug FROM series WHERE slug IS NOT NULL AND slug != %s', ('',))
        for s in cur.fetchall():
            pages.append((f"/cricket-series/{s['slug']}", '0.8', 'daily'))
        
        cur.execute('SELECT slug FROM matches WHERE slug IS NOT NULL AND slug != %s', ('',))
        for m in cur.fetchall():
            pages.append((f"/cricket-match/{m['slug']}", '0.7', 'daily'))
        
        cur.execute('SELECT slug FROM teams WHERE slug IS NOT NULL AND slug != %s', ('',))
        for t in cur.fetchall():
            pages.append((f"/team/{t['slug']}", '0.8', 'weekly'))
        
        cur.execute('SELECT slug FROM players WHERE slug IS NOT NULL AND slug != %s', ('',))
        for p in cur.fetchall():
            pages.append((f"/player/{p['slug']}", '0.7', 'weekly'))
        
        cur.execute('SELECT slug FROM posts WHERE is_published = true AND slug IS NOT NULL')
        for post in cur.fetchall():
            pages.append((f"/post/{post['slug']}", '0.8', 'weekly'))
        
        cur.execute('SELECT slug FROM post_categories WHERE is_published = true AND slug IS NOT NULL')
        for cat in cur.fetchall():
            pages.append((f"/category/{cat['slug']}", '0.8', 'weekly'))
        
        cur.execute('SELECT slug FROM matchups WHERE is_published = true AND slug IS NOT NULL')
        for mu in cur.fetchall():
            pages.append((f"/match/{mu['slug']}", '0.9', 'daily'))
    except:
        pass
    
    cur.close()
    conn.close()
    
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    
    settings = get_site_settings()
    base_url = settings.get('site_url', 'https://cricbuzz-live-score.com').rstrip('/')
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

@app.route('/admin/generate-sitemap')
@login_required
def admin_generate_sitemap():
    flash('Sitemap regenerated successfully! Visit /sitemap.xml to view.', 'success')
    return redirect(url_for('admin_settings'))

with app.app_context():
    init_db()
    seed_defaults()

if __name__ == '__main__':
    if not os.environ.get('WERKZEUG_RUN_MAIN'):
        start_scheduler()
    app.run(host='0.0.0.0', port=5000, debug=True)
