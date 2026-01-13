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
    
    series_count = 0
    processed_urls = set()
    
    conn = get_db()
    cur = conn.cursor()
    
    month_divs = soup.find_all('div', class_=re.compile(r'w-4/12.*font-bold'))
    
    for month_div in month_divs:
        month_text = month_div.get_text(strip=True).lower()
        
        parts = month_text.split()
        if len(parts) >= 2:
            series_month = parts[0].capitalize()
            series_year = parts[1]
        else:
            series_month = 'January'
            series_year = '2026'
        
        parent_row = month_div.parent
        if not parent_row:
            continue
        
        series_container = parent_row.find('div', class_='w-full')
        if not series_container:
            continue
        
        series_links = series_container.find_all('a', href=re.compile(r'/cricket-series/\d+/'))
        
        for link in series_links:
            href = link.get('href', '')
            
            if not href:
                continue
            
            if href in processed_urls:
                continue
            processed_urls.add(href)
            
            if '/matches' in href:
                series_url = f"https://www.cricbuzz.com{href}"
            else:
                series_url = f"https://www.cricbuzz.com{href}/matches"
            
            full_text = link.get_text(strip=True)
            
            date_match = re.search(r'([A-Z][a-z]{2}\s*\d{1,2}\s*-\s*[A-Z][a-z]{2}\s*\d{1,2})', full_text)
            if date_match:
                date_range = date_match.group(1)
                series_name = full_text.replace(date_match.group(0), '').strip()
            else:
                date_range = ''
                series_name = full_text
            
            series_id_match = re.search(r'/cricket-series/(\d+)/', href)
            cricbuzz_series_id = series_id_match.group(1) if series_id_match else ''
            
            if series_name and len(series_name) > 2:
                cur.execute('SELECT id FROM series WHERE series_url = %s', (series_url,))
                if cur.fetchone() is None:
                    cur.execute(
                        'INSERT INTO series (series_id, month, year, series_name, date_range, series_url) VALUES (%s, %s, %s, %s, %s, %s)',
                        (cricbuzz_series_id, series_month, series_year, series_name, date_range, series_url)
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
    
    country_map = {
        'india': ['ind', 'india', 'indian'],
        'new zealand': ['nz', 'new-zealand', 'newzealand'],
        'australia': ['aus', 'australia', 'australian'],
        'england': ['eng', 'england', 'english'],
        'pakistan': ['pak', 'pakistan'],
        'south africa': ['sa', 'south-africa', 'southafrica'],
        'sri lanka': ['sl', 'sri-lanka', 'srilanka'],
        'bangladesh': ['ban', 'bangladesh'],
        'west indies': ['wi', 'west-indies', 'westindies', 'windies'],
        'afghanistan': ['afg', 'afghanistan'],
        'zimbabwe': ['zim', 'zimbabwe'],
        'ireland': ['ire', 'ireland'],
        'uae': ['uae', 'emirates'],
        'usa': ['usa', 'united-states'],
        'nepal': ['nep', 'nepal'],
        'namibia': ['nam', 'namibia'],
        'netherlands': ['ned', 'netherlands', 'dutch'],
        'scotland': ['sco', 'scotland'],
        'oman': ['oman'],
        'canada': ['can', 'canada'],
    }
    
    series_name_lower = series_name.lower()
    series_teams = []
    for country, aliases in country_map.items():
        if country in series_name_lower:
            series_teams.append(aliases)
    
    def match_belongs_to_series(match_slug):
        match_slug_lower = match_slug.lower()
        
        if series_slug and series_slug.lower() in match_slug_lower:
            return True
        
        if len(series_teams) >= 2:
            teams_found = 0
            for team_aliases in series_teams:
                for alias in team_aliases:
                    if alias in match_slug_lower:
                        teams_found += 1
                        break
            if teams_found >= 2:
                return True
        
        if len(series_teams) == 1:
            for alias in series_teams[0]:
                if alias in match_slug_lower:
                    return True
        
        if 'icc' in series_name_lower or 'world cup' in series_name_lower or 'league' in series_name_lower:
            return True
        
        return False
    
    match_count = 0
    processed_match_ids = set()
    
    soup = BeautifulSoup(html, 'html.parser')
    
    match_links = soup.find_all('a', href=re.compile(r'/live-cricket-scores/\d+/'))
    
    for link in match_links:
        href = link.get('href', '')
        title = link.get('title', '')
        
        if not href:
            continue
        
        match_id_search = re.search(r'/live-cricket-scores/(\d+)/([^?]+)', href)
        if not match_id_search:
            continue
        
        match_id = match_id_search.group(1)
        match_slug = match_id_search.group(2)
        
        if not match_belongs_to_series(match_slug):
            continue
        
        if not title:
            title = link.get_text(strip=True)
        
        if not match_id or match_id in processed_match_ids:
            continue
        processed_match_ids.add(match_id)
        
        match_url = f"https://www.cricbuzz.com{href}"
        match_title = title.strip() if title else ''
        
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
