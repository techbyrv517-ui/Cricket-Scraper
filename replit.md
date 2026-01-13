# Cricbuzz Live Score - Cricket Data Website

## Overview
A full-featured cricket data website with Cricbuzz-style frontend, admin panel with authentication, and advanced SEO optimization. Scrapes series, match, and scorecard data from cricbuzz.com using pure Python (requests + BeautifulSoup).

**Website:** https://cricbuzz-live-score.com  
**Name:** Cricbuzz Live Score

## Project Structure
```
/
├── app.py                          # Main Flask application
├── scraper.py                      # Scraping functions (pure Python)
├── templates/
│   ├── admin.html                  # Admin panel base template
│   ├── admin/
│   │   ├── login.html              # Admin login page
│   │   ├── settings.html           # Site settings management
│   │   ├── pages.html              # Pages list
│   │   └── edit_page.html          # Edit page content
│   ├── frontend/
│   │   ├── base.html               # Frontend base template with SEO
│   │   ├── home.html               # Homepage with matchups
│   │   ├── page.html               # Static pages (About, Contact, etc.)
│   │   └── keyword_page.html       # SEO keyword landing pages
│   ├── matches_page.html           # View matches for a series
│   ├── scorecard.html              # Scorecard viewing page
│   └── live_score.html             # Live score page
├── static/
│   └── style.css                   # Admin panel styling
└── replit.md                       # Project documentation
```

## Database Schema

### Users Table
- id: Auto-increment primary key
- username: Unique username
- password_hash: Hashed password (werkzeug)
- role: User role (admin)
- created_at: Account creation timestamp
- last_login: Last login timestamp

### Site Settings Table
- id: Auto-increment primary key
- setting_key: Unique setting name
- setting_value: Setting value
- updated_at: Last update timestamp

### Pages Table (AdSense)
- id: Auto-increment primary key
- slug: URL slug (about, contact, privacy-policy, disclaimer, terms)
- title: Page title
- content: HTML content
- meta_title: SEO meta title
- meta_description: SEO meta description
- is_published: Published status
- created_at, updated_at: Timestamps

### Keyword Pages Table (SEO)
- id: Auto-increment primary key
- keyword: Full keyword (India vs Pakistan)
- short_keyword: Short form (Ind vs Pak)
- slug: URL slug (india-vs-pakistan)
- hero_title, hero_description: Hero section content
- content: Page content
- meta_title, meta_description: SEO meta tags
- is_published: Published status

### Series Table
- id, series_id, month, year, series_name, date_range, series_url

### Matches Table
- id, series_id, match_id, match_title, match_url, match_date

### Scorecards Table
- id, match_id, match_title, match_status, scorecard_html, scraped_at

### Posts Table (Sidebar)
- id: Auto-increment primary key
- title: Post title
- slug: URL slug (auto-generated, unique)
- featured_image: Image URL
- excerpt: Short description for sidebar
- content: Full post content (HTML)
- category: Post category
- meta_title, meta_description: SEO meta tags
- is_published: Published status
- created_at, updated_at: Timestamps

## Features

### Frontend (Public)
1. Cricbuzz-style responsive design
2. Dynamic header/footer from admin settings
3. Homepage with popular matchups
4. SEO keyword landing pages (India vs Pakistan, etc.)
5. 5 AdSense-required static pages

### Admin Panel
1. Secure login with password hashing
2. Site settings management (name, URL, tagline)
3. Theme color customization (primary, secondary, accent)
4. Dynamic header/footer editing
5. Page content management (WYSIWYG HTML)
6. Series/Match/Scorecard scraping

### SEO Features
1. Dynamic meta titles and descriptions
2. OpenGraph and Twitter Card tags
3. Canonical URLs
4. Structured data (JSON-LD) for WebSite and SportsEvent
5. XML Sitemap (/sitemap.xml)
6. Robots.txt (/robots.txt)
7. Keyword-optimized landing pages

## Target Keywords
- India vs Pakistan, Ind vs Pak
- India vs Australia, Ind vs Aus
- India vs England, Ind vs Eng
- India vs New Zealand, Ind vs NZ
- India vs South Africa, Ind vs SA
- India vs Sri Lanka, Ind vs SL
- India vs Bangladesh, Ind vs Ban
- India vs Afghanistan, Ind vs Afg
- India vs West Indies, Ind vs WI
- Cricbuzz

## Default Admin Credentials
- Username: admin
- Password: admin123
(Change after first login)

## Environment Variables
- DATABASE_URL: PostgreSQL connection string
- SESSION_SECRET: Flask session secret key

## Routes

### Public Routes
- GET / - Homepage
- GET /match/<slug> - Keyword landing pages
- GET /page/<slug> - Static pages (about, contact, etc.)
- GET /sitemap.xml - XML sitemap
- GET /robots.txt - Robots file

### Admin Routes
- GET /admin/login - Login page
- GET /admin/logout - Logout
- GET /admin - Series list (protected)
- GET /admin/settings - Site settings (protected)
- GET /admin/pages - Manage pages (protected)
- GET /admin/pages/edit/<id> - Edit page (protected)

### API Endpoints
- POST /api/scrape-series - Scrape series
- POST /api/scrape-matches/<id> - Scrape matches
- POST /api/scrape-scorecard - Scrape scorecard
- GET /api/get-scorecard/<id> - Get saved scorecard
- GET /api/saved-scorecards - List scorecards

## Tech Stack
- Python 3.11 with Flask
- PostgreSQL Database
- Jinja2 Templates
- BeautifulSoup4 + lxml for scraping
- Werkzeug for password hashing

## Recent Changes
- January 2026: Added frontend with Cricbuzz-style design
- January 2026: Implemented admin authentication system
- January 2026: Added site settings and theme customization
- January 2026: Created 5 AdSense-required pages
- January 2026: Built 9 SEO keyword landing pages
- January 2026: Added sitemap.xml and robots.txt
- January 2026: Implemented structured data (JSON-LD)
- January 2026: Added OpenGraph and Twitter Card meta tags
