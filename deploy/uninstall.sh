#!/bin/bash

echo "=========================================="
echo "  Cricbuzz Live Score - Uninstall"
echo "=========================================="

read -p "Are you sure you want to uninstall? (y/n): " confirm
if [ "$confirm" != "y" ]; then
    echo "Cancelled."
    exit 0
fi

echo ""
echo "Stopping services..."
sudo systemctl stop cricbuzz
sudo systemctl disable cricbuzz

echo "Removing systemd service..."
sudo rm -f /etc/systemd/system/cricbuzz.service
sudo systemctl daemon-reload

echo "Removing Nginx config..."
sudo rm -f /etc/nginx/sites-enabled/cricbuzz
sudo rm -f /etc/nginx/sites-available/cricbuzz
sudo systemctl restart nginx

read -p "Delete application files? (y/n): " del_files
if [ "$del_files" == "y" ]; then
    sudo rm -rf /var/www/cricbuzz
    echo "Application files deleted."
fi

read -p "Delete database? (y/n): " del_db
if [ "$del_db" == "y" ]; then
    sudo -u postgres psql -c "DROP DATABASE IF EXISTS cricbuzz_db;"
    sudo -u postgres psql -c "DROP USER IF EXISTS cricbuzz_user;"
    echo "Database deleted."
fi

echo ""
echo "Uninstall complete!"
