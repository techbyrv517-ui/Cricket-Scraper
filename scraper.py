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
    
    is_franchise_league = any(x in series_name_lower for x in ['big bash', 'bbl', 'ipl', 'psl', 'cpl', 'bpl', 'sa20', 't20 league', 'hundred', 'wpl', 'major league'])
    is_womens = 'women' in series_name_lower or 'wpl' in series_name_lower
    is_u19 = 'u19' in series_name_lower or 'under-19' in series_name_lower or 'under 19' in series_name_lower
    
    international_markers = ['odi', 'test', 't20i', '1st-odi', '2nd-odi', '3rd-odi', '1st-test', '2nd-test', '1st-t20i', '2nd-t20i', '3rd-t20i']
    
    def match_belongs_to_series(match_slug, match_title=''):
        match_slug_lower = match_slug.lower()
        match_title_lower = match_title.lower() if match_title else ''
        
        if not is_womens and ('women' in match_slug_lower or 'women' in match_title_lower):
            return False
        if not is_u19 and ('u19' in match_slug_lower or 'u19' in match_title_lower or 'under-19' in match_slug_lower):
            return False
        if is_franchise_league:
            for marker in international_markers:
                if marker in match_slug_lower:
                    return False
        
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
        
        if is_franchise_league:
            other_series_markers = ['ranji', 'vijay-hazare', 'syed-mushtaq', 'sheffield', 'county', 'super-smash', 'ford-trophy']
            for marker in other_series_markers:
                if marker in match_slug_lower:
                    return False
            return True
        
        series_keywords = []
        series_words = series_name_lower.replace('-', ' ').split()
        for word in series_words:
            if len(word) > 2 and word not in ['the', 'and', 'for', 'tour', 'series', 'match', 'cricket', 'league', 'cup', 'trophy', '2024', '2025', '2026']:
                series_keywords.append(word)
        
        if series_keywords:
            for keyword in series_keywords:
                if keyword in match_slug_lower:
                    return True
        
        if series_slug:
            series_slug_words = series_slug.lower().replace('-', ' ').split()
            for word in series_slug_words:
                if len(word) > 3 and word not in ['2024', '2025', '2026'] and word in match_slug_lower:
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
        
        if not match_belongs_to_series(match_slug, title):
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
        
        date_pattern = re.compile(rf'{match_id}[^{{}}]{{0,500}}startDate[\\\":]+(\d{{13}})')
        date_match = date_pattern.search(html)
        if date_match:
            try:
                timestamp = int(date_match.group(1)) / 1000
                from datetime import datetime
                dt = datetime.fromtimestamp(timestamp)
                match_date = dt.strftime('%a, %b %d %Y')
            except:
                pass
        
        if not match_date:
            status_pattern = re.compile(rf'{match_id}[^{{}}]{{0,500}}status[\\\":]+([^"\'\\\\]+)')
            status_match = status_pattern.search(html)
            if status_match:
                status_text = status_match.group(1)
                date_in_status = re.search(r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d+)', status_text)
                if date_in_status:
                    month = date_in_status.group(1)
                    day = date_in_status.group(2)
                    match_date = f"{month} {day}, 2026"
        
        if not match_date:
            date_elem = link.find_previous(string=re.compile(r'(Mon|Tue|Wed|Thu|Fri|Sat|Sun),\s*[A-Za-z]+\s*\d+'))
            if date_elem:
                match_date = date_elem.strip()
        
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
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        html = response.text
    except Exception as e:
        return {'success': False, 'message': f'Error fetching scorecard: {str(e)}'}
    
    soup = BeautifulSoup(html, 'html.parser')
    scorecard_html = ''
    team_scores = []
    
    title = soup.find('title')
    if title:
        title_text = title.get_text(strip=True).replace('Cricket scorecard | ', '').replace(' | Cricbuzz.com', '')
        scorecard_html += f'<div class="match-header"><h2>{title_text}</h2></div>'
    
    status_div = soup.find('div', class_='text-cbComplete')
    status_text = status_div.get_text(strip=True) if status_div else ''
    
    is_live = False
    live_indicators = soup.find_all('div', class_=re.compile(r'text-live|cb-text-live|live-score'))
    if live_indicators:
        is_live = True
    live_text_check = soup.find(string=re.compile(r'\bLive\b|\bIn Progress\b|\bDay \d+\b', re.I))
    if live_text_check and 'won' not in status_text.lower() and 'drawn' not in status_text.lower():
        is_live = True
    if status_text and ('won' in status_text.lower() or 'drawn' in status_text.lower() or 'match' in status_text.lower()):
        is_live = False
    
    innings_divs = soup.find_all('div', id=re.compile(r'^scard-team-\d+-innings-\d+$'))
    
    for innings in innings_divs:
        innings_id = innings.get('id', '')
        header_id = innings_id.replace('scard-', '')
        header_div = soup.find('div', id=header_id)
        
        if header_div:
            team_name = header_div.find('div', class_='font-bold')
            team_score = header_div.find('span', class_='font-bold')
            overs_span = header_div.find_all('span')
            
            team_text = team_name.get_text(strip=True) if team_name else ''
            score_text = team_score.get_text(strip=True) if team_score else ''
            overs_text = overs_span[-1].get_text(strip=True) if len(overs_span) > 1 else ''
            
            if team_text and score_text:
                score_entry = f"{team_text} {score_text}"
                if score_entry not in team_scores:
                    team_scores.append(score_entry)
        
        bat_grids = innings.find_all('div', class_=re.compile(r'scorecard-bat-grid'))
        
        if bat_grids:
            scorecard_html += '<div class="table-scroll"><table class="batting-table"><thead><tr><th>Batter</th><th>R</th><th>B</th><th>4s</th><th>6s</th><th>SR</th></tr></thead><tbody>'
            
            for grid in bat_grids:
                player_link = grid.find('a', href=re.compile(r'/profiles/'))
                if player_link:
                    batter_name = player_link.get_text(strip=True)
                    
                    dismissal_div = grid.find('div', class_='text-cbTxtSec')
                    dismissal = dismissal_div.get_text(strip=True) if dismissal_div else 'not out'
                    
                    all_divs = grid.find_all('div', recursive=False)
                    runs = all_divs[1].get_text(strip=True) if len(all_divs) > 1 else '-'
                    balls = all_divs[2].get_text(strip=True) if len(all_divs) > 2 else '-'
                    fours = all_divs[3].get_text(strip=True) if len(all_divs) > 3 else '-'
                    sixes = all_divs[4].get_text(strip=True) if len(all_divs) > 4 else '-'
                    sr = all_divs[5].get_text(strip=True) if len(all_divs) > 5 else '-'
                    
                    scorecard_html += f'<tr><td><div class="batter-name">{batter_name}</div><div class="dismissal-text">{dismissal}</div></td><td>{runs}</td><td>{balls}</td><td>{fours}</td><td>{sixes}</td><td>{sr}</td></tr>'
            
            scorecard_html += '</tbody></table></div>'
        
        extras_div = innings.find('div', class_='font-bold', string='Extras')
        if extras_div:
            extras_parent = extras_div.find_parent('div', class_='flex')
            if extras_parent:
                extras_val = extras_parent.find_all('span')
                if extras_val:
                    extras_text = ' '.join([s.get_text(strip=True) for s in extras_val])
                    scorecard_html += f'<div class="extras">Extras: {extras_text}</div>'
        
        total_div = innings.find('div', class_='font-bold', string='Total')
        if total_div:
            total_parent = total_div.find_parent('div', class_='flex')
            if total_parent:
                total_spans = total_parent.find_all('span')
                if total_spans:
                    total_text = ' '.join([s.get_text(strip=True) for s in total_spans])
                    scorecard_html += f'<div class="total">Total: {total_text}</div>'
        
        dnb_div = innings.find('div', class_='font-bold', string='Did not Bat')
        if dnb_div:
            dnb_parent = dnb_div.find_parent('div', class_='flex')
            if dnb_parent:
                dnb_links = dnb_parent.find_all('a')
                if dnb_links:
                    dnb_names = ', '.join([a.get_text(strip=True) for a in dnb_links])
                    scorecard_html += f'<div class="did-not-bat">Did not bat: {dnb_names}</div>'
        
        bowl_grids = innings.find_all('div', class_=re.compile(r'scorecard-bowl-grid'))
        
        if bowl_grids:
            scorecard_html += '<div class="table-scroll"><table class="bowling-table"><thead><tr><th>Bowler</th><th>O</th><th>M</th><th>R</th><th>W</th><th>NB</th><th>WD</th><th>ECO</th></tr></thead><tbody>'
            
            for grid in bowl_grids:
                bowler_link = grid.find('a', href=re.compile(r'/profiles/'))
                if bowler_link:
                    bowler_name = bowler_link.get_text(strip=True)
                    
                    all_divs = grid.find_all('div', recursive=False)
                    overs = all_divs[0].get_text(strip=True) if len(all_divs) > 0 else '-'
                    maidens = all_divs[1].get_text(strip=True) if len(all_divs) > 1 else '-'
                    bruns = all_divs[2].get_text(strip=True) if len(all_divs) > 2 else '-'
                    wickets = all_divs[3].get_text(strip=True) if len(all_divs) > 3 else '-'
                    noballs = all_divs[4].get_text(strip=True) if len(all_divs) > 4 else '-'
                    wides = all_divs[5].get_text(strip=True) if len(all_divs) > 5 else '-'
                    eco = all_divs[6].get_text(strip=True) if len(all_divs) > 6 else '-'
                    
                    scorecard_html += f'<tr><td>{bowler_name}</td><td>{overs}</td><td>{maidens}</td><td>{bruns}</td><td class="wickets">{wickets}</td><td>{noballs}</td><td>{wides}</td><td>{eco}</td></tr>'
            
            scorecard_html += '</tbody></table></div>'
    
    final_score = ' vs '.join(team_scores) if team_scores else ''
    
    match_summary = ''
    if status_text or team_scores:
        scores_html = ' | '.join([f'<span class="team-score-item">{s}</span>' for s in team_scores])
        match_summary = f'<div class="match-summary"><div class="match-summary-left">{status_text}</div><div class="match-summary-right">{scores_html}</div></div>'
    
    if not scorecard_html or '<table' not in scorecard_html:
        scorecard_html = '<p class="no-data">Scorecard data not available. Match may not have started yet or the page structure has changed.</p>'
    else:
        scorecard_html = match_summary + '<div class="scorecard-data">' + scorecard_html + '</div>'
    
    return {'success': True, 'html': scorecard_html, 'final_score': final_score, 'is_live': is_live, 'status_text': status_text}

def scrape_teams(team_type='international'):
    urls = {
        'international': 'https://www.cricbuzz.com/cricket-team',
        'domestic': 'https://www.cricbuzz.com/cricket-team/domestic',
        'league': 'https://www.cricbuzz.com/cricket-team/league',
        'women': 'https://www.cricbuzz.com/cricket-team/women'
    }
    
    url = urls.get(team_type, urls['international'])
    
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
    
    team_count = 0
    conn = get_db()
    cur = conn.cursor()
    
    team_containers = soup.find_all('a', href=re.compile(r'/cricket-team/[^/]+/\d+'))
    
    for container in team_containers:
        href = container.get('href', '')
        if not href:
            continue
        
        team_match = re.search(r'/cricket-team/([^/]+)/(\d+)', href)
        if not team_match:
            continue
        
        team_slug = team_match.group(1)
        team_id = team_match.group(2)
        
        team_name = container.get_text(strip=True)
        if not team_name or len(team_name) < 2:
            continue
        
        img = container.find('img')
        flag_url = ''
        if img and img.get('src'):
            flag_url = img.get('src')
            if flag_url.startswith('//'):
                flag_url = 'https:' + flag_url
        
        if not flag_url:
            parent = container.parent
            if parent:
                img = parent.find('img')
                if img and img.get('src'):
                    flag_url = img.get('src')
                    if flag_url.startswith('//'):
                        flag_url = 'https:' + flag_url
        
        short_name = team_name[:3].upper() if len(team_name) >= 3 else team_name.upper()
        
        color_map = {
            'india': '#FF9933', 'pakistan': '#01411C', 'australia': '#FFCD00',
            'england': '#002366', 'new-zealand': '#000000', 'south-africa': '#007A4D',
            'sri-lanka': '#0033A0', 'bangladesh': '#006A4E', 'afghanistan': '#000000',
            'west-indies': '#7B0041', 'zimbabwe': '#FCE300', 'ireland': '#169B62',
            'netherlands': '#FF6600', 'scotland': '#0065BF', 'nepal': '#DC143C'
        }
        flag_color = color_map.get(team_slug.lower(), '#046A38')
        
        cricbuzz_team_id = team_id
        
        cur.execute('SELECT id, flag_url, cricbuzz_team_id FROM teams WHERE slug = %s', (team_slug,))
        existing = cur.fetchone()
        if existing is None:
            cur.execute('''
                INSERT INTO teams (name, short_name, slug, country, flag_color, flag_url, team_type, cricbuzz_team_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ''', (team_name, short_name, team_slug, team_name, flag_color, flag_url, team_type, cricbuzz_team_id))
            team_count += 1
        else:
            if flag_url and (not existing.get('flag_url')):
                cur.execute('UPDATE teams SET flag_url = %s WHERE slug = %s', (flag_url, team_slug))
            if cricbuzz_team_id and (not existing.get('cricbuzz_team_id')):
                cur.execute('UPDATE teams SET cricbuzz_team_id = %s WHERE slug = %s', (cricbuzz_team_id, team_slug))
            team_count += 1
    
    conn.commit()
    cur.close()
    conn.close()
    
    return {'success': True, 'message': f'Successfully scraped {team_count} {team_type} teams'}

def scrape_players_from_team(team_id):
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute('SELECT id, name, slug, cricbuzz_team_id FROM teams WHERE id = %s', (team_id,))
    team = cur.fetchone()
    
    if not team:
        cur.close()
        conn.close()
        return {'success': False, 'message': 'Team not found'}
    
    team_slug = team['slug']
    team_name = team['name']
    cricbuzz_id = team.get('cricbuzz_team_id')
    
    if not cricbuzz_id:
        cur.close()
        conn.close()
        return {'success': False, 'message': 'Cricbuzz team ID not found. Please re-scrape teams first.'}
    
    url = f"https://www.cricbuzz.com/cricket-team/{team_slug}/{cricbuzz_id}/players"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    }
    
    scraper_api_key = os.environ.get('SCRAPER_API_KEY')
    
    try:
        if scraper_api_key:
            api_url = f"http://api.scraperapi.com?api_key={scraper_api_key}&url={url}"
            response = requests.get(api_url, timeout=60)
        else:
            response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        html = response.text
    except Exception as e:
        cur.close()
        conn.close()
        return {'success': False, 'message': f'Request error: {str(e)}'}
    
    soup = BeautifulSoup(html, 'lxml')
    
    player_count = 0
    
    html_str = str(soup)
    
    role_positions = []
    role_patterns = [
        (r'(?i)>BATTER[S]?<|>Batter[s]?<', 'Batter'),
        (r'(?i)>ALL[ -]?ROUNDER[S]?<|>All[ -]?Rounder[s]?<', 'All-Rounder'),
        (r'(?i)>WICKET[ -]?KEEPER[S]?<|>Wicket[ -]?Keeper[s]?<|>WK<', 'Wicket-Keeper'),
        (r'(?i)>BOWLER[S]?<|>Bowler[s]?<', 'Bowler'),
    ]
    
    for pattern, role in role_patterns:
        for m in re.finditer(pattern, html_str):
            role_positions.append((m.start(), role))
    
    role_positions.sort(key=lambda x: x[0])
    
    player_links = soup.find_all('a', href=re.compile(r'/profiles/\d+/'))
    
    for link in player_links:
        href = link.get('href', '')
        player_match = re.search(r'/profiles/(\d+)/([^/]+)', href)
        
        if not player_match:
            continue
        
        cricbuzz_id = player_match.group(1)
        player_slug = player_match.group(2)
        
        player_name = ''
        name_elem = link.find(class_=re.compile(r'cb-font-16'))
        if name_elem:
            player_name = name_elem.get_text(strip=True)
        if not player_name:
            player_name = link.get_text(strip=True)
        
        if not player_name or len(player_name) < 2:
            continue
        
        link_html = str(link)
        link_pos = html_str.find(link_html)
        
        current_role = 'Batter'
        for pos, role in role_positions:
            if pos < link_pos:
                current_role = role
            else:
                break
        
        img = link.find('img')
        image_url = ''
        if img and img.get('src'):
            image_url = img.get('src')
            if image_url.startswith('//'):
                image_url = 'https:' + image_url
        
        profile_url = f"https://www.cricbuzz.com/profiles/{cricbuzz_id}/{player_slug}"
        
        cur.execute('SELECT id FROM players WHERE cricbuzz_id = %s AND team_id = %s', (cricbuzz_id, team_id))
        if cur.fetchone() is None:
            cur.execute('''
                INSERT INTO players (team_id, cricbuzz_id, name, slug, image_url, role, profile_url)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            ''', (team_id, cricbuzz_id, player_name, player_slug, image_url, current_role, profile_url))
            player_count += 1
    
    conn.commit()
    cur.close()
    conn.close()
    
    return {'success': True, 'message': f'Successfully scraped {player_count} players for {team_name}'}


def scrape_player_profile(player_id):
    import json
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute('SELECT id, name, cricbuzz_id, slug, profile_url FROM players WHERE id = %s', (player_id,))
    player = cur.fetchone()
    
    if not player:
        cur.close()
        conn.close()
        return {'success': False, 'message': 'Player not found'}
    
    profile_url = player.get('profile_url')
    if not profile_url:
        profile_url = f"https://www.cricbuzz.com/profiles/{player['cricbuzz_id']}/{player['slug']}"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    }
    
    scraper_api_key = os.environ.get('SCRAPER_API_KEY')
    
    try:
        if scraper_api_key:
            api_url = f"http://api.scraperapi.com?api_key={scraper_api_key}&url={profile_url}"
            response = requests.get(api_url, timeout=60)
        else:
            response = requests.get(profile_url, headers=headers, timeout=30)
        response.raise_for_status()
        html = response.text
    except Exception as e:
        cur.close()
        conn.close()
        return {'success': False, 'message': f'Request error: {str(e)}'}
    
    soup = BeautifulSoup(html, 'lxml')
    
    personal_info = {}
    batting_stats = {}
    bowling_stats = {}
    
    info_rows = soup.find_all('div', class_=re.compile(r'.*w-full.*bg-white.*flex.*'))
    for row in info_rows:
        label_div = row.find('div', class_=re.compile(r'.*w-1/3.*'))
        value_div = row.find('div', class_=re.compile(r'.*w-2/3.*'))
        if label_div and value_div:
            label = label_div.get_text(strip=True)
            value = value_div.get_text(strip=True)
            if label and value and len(label) < 30:
                personal_info[label] = value
    
    formats = ['Test', 'ODI', 'T20I', 'IPL']
    batting_stats = {fmt: {} for fmt in formats}
    bowling_stats = {fmt: {} for fmt in formats}
    
    career_divs = soup.find_all('div', class_=re.compile(r'.*flex.*flex-col.*'))
    for div in career_divs:
        header_div = div.find('div', string=re.compile(r'.*(Batting|Bowling).*Career.*Summary.*', re.I))
        if not header_div:
            header_text = div.get_text()[:100]
            is_bowling_section = 'Bowling Career' in header_text
            is_batting_section = 'Batting Career' in header_text
        else:
            header_text = header_div.get_text()
            is_bowling_section = 'Bowling' in header_text
            is_batting_section = 'Batting' in header_text
        
        if not is_batting_section and not is_bowling_section:
            continue
        
        table = div.find('table')
        if not table:
            continue
        
        rows = table.find_all('tr')
        for row in rows:
            cells = row.find_all('td')
            if len(cells) >= 5:
                stat_name = cells[0].get_text(strip=True)
                for i, fmt in enumerate(formats):
                    if i + 1 < len(cells):
                        val = cells[i + 1].get_text(strip=True)
                        if is_bowling_section:
                            bowling_stats[fmt][stat_name] = val
                        else:
                            batting_stats[fmt][stat_name] = val
    
    batting_stats = {k: v for k, v in batting_stats.items() if v}
    bowling_stats = {k: v for k, v in bowling_stats.items() if v}
    
    career_timeline = []
    timeline_div = soup.find('div', string=re.compile(r'Career Timeline', re.I))
    if timeline_div:
        timeline_container = timeline_div.find_parent('div', class_=re.compile(r'.*bg-white.*'))
        if timeline_container:
            timeline_rows = timeline_container.find_all('div', class_=re.compile(r'grid.*grid-cols-12.*border-b.*'))
            for row in timeline_rows:
                cols = row.find_all(['div', 'a'])
                if len(cols) >= 3:
                    format_div = row.find('div', class_=re.compile(r'.*uppercase.*'))
                    if format_div:
                        format_name = format_div.get_text(strip=True).upper()
                        debut_link = cols[1] if len(cols) > 1 else None
                        last_link = cols[2] if len(cols) > 2 else None
                        debut_text = debut_link.get_text(strip=True) if debut_link else ''
                        last_text = last_link.get_text(strip=True) if last_link else ''
                        if format_name and (debut_text or last_text):
                            career_timeline.append({
                                'format': format_name,
                                'debut': debut_text,
                                'last_match': last_text
                            })
    
    cur.execute('''
        UPDATE players 
        SET personal_info = %s, batting_stats = %s, bowling_stats = %s, career_timeline = %s, profile_scraped = TRUE
        WHERE id = %s
    ''', (json.dumps(personal_info), json.dumps(batting_stats), json.dumps(bowling_stats), json.dumps(career_timeline), player_id))
    
    conn.commit()
    cur.close()
    conn.close()
    
    return {'success': True, 'message': f'Profile scraped for {player["name"]}'}
