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
        
        if not match_id or match_id in processed_match_ids:
            continue
        processed_match_ids.add(match_id)
        
        if title:
            match_title = re.sub(r'\s*-\s*(Preview|Live|Stumps|Result|Scheduled|Need \d+.*)\s*$', '', title).strip()
            match_title = re.sub(r'\s*-\s*Preview\s*$', '', match_title).strip()
        else:
            match_title = link.get_text(strip=True)
        
        match_date = ''
        parent = link.parent
        while parent and parent.name != 'body':
            date_elem = parent.find(string=re.compile(r'(Mon|Tue|Wed|Thu|Fri|Sat|Sun),'))
            if date_elem:
                match_date = date_elem.strip()
                break
            parent = parent.parent
        
        match_url = f"https://www.cricbuzz.com{href}"
        
        if match_title and len(match_title) > 2:
            cur.execute('SELECT id FROM matches WHERE match_id = %s AND series_id = %s', (match_id, series_id))
            if cur.fetchone() is None:
                cur.execute(
                    'INSERT INTO matches (series_id, match_id, match_title, match_url, match_date) VALUES (%s, %s, %s, %s, %s)',
                    (series_id, match_id, match_title, match_url, match_date)
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

def scrape_scorecard(url):
    if not url or 'cricbuzz.com/live-cricket-scorecard' not in url:
        return {'success': False, 'message': 'Invalid scorecard URL'}
    
    api_key = os.environ.get('SCRAPER_API_KEY', '')
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }
    
    try:
        if api_key:
            api_url = f"http://api.scraperapi.com?api_key={api_key}&url={url}&render=true"
            response = requests.get(api_url, timeout=120)
        else:
            response = requests.get(url, headers=headers, timeout=30)
        
        response.raise_for_status()
        html = response.text
    except Exception as e:
        return {'success': False, 'message': f'Error fetching scorecard: {str(e)}'}
    
    soup = BeautifulSoup(html, 'html.parser')
    scorecard_html = ''
    
    match_title = soup.find('h1')
    if match_title:
        scorecard_html += f'<div class="match-header"><h2>{match_title.get_text(strip=True)}</h2></div>'
    
    status_div = soup.find('div', class_=re.compile(r'cb-col-100.*cb-min-stts'))
    if not status_div:
        status_div = soup.find('div', class_=re.compile(r'cb-text-complete|cb-text-live'))
    if status_div:
        scorecard_html += f'<div class="match-status">{status_div.get_text(strip=True)}</div>'
    
    innings_containers = soup.find_all('div', id=re.compile(r'^innings_\d+$'))
    
    for innings in innings_containers:
        team_header = innings.find('div', class_=re.compile(r'cb-col-100.*cb-scrd-hdr-rw'))
        if team_header:
            team_name_el = team_header.find('span')
            team_score_el = team_header.find('span', class_=re.compile(r'pull-right|float-right'))
            team_name = team_name_el.get_text(strip=True) if team_name_el else ''
            team_score = team_score_el.get_text(strip=True) if team_score_el else ''
            scorecard_html += f'<div class="innings-header">{team_name} <span class="innings-score">{team_score}</span></div>'
        
        scorecard_html += '<table class="batting-table"><thead><tr><th>Batter</th><th>Dismissal</th><th>R</th><th>B</th><th>4s</th><th>6s</th><th>SR</th></tr></thead><tbody>'
        
        bat_rows = innings.find_all('div', class_=re.compile(r'cb-col-100.*cb-scrd-itms'))
        for row in bat_rows:
            all_divs = row.find_all('div', recursive=False)
            if len(all_divs) >= 7:
                batter_div = all_divs[0]
                batter_name = batter_div.get_text(strip=True)
                
                if batter_name and batter_name not in ['Extras', 'Total', 'Did not Bat', 'Fall of Wickets', 'Bowler', 'Yet to Bat']:
                    dismissal = all_divs[1].get_text(strip=True) if len(all_divs) > 1 else '-'
                    runs = all_divs[2].get_text(strip=True) if len(all_divs) > 2 else '-'
                    balls = all_divs[3].get_text(strip=True) if len(all_divs) > 3 else '-'
                    fours = all_divs[4].get_text(strip=True) if len(all_divs) > 4 else '-'
                    sixes = all_divs[5].get_text(strip=True) if len(all_divs) > 5 else '-'
                    sr = all_divs[6].get_text(strip=True) if len(all_divs) > 6 else '-'
                    
                    if runs.replace('-','').isdigit() or runs == '-':
                        scorecard_html += f'<tr><td>{batter_name}</td><td class="dismissal">{dismissal}</td><td>{runs}</td><td>{balls}</td><td>{fours}</td><td>{sixes}</td><td>{sr}</td></tr>'
        
        scorecard_html += '</tbody></table>'
        
        extras_row = innings.find('div', string=re.compile(r'Extras'))
        if extras_row:
            extras_parent = extras_row.find_parent('div', class_=re.compile(r'cb-scrd-itms'))
            if extras_parent:
                scorecard_html += f'<div class="extras">{extras_parent.get_text(" ", strip=True)}</div>'
        
        total_row = innings.find('div', string=re.compile(r'^Total$'))
        if total_row:
            total_parent = total_row.find_parent('div', class_=re.compile(r'cb-scrd-itms'))
            if total_parent:
                scorecard_html += f'<div class="total">{total_parent.get_text(" ", strip=True)}</div>'
        
        dnb_row = innings.find('div', string=re.compile(r'Did not Bat'))
        if dnb_row:
            dnb_parent = dnb_row.find_parent('div', class_=re.compile(r'cb-col-100'))
            if dnb_parent:
                scorecard_html += f'<div class="did-not-bat">{dnb_parent.get_text(" ", strip=True)}</div>'
        
        bowling_header = innings.find('div', string=re.compile(r'Bowler'))
        if bowling_header:
            scorecard_html += '<table class="bowling-table"><thead><tr><th>Bowler</th><th>O</th><th>M</th><th>R</th><th>W</th><th>NB</th><th>WD</th><th>ECO</th></tr></thead><tbody>'
            
            bowling_parent = bowling_header.find_parent('div', class_=re.compile(r'cb-scrd-itms'))
            if bowling_parent:
                next_rows = bowling_parent.find_next_siblings('div', class_=re.compile(r'cb-scrd-itms'))
                for brow in next_rows:
                    bcols = brow.find_all('div', recursive=False)
                    if len(bcols) >= 8:
                        bowler_name = bcols[0].get_text(strip=True)
                        if bowler_name and not bowler_name.startswith('Fall'):
                            overs = bcols[1].get_text(strip=True)
                            maidens = bcols[2].get_text(strip=True)
                            bruns = bcols[3].get_text(strip=True)
                            wickets = bcols[4].get_text(strip=True)
                            noballs = bcols[5].get_text(strip=True)
                            wides = bcols[6].get_text(strip=True)
                            eco = bcols[7].get_text(strip=True)
                            scorecard_html += f'<tr><td>{bowler_name}</td><td>{overs}</td><td>{maidens}</td><td>{bruns}</td><td class="wickets">{wickets}</td><td>{noballs}</td><td>{wides}</td><td>{eco}</td></tr>'
            
            scorecard_html += '</tbody></table>'
    
    if not scorecard_html or scorecard_html == '':
        scorecard_html = '<p class="no-data">Scorecard data not available. Match may not have started yet.</p>'
    else:
        scorecard_html = '<div class="scorecard-data">' + scorecard_html + '</div>'
    
    return {'success': True, 'html': scorecard_html}
