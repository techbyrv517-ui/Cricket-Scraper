# Cricket Scraper Website

## Overview
A PHP-based cricket data scraping website that scrapes series and match data from cricbuzz.com and stores it in a PostgreSQL database.

## Project Structure
```
/
├── config/
│   ├── database.php    # Database connection
│   └── init_db.php     # Database table initialization
├── admin/
│   ├── index.php       # Admin panel main page
│   ├── scraper.php     # Scraping functions
│   ├── matches.php     # View matches for a series
│   └── style.css       # Admin panel styling
└── index.php           # Redirect to admin panel
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

## Features Implemented
1. Series data scraping from cricbuzz.com/cricket-schedule/series/all
2. Match data scraping from individual series pages (JavaScript-rendered content via ScraperAPI)
3. Admin panel to view and manage scraped data
4. Smart match filtering using team abbreviations for all cricket nations

## Tech Stack
- PHP 8.2
- PostgreSQL Database
- HTML/CSS
- cURL for web scraping
- ScraperAPI for JavaScript rendering (SCRAPER_API_KEY required)

## Environment Variables
- SCRAPER_API_KEY: Required for scraping JavaScript-rendered match data from Cricbuzz
- DATABASE_URL: PostgreSQL connection string

## Recent Changes
- January 2026: Added ScraperAPI integration for JavaScript-rendered content
- January 2026: Fixed match filtering for abbreviated country codes (NZ, IND, etc.)
- January 2026: Added support for 25+ cricket nations (including associate members)
- January 2026: Initial project setup with admin panel and scraping functionality
