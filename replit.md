# Cricket Scraper Website

## Overview
A Python/Flask-based cricket data scraping website that scrapes series and match data from cricbuzz.com and stores it in a PostgreSQL database. Uses pure Python (requests + BeautifulSoup) for all scraping - no external APIs required.

## Project Structure
```
/
├── app.py              # Main Flask application
├── scraper.py          # Scraping functions (pure Python, no external API)
├── templates/
│   ├── admin.html      # Admin panel main page
│   ├── matches_page.html # View matches for a series
│   ├── scorecard.html  # Scorecard viewing page
│   └── live_score.html # Live score page
├── static/
│   └── style.css       # Admin panel styling
└── replit.md           # Project documentation
```

## Database Schema
### Series Table
- id: Auto-increment primary key
- month: Month name (e.g., January)
- year: Year (e.g., 2025)
- series_name: Name of the cricket series
- date_range: Date range when series runs
- series_url: URL to the series matches page

### Matches Table
- id: Auto-increment primary key
- series_id: Foreign key to series table
- match_id: Cricbuzz match ID (extracted from URL)
- match_title: Title of the match
- match_url: Full URL to the match page
- match_date: Date of the match

### Scorecards Table
- id: Auto-increment primary key
- match_id: Cricbuzz match ID (unique)
- match_title: Title of the match
- match_status: Current match status
- scorecard_html: Full HTML of the scraped scorecard
- scraped_at: Timestamp of when scorecard was scraped

## Features Implemented
1. Series data scraping from cricbuzz.com/cricket-schedule/series/all
2. Match data scraping from individual series pages
3. Scorecard scraping with batting & bowling tables (pure Python)
4. Admin panel with sidebar navigation
5. Smart match filtering using team abbreviations for all cricket nations

## Tech Stack
- Python 3.11 with Flask framework
- PostgreSQL Database
- Jinja2 Templates
- BeautifulSoup4 for HTML parsing
- Requests for HTTP requests
- lxml for faster HTML parsing

## Environment Variables
- DATABASE_URL: PostgreSQL connection string
- SESSION_SECRET: Flask session secret key

## Pages
- GET / - Redirects to admin panel
- GET /admin - Admin panel with series scraping
- GET /matches - View matches page with series selector
- GET /scorecard - Scorecard viewing with series/match selectors
- GET /live-score - Live score page

## API Endpoints
- POST /api/scrape-series - Scrape series data from Cricbuzz
- POST /api/scrape-matches/<series_id> - Scrape matches for a specific series
- POST /api/scrape-all-matches - Scrape matches for all series
- POST /api/scrape-scorecard - Scrape scorecard for a match (saves to database)
- GET /api/matches/<series_id> - Get matches for a series (JSON)
- GET /api/get-scorecard/<match_id> - Get saved scorecard from database
- GET /api/saved-scorecards - List all saved scorecards

## Recent Changes
- January 2026: Added database storage for scorecards with ON CONFLICT UPDATE
- January 2026: Migrated from PHP to Python/Flask framework
- January 2026: Removed ScraperAPI dependency - now uses pure Python requests
- January 2026: Added scorecard scraping with batting/bowling tables
- January 2026: Restructured sidebar navigation with dedicated pages
- January 2026: Fixed HTML parsing for Cricbuzz's Next.js structure
