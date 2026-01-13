# Cricket Scraper Website

## Overview
A Python/Flask-based cricket data scraping website that scrapes series and match data from cricbuzz.com and stores it in a PostgreSQL database.

## Project Structure
```
/
├── app.py              # Main Flask application
├── scraper.py          # Scraping functions with ScraperAPI integration
├── templates/
│   ├── admin.html      # Admin panel main page
│   └── matches.html    # View matches for a series
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

## Features Implemented
1. Series data scraping from cricbuzz.com/cricket-schedule/series/all
2. Match data scraping from individual series pages (JavaScript-rendered content via ScraperAPI)
3. Admin panel to view and manage scraped data
4. Smart match filtering using team abbreviations for all cricket nations

## Tech Stack
- Python 3.11 with Flask framework
- PostgreSQL Database
- Jinja2 Templates
- BeautifulSoup4 for HTML parsing
- Requests for HTTP requests
- ScraperAPI for JavaScript rendering

## Environment Variables
- SCRAPER_API_KEY: Required for scraping JavaScript-rendered match data from Cricbuzz
- DATABASE_URL: PostgreSQL connection string
- SESSION_SECRET: Flask session secret key

## API Endpoints
- GET / - Redirects to admin panel
- GET /admin - Admin panel with series list
- GET /admin/matches/<series_id> - View matches for a specific series
- POST /api/scrape-series - Scrape series data from Cricbuzz
- POST /api/scrape-matches/<series_id> - Scrape matches for a specific series
- POST /api/scrape-all-matches - Scrape matches for all series

## Recent Changes
- January 2026: Migrated from PHP to Python/Flask framework
- January 2026: Added ScraperAPI integration for JavaScript-rendered content
- January 2026: Fixed match filtering for abbreviated country codes (NZ, IND, etc.)
- January 2026: Added support for 25+ cricket nations (including associate members)
