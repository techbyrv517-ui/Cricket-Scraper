# Cricbuzz Live Score - Server Deployment Guide

## Requirements
- Ubuntu 20.04+ / Debian 11+
- Python 3.9+
- PostgreSQL 12+
- Nginx
- Root/sudo access

## Quick Install

```bash
cd deploy
chmod +x install.sh
sudo ./install.sh
```

## Manual Installation

### 1. Install Dependencies
```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv postgresql postgresql-contrib nginx
```

### 2. Setup Database
```bash
sudo -u postgres psql
CREATE USER cricbuzz_user WITH PASSWORD 'your_password';
CREATE DATABASE cricbuzz_db OWNER cricbuzz_user;
GRANT ALL PRIVILEGES ON DATABASE cricbuzz_db TO cricbuzz_user;
\q
```

### 3. Setup Application
```bash
sudo mkdir -p /var/www/cricbuzz
sudo cp -r * /var/www/cricbuzz/
cd /var/www/cricbuzz
python3 -m venv venv
source venv/bin/activate
pip install flask gunicorn psycopg2-binary requests beautifulsoup4 lxml apscheduler werkzeug python-dotenv pillow
```

### 4. Create .env file
```bash
sudo nano /var/www/cricbuzz/.env
```
Add:
```
DATABASE_URL=postgresql://cricbuzz_user:your_password@localhost/cricbuzz_db
SESSION_SECRET=your-random-secret-key
```

### 5. Test Application
```bash
cd /var/www/cricbuzz
source venv/bin/activate
python app.py
```

### 6. Setup Systemd Service
Create `/etc/systemd/system/cricbuzz.service`:
```ini
[Unit]
Description=Cricbuzz Live Score Application
After=network.target postgresql.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/cricbuzz
Environment="PATH=/var/www/cricbuzz/venv/bin"
EnvironmentFile=/var/www/cricbuzz/.env
ExecStart=/var/www/cricbuzz/venv/bin/gunicorn --workers 2 --threads 4 --bind 127.0.0.1:5000 app:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable cricbuzz
sudo systemctl start cricbuzz
```

### 7. Setup Nginx
Create `/etc/nginx/sites-available/cricbuzz`:
```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    location /static {
        alias /var/www/cricbuzz/static;
        expires 7d;
    }
}
```

Enable and restart:
```bash
sudo ln -s /etc/nginx/sites-available/cricbuzz /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

## SSL Certificate (Optional)
```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

## Useful Commands

| Command | Description |
|---------|-------------|
| `sudo systemctl status cricbuzz` | Check app status |
| `sudo systemctl restart cricbuzz` | Restart application |
| `sudo systemctl stop cricbuzz` | Stop application |
| `sudo journalctl -u cricbuzz -f` | View live logs |
| `sudo journalctl -u cricbuzz --since "1 hour ago"` | View recent logs |

## Default Admin Login
- URL: `http://your-server/admin/login`
- Username: `admin`
- Password: `admin123`

**Important:** Change the default password after first login!

## Troubleshooting

### App not starting
```bash
sudo journalctl -u cricbuzz -n 50
```

### Database connection error
```bash
sudo -u postgres psql -c "\l"  # List databases
sudo -u postgres psql -c "\du" # List users
```

### Nginx error
```bash
sudo nginx -t
sudo tail -f /var/log/nginx/error.log
```

## Uninstall
```bash
cd deploy
chmod +x uninstall.sh
sudo ./uninstall.sh
```
