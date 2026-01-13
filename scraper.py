import os
import re
import time
import requests
from bs4 import BeautifulSoup
import psycopg2
from psycopg2.extras import RealDictCursor

def get_db():
    return psycopg2.connect(os.environ.get('DATABASE_URL'), cursor_factory=RealDictCursor)

def scrape_series_data():
    url = "https://www.cricbuzz.com/cricket-schedule/series/all"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        html = response.text
    except Exception as e:
        return {'success': False, 'message': f'Request error: {str(e)}'}
    
    if not html:
        return {'success': False, 'message': 'Empty response from website'}
    
    soup = BeautifulSoup(html, 'html.parser')
    
    month_pattern = re.compile(r'w-4\/12.*?font-bold')
    month_divs = soup.find_all('div', class_=month_pattern)
    
    month_positions = []
    for div in month_divs:
        text = div.get_text(strip=True)
        parts = text.split()
        if len(parts) >= 2:
            month_positions.append({
                'month': parts[0].capitalize(),
                'year': parts[1],
                'element': div
            })
    
    series_count = 0
    processed_urls = set()
    
    conn = get_db()
    cur = conn.cursor()
    
    series_links = soup.find_all('a', href=re.compile(r'/cricket-series/\d+/'))
    
    for link in series_links:
        href = link.get('href', '')
        title = link.get('title', '')
        
        if not href or '/matches' in href:
            base_url = re.sub(r'/matches$', '', href)
        else:
            base_url = href
        
        if base_url in processed_urls:
            continue
        processed_urls.add(base_url)
        
        series_url = f"https://www.cricbuzz.com{href}"
        if '/matches' not in series_url:
            series_url = series_url.rstrip('/') + '/matches'
        
        name_div = link.find('div', class_=re.compile(r'text-ellipsis'))
        series_name = name_div.get_text(strip=True) if name_div else title
        
        date_div = link.find('div', class_=re.compile(r'text-cbTxtSec'))
        date_range = date_div.get_text(strip=True) if date_div else ''
        date_range = re.sub(r'<!--[^>]*-->', '', date_range).strip()
        
        series_month = 'January'
        series_year = '2026'
        
        if series_name:
            cur.execute('SELECT id FROM series WHERE series_url = %s', (series_url,))
            if cur.fetchone() is None:
                cur.execute(
                    'INSERT INTO series (month, year, series_name, date_range, series_url) VALUES (%s, %s, %s, %s, %s)',
                    (series_month, series_year, series_name, date_range, series_url)
                )
                series_count += 1
    
    conn.commit()
    cur.close()
    conn.close()
    
    return {'success': True, 'message': f'Successfully scraped {series_count} new series'}

def scrape_matches_from_series(series_id):
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute('SELECT series_url, series_name FROM series WHERE id = %s', (series_id,))
    series = cur.fetchone()
    
    if not series:
        cur.close()
        conn.close()
        return {'success': False, 'message': 'Series not found'}
    
    url = series['series_url']
    series_name = series['series_name']
    
    match = re.search(r'cricket-series/(\d+)/([^/]+)', url)
    series_slug = match.group(2) if match else ''
    
    scraper_api_key = os.environ.get('SCRAPER_API_KEY')
    
    if scraper_api_key:
        api_url = f"https://api.scraperapi.com/?api_key={scraper_api_key}&url={requests.utils.quote(url)}&render=true"
        try:
            response = requests.get(api_url, timeout=120)
            html = response.text
        except Exception as e:
            return {'success': False, 'message': f'ScraperAPI error: {str(e)}'}
    else:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        try:
            response = requests.get(url, headers=headers, timeout=30)
            html = response.text
        except Exception as e:
            return {'success': False, 'message': f'Request error: {str(e)}'}
    
    if not html:
        cur.close()
        conn.close()
        return {'success': False, 'message': 'Empty response from website'}
    
    country_abbrevs = {
        'india': 'ind', 'new zealand': 'nz', 'australia': 'aus',
        'england': 'eng', 'pakistan': 'pak', 'south africa': 'sa',
        'sri lanka': 'sl', 'bangladesh': 'ban', 'west indies': 'wi',
        'afghanistan': 'afg', 'zimbabwe': 'zim', 'ireland': 'ire',
        'uae': 'uae', 'usa': 'usa', 'nepal': 'nep', 'namibia': 'nam',
        'netherlands': 'ned', 'scotland': 'sco', 'oman': 'oman',
        'canada': 'can', 'kenya': 'ken', 'hong kong': 'hk',
        'papua new guinea': 'png', 'bermuda': 'ber', 'jersey': 'jer'
    }
    
    match_count = 0
    processed_match_ids = set()
    
    match_pattern = re.compile(r'href="(/live-cricket-scores/(\d+)/[^"]+)"[^>]*title="([^"]+)"')
    matches = match_pattern.findall(html)
    
    series_name_lower = series_name.lower()
    
    for match_data in matches:
        match_url_path = match_data[0]
        match_id = match_data[1]
        match_title = match_data[2].strip()
        
        match_url = f"https://www.cricbuzz.com{match_url_path}"
        match_url_lower = match_url_path.lower()
        
        match_belongs_to_series = False
        
        if series_slug and series_slug in match_url_path:
            match_belongs_to_series = True
        
        if not match_belongs_to_series:
            teams_found = 0
            for full_name, abbr in country_abbrevs.items():
                if full_name in series_name_lower:
                    if f'{abbr}-' in match_url_lower or f'-{abbr}-' in match_url_lower or match_url_lower.endswith(f'-{abbr}'):
                        teams_found += 1
            
            year_match = re.search(r'(\d{4})', series_slug)
            year_in_url = year_match and year_match.group(1) in match_url_path
            
            if teams_found >= 2:
                match_belongs_to_series = True
            
            if not match_belongs_to_series and 'tour' in series_name_lower:
                if 'tour' in match_url_lower and teams_found >= 1:
                    match_belongs_to_series = True
        
        if not match_belongs_to_series:
            continue
        
        if not match_id or match_id in processed_match_ids:
            continue
        processed_match_ids.add(match_id)
        
        if match_title and len(match_title) > 2:
            cur.execute('SELECT id FROM matches WHERE match_id = %s AND series_id = %s', (match_id, series_id))
            if cur.fetchone() is None:
                cur.execute(
                    'INSERT INTO matches (series_id, match_id, match_title, match_url, match_date) VALUES (%s, %s, %s, %s, %s)',
                    (series_id, match_id, match_title, match_url, '')
                )
                match_count += 1
    
    conn.commit()
    cur.close()
    conn.close()
    
    return {'success': True, 'message': f'Successfully scraped {match_count} new matches'}

def scrape_all_matches():
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute('SELECT id, series_name FROM series ORDER BY id')
    all_series = cur.fetchall()
    
    cur.close()
    conn.close()
    
    total_matches = 0
    series_processed = 0
    
    for series in all_series:
        result = scrape_matches_from_series(series['id'])
        if result['success']:
            match = re.search(r'(\d+)', result['message'])
            if match:
                total_matches += int(match.group(1))
        series_processed += 1
        time.sleep(0.5)
    
    return {'success': True, 'message': f'Scraped {total_matches} matches from {series_processed} series'}
