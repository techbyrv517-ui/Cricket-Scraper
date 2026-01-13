import os
from flask import Flask, render_template, request, jsonify, redirect, url_for
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('SESSION_SECRET', 'dev-secret-key')

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
    
    conn.commit()
    cur.close()
    conn.close()

@app.route('/')
def index():
    return redirect(url_for('admin'))

@app.route('/admin')
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
    sidebar = get_sidebar_data()
    return render_template('scorecard.html', sidebar=sidebar)

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

with app.app_context():
    init_db()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
