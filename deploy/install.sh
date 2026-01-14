#!/bin/bash

echo "=========================================="
echo "  Cricbuzz Live Score - Server Setup"
echo "=========================================="

read -p "Enter your domain name (e.g., cricbuzz-live-score.com): " DOMAIN_NAME
read -p "Enter installation directory (e.g., /var/www/cricbuzz-live-score.com): " APP_DIR

if [ -z "$APP_DIR" ]; then
    APP_DIR="/var/www/$DOMAIN_NAME"
fi

APP_USER="www-data"
DB_NAME="cricbuzz_db"
DB_USER="cricbuzz_user"

read -p "Enter database password: " DB_PASS
read -p "Enter session secret key: " SESSION_SECRET

echo ""
echo "Installing to: $APP_DIR"
echo "Domain: $DOMAIN_NAME"
echo ""

echo ""
echo "[1/7] Installing system dependencies..."
sudo apt update
sudo apt install -y python3 python3-pip python3-venv postgresql postgresql-contrib nginx

echo ""
echo "[2/7] Setting up PostgreSQL database..."
sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASS';" 2>/dev/null || echo "User may already exist"
sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;" 2>/dev/null || echo "Database may already exist"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;"

echo ""
echo "[3/7] Creating application directory..."
sudo mkdir -p $APP_DIR
sudo cp -r ../* $APP_DIR/ 2>/dev/null || sudo cp -r ./* $APP_DIR/
sudo chown -R $APP_USER:$APP_USER $APP_DIR

echo ""
echo "[4/7] Setting up Python environment..."
cd $APP_DIR
sudo -u $APP_USER python3 -m venv venv
sudo -u $APP_USER $APP_DIR/venv/bin/pip install --upgrade pip
sudo -u $APP_USER $APP_DIR/venv/bin/pip install flask gunicorn psycopg2-binary requests beautifulsoup4 lxml apscheduler werkzeug python-dotenv pillow

echo ""
echo "[5/7] Creating environment file..."
sudo tee $APP_DIR/.env > /dev/null << EOF
DATABASE_URL=postgresql://$DB_USER:$DB_PASS@localhost/$DB_NAME
SESSION_SECRET=$SESSION_SECRET
EOF
sudo chown $APP_USER:$APP_USER $APP_DIR/.env
sudo chmod 600 $APP_DIR/.env

echo ""
echo "[6/7] Creating systemd service..."
sudo tee /etc/systemd/system/cricbuzz.service > /dev/null << EOF
[Unit]
Description=Cricbuzz Live Score Application
After=network.target postgresql.service

[Service]
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR
Environment="PATH=$APP_DIR/venv/bin"
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/venv/bin/gunicorn --workers 2 --threads 4 --bind 127.0.0.1:5000 app:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

echo ""
echo "[7/7] Creating Nginx configuration..."
sudo tee /etc/nginx/sites-available/$DOMAIN_NAME > /dev/null << EOF
server {
    listen 80;
    server_name $DOMAIN_NAME www.$DOMAIN_NAME;

    client_max_body_size 10M;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_connect_timeout 60s;
        proxy_read_timeout 60s;
    }

    location /static {
        alias $APP_DIR/static;
        expires 7d;
        add_header Cache-Control "public, immutable";
    }
}
EOF

sudo ln -sf /etc/nginx/sites-available/$DOMAIN_NAME /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default

echo ""
echo "Starting services..."
sudo systemctl daemon-reload
sudo systemctl enable cricbuzz
sudo systemctl start cricbuzz
sudo systemctl restart nginx

echo ""
echo "=========================================="
echo "  Installation Complete!"
echo "=========================================="
echo ""
echo "Domain: $DOMAIN_NAME"
echo "Directory: $APP_DIR"
echo ""
echo "App running at: http://$DOMAIN_NAME"
echo "Admin panel: http://$DOMAIN_NAME/admin/login"
echo "Default login: admin / admin123"
echo ""
echo "Useful commands:"
echo "  sudo systemctl status cricbuzz    - Check app status"
echo "  sudo systemctl restart cricbuzz   - Restart app"
echo "  sudo journalctl -u cricbuzz -f    - View logs"
echo ""
echo "For SSL certificate (HTTPS):"
echo "  sudo apt install certbot python3-certbot-nginx"
echo "  sudo certbot --nginx -d $DOMAIN_NAME -d www.$DOMAIN_NAME"
echo ""
