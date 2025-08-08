# AWS Lightsail Deployment Guide - CardMarketScan

## 🚀 Complete Deployment Tutorial

This guide will walk you through deploying your Flask CardMarketScan application to AWS Lightsail with PostgreSQL database persistence.

## 📋 Prerequisites

- AWS account with billing set up
- Basic terminal/command line knowledge
- Your Replit project code ready to download

## 🛠️ Step 1: Create AWS Lightsail Instance

### 1.1 Launch Lightsail Instance
```bash
# Go to AWS Lightsail Console
# https://lightsail.aws.amazon.com/

# Create Instance:
# - Platform: Linux/Unix
# - Blueprint: Ubuntu 22.04 LTS
# - Instance Plan: $10/month (2GB RAM, 1 vCPU) - Recommended minimum
# - Instance Name: cardmarketscan
```

### 1.2 Configure Networking
```bash
# In Lightsail Console -> Networking:
# - Create Static IP and attach to your instance
# - Open these ports in Firewall:
#   - SSH (22) - Already open
#   - HTTP (80) - Add this
#   - HTTPS (443) - Add this  
#   - Custom (5000) - Add this for testing
```

## 🔧 Step 2: Initial Server Setup

### 2.1 Connect to Your Instance
```bash
# From Lightsail Console, click "Connect using SSH"
# Or use your preferred SSH client:
ssh ubuntu@YOUR_STATIC_IP
```

### 2.2 Update System Packages
```bash
# Update package list and upgrade system
sudo apt update && sudo apt upgrade -y

# Install essential packages
sudo apt install -y software-properties-common curl wget git unzip
```

## 🐍 Step 3: Install Python and Dependencies

### 3.1 Install Python 3.11
```bash
# Add Python repository and install Python 3.11
sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3.11-dev python3-pip

# Set Python 3.11 as default
sudo update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1
sudo update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1

# Verify installation
python --version  # Should show Python 3.11.x
```

### 3.2 Install uv Package Manager
```bash
# Install uv for faster package management (same as used in Replit)
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc

# Verify uv installation
uv --version
```

## 🗄️ Step 4: Install and Configure PostgreSQL

### 4.1 Install PostgreSQL
```bash
# Install PostgreSQL 14
sudo apt install -y postgresql postgresql-contrib

# Start and enable PostgreSQL service
sudo systemctl start postgresql
sudo systemctl enable postgresql

# Verify PostgreSQL is running
sudo systemctl status postgresql
```

### 4.2 Configure PostgreSQL Database
```bash
# Switch to postgres user and create database
sudo -u postgres psql

# In PostgreSQL prompt:
CREATE DATABASE cardmarketscan;
CREATE USER cmsuser WITH ENCRYPTED PASSWORD 'cms_secure_password_2024';
GRANT ALL PRIVILEGES ON DATABASE cardmarketscan TO cmsuser;
\q

# Test database connection
psql -h localhost -U cmsuser -d cardmarketscan
# Enter password when prompted, then type \q to exit
```

### 4.3 Configure PostgreSQL for Application Access
```bash
# First, find the correct PostgreSQL version and directory
sudo find /etc/postgresql -name "postgresql.conf" 2>/dev/null
# This will show the actual path, likely /etc/postgresql/15/main/ or /etc/postgresql/16/main/

# Check PostgreSQL version
sudo -u postgres psql -c "SELECT version();"

# Use the correct path (replace XX with your version number):
PGVERSION=$(sudo -u postgres psql -t -c "SELECT version();" | grep -oE '[0-9]+\.[0-9]+' | head -1 | cut -d. -f1)
echo "PostgreSQL version: $PGVERSION"

# Edit PostgreSQL configuration (using detected version)
sudo nano /etc/postgresql/$PGVERSION/main/postgresql.conf

# Find and modify these lines (uncomment if needed):
listen_addresses = 'localhost'
port = 5432

# Save and exit (Ctrl+X, Y, Enter)

# Edit authentication file
sudo nano /etc/postgresql/$PGVERSION/main/pg_hba.conf

# Add this line BEFORE the existing local entries:
local   cardmarketscan   cmsuser                 md5

# Save and restart PostgreSQL
sudo systemctl restart postgresql

# Test the configuration
sudo -u postgres psql -c "\l" | grep cardmarketscan
```

## 📁 Step 5: Deploy Application Code

### 5.1 Download Your Code from Replit
```bash
# Create application directory
mkdir -p /home/ubuntu/cardmarketscan
cd /home/ubuntu/cardmarketscan

# Option A: Download via Replit export
# 1. In Replit, go to Files > Export as ZIP
# 2. Upload ZIP to your server and extract:
wget "YOUR_REPLIT_EXPORT_URL" -O tcg-app.zip
unzip tcg-app.zip
```

### 5.2 Alternative: Manual File Transfer
```bash
# Option B: Create files manually (if export doesn't work)
# You'll need to copy each file content from Replit to your server

# Create main application files:
nano app.py          # Copy content from Replit
nano main.py         # Copy content from Replit
nano models.py       # Copy content from Replit
nano routes.py       # Copy content from Replit
nano storage_db.py   # Copy content from Replit
nano seed_database.py # Copy content from Replit

# Create requirements file:
nano requirements.txt
```

### 5.3 Create requirements.txt
```txt
# Copy this content to requirements.txt:
Flask==3.0.3
Flask-Login==0.6.3
Flask-SQLAlchemy==3.1.1
Flask-Migrate==4.0.5
SQLAlchemy==2.0.23
psycopg2-binary==2.9.9
Werkzeug==3.0.4
gunicorn==21.2.0
email-validator==2.1.1
coverage==7.3.2
pytest==7.4.3
pytest-flask==1.3.0
pytest-cov==4.1.0
```

### 5.4 Create Templates and Static Directories
```bash
# Create directory structure
mkdir -p templates static/css static/js

# Copy template files from Replit:
# templates/base.html
# templates/index.html
# templates/catalog.html
# templates/login.html
# templates/admin.html
# templates/cart.html
# templates/card_detail.html

# Note: You'll need to manually copy these files from your Replit project
```

## 🔧 Step 6: Configure Application Environment

### 6.1 Create Virtual Environment and Install Dependencies
```bash
# Create Python virtual environment
cd /home/ubuntu/cardmarketscan
python -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install dependencies using uv (faster) or pip
uv pip install -r requirements.txt
# OR: pip install -r requirements.txt

# Verify installation
python -c "import flask; print('Flask installed successfully')"
```

### 6.2 Set Environment Variables
```bash
# Create environment configuration file
nano .env

# Add these environment variables:
DATABASE_URL=postgresql://cmsuser:cms_secure_password_2024@localhost:5432/cardmarketscan
SESSION_SECRET=your_super_secret_session_key_here_change_this
FLASK_APP=main.py
FLASK_ENV=production
PGHOST=localhost
PGPORT=5432
PGUSER=cmsuser
PGPASSWORD=cms_secure_password_2024
PGDATABASE=cardmarketscan

# Load environment variables (add to ~/.bashrc for persistence)
echo 'export $(cat /home/ubuntu/cardmarketscan/.env | xargs)' >> ~/.bashrc
source ~/.bashrc
```

## 🗄️ Step 7: Initialize Database

### 7.1 Set up Database Schema
```bash
# Ensure you're in the app directory and venv is activated
cd /home/ubuntu/cardmarketscan
source venv/bin/activate

# Initialize database tables
python -c "
from app import app, db
with app.app_context():
    db.create_all()
    print('Database tables created successfully')
"

# Seed database with sample data
python seed_database.py
```

### 7.2 Verify Database Setup
```bash
# Test database connection and data
python -c "
from app import app
from models import User, Card

with app.app_context():
    print(f'Users: {User.query.count()}')
    print(f'Cards: {Card.query.count()}')
    print('Database verification complete')
"
```

## 🌐 Step 8: Configure Web Server (Nginx)

### 8.1 Install and Configure Nginx
```bash
# Install Nginx
sudo apt install -y nginx

# Create Nginx configuration
sudo nano /etc/nginx/sites-available/cardmarketscan

# Add this configuration:
server {
    listen 80;
    server_name YOUR_STATIC_IP;  # Replace with your Lightsail static IP

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static {
        alias /home/ubuntu/cardmarketscan/static;
        expires 30d;
    }
}

# Enable the site
sudo ln -s /etc/nginx/sites-available/cardmarketscan /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default

# Test Nginx configuration
sudo nginx -t

# Start and enable Nginx
sudo systemctl start nginx
sudo systemctl enable nginx
```

## 🚀 Step 9: Deploy with Gunicorn

### 9.1 Create Gunicorn Service
```bash
# Create systemd service file
sudo nano /etc/systemd/system/cardmarketscan.service

# Add this configuration:
[Unit]
Description=CardMarketScan Gunicorn Application
After=network.target

[Service]
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu/cardmarketscan
Environment="PATH=/home/ubuntu/cardmarketscan/venv/bin"
EnvironmentFile=/home/ubuntu/cardmarketscan/.env
ExecStart=/home/ubuntu/cardmarketscan/venv/bin/gunicorn --workers 3 --bind 127.0.0.1:5000 main:app
Restart=always

[Install]
WantedBy=multi-user.target

# Reload systemd and start service
sudo systemctl daemon-reload
sudo systemctl start cardmarketscan
sudo systemctl enable cardmarketscan

# Check service status
sudo systemctl status cardmarketscan
```

### 9.2 Verify Deployment
```bash
# Check if application is running
curl http://localhost:5000

# Check Nginx is serving the app
curl http://YOUR_STATIC_IP

# View application logs
sudo journalctl -u cardmarketscan -f
```

## 🔒 Step 10: Security and SSL Setup

### 10.1 Install SSL Certificate (Let's Encrypt)
```bash
# Install Certbot
sudo apt install -y certbot python3-certbot-nginx

# Get SSL certificate (replace with your domain)
sudo certbot --nginx -d your-domain.com

# Test automatic renewal
sudo certbot renew --dry-run
```

### 10.2 Configure Firewall
```bash
# Install and configure UFW firewall
sudo ufw enable
sudo ufw allow ssh
sudo ufw allow 'Nginx Full'
sudo ufw status
```

## 🎯 Step 11: Testing and Verification

### 11.1 Test Application Features
```bash
# Test login page
curl -I http://YOUR_STATIC_IP/login

# Check database connectivity
python -c "
from app import app
from storage_db import storage

with app.app_context():
    cards = storage.get_all_cards()
    print(f'Successfully loaded {len(cards)} cards')
"
```

### 11.2 Performance Testing
```bash
# Install Apache Bench for load testing
sudo apt install -y apache2-utils

# Test application performance
ab -n 100 -c 10 http://YOUR_STATIC_IP/catalog
```

## 🔧 Step 12: Ongoing Maintenance

### 12.1 Log Management
```bash
# View application logs
sudo journalctl -u cardmarketscan --since "1 hour ago"

# View Nginx access logs
sudo tail -f /var/log/nginx/access.log

# View Nginx error logs
sudo tail -f /var/log/nginx/error.log
```

### 12.2 Backup Database
```bash
# Create database backup script
nano ~/backup-db.sh

#!/bin/bash
backup_file="tcg_backup_$(date +%Y%m%d_%H%M%S).sql"
pg_dump -h localhost -U cmsuser cardmarketscan > ~/backups/$backup_file
echo "Database backed up to $backup_file"

# Make executable and create backups directory
chmod +x ~/backup-db.sh
mkdir -p ~/backups

# Run backup
./backup-db.sh
```

## ⚠️ Common Issues and Troubleshooting

### Issue 1: Database Connection Failed
```bash
# Check PostgreSQL status
sudo systemctl status postgresql

# Check database credentials
psql -h localhost -U cmsuser -d cardmarketscan

# Check environment variables
echo $DATABASE_URL
```

### Issue 2: Gunicorn Won't Start
```bash
# Check logs
sudo journalctl -u cardmarketscan -n 50

# Test manually
cd /home/ubuntu/cardmarketscan
source venv/bin/activate
gunicorn --bind 127.0.0.1:5000 main:app
```

### Issue 3: Nginx 502 Bad Gateway
```bash
# Check if Gunicorn is running
sudo systemctl status cardmarketscan

# Check Nginx configuration
sudo nginx -t

# Check Nginx logs
sudo tail -f /var/log/nginx/error.log
```

### Issue 4: Static Files Not Loading
```bash
# Check static files path
ls -la /home/ubuntu/cardmarketscan/static/

# Update Nginx static files location
sudo nano /etc/nginx/sites-available/cardmarketscan
```

## 🌟 Final Verification Checklist

- [ ] Lightsail instance running and accessible
- [ ] PostgreSQL installed and database created
- [ ] Application code deployed and dependencies installed
- [ ] Environment variables configured
- [ ] Database seeded with sample data
- [ ] Nginx configured and running
- [ ] Gunicorn service running
- [ ] Application accessible via static IP
- [ ] All features working (login, catalog, cart, admin)
- [ ] SSL certificate installed (optional but recommended)
- [ ] Firewall configured
- [ ] Backup system in place

## 🎉 Success!

Your CardMarketScan is now live on AWS Lightsail! Access it at:
- **HTTP**: http://YOUR_STATIC_IP
- **HTTPS**: https://your-domain.com (if SSL configured)

**Login Credentials:**
- Admin: username=`admin`, password=`admin123`
- User: username=`user`, password=`user123`

## 💡 Next Steps

1. **Domain Setup**: Point your custom domain to the Lightsail static IP
2. **SSL Certificate**: Set up Let's Encrypt for HTTPS
3. **Monitoring**: Set up CloudWatch or similar monitoring
4. **Backups**: Schedule regular database backups
5. **Scaling**: Consider upgrading instance size based on traffic

## 📞 Support

If you encounter issues:
1. Check the troubleshooting section above
2. Review application and system logs
3. Verify all services are running
4. Check AWS Lightsail documentation

**Estimated Deployment Time**: 45-60 minutes for beginners
**Monthly Cost**: ~$10-20 USD (depending on instance size and data transfer)