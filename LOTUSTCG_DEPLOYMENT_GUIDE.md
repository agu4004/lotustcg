# 🚀 AWS Lightsail Deployment Guide - LotusTCG

This comprehensive guide will walk you through deploying your LotusTCG Flask application on AWS Lightsail from start to finish.

## 📋 Prerequisites

- AWS account with billing enabled
- Basic command line knowledge
- Your application files ready for deployment

## 🔧 Step 1: Create AWS Lightsail Instance

### 1.1 Launch Instance
```bash
# Login to AWS Lightsail Console
# https://lightsail.aws.amazon.com/

# Create new instance:
# - Platform: Linux/Unix
# - Blueprint: Ubuntu 20.04 LTS
# - Instance Plan: $10/month (2 GB RAM, 1 vCPU)
# - Instance name: lotustcg-server
```

### 1.2 Configure Networking
```bash
# In Lightsail console:
# 1. Go to Networking tab
# 2. Create static IP and attach to instance
# 3. Open firewall ports:
#    - SSH (22) - Already open
#    - HTTP (80) - Add this
#    - HTTPS (443) - Add this
#    - Custom (5000) - Add this for testing
```

## 🔐 Step 2: Connect to Server

### 2.1 SSH Connection
```bash
# Download SSH key from Lightsail console
# Connect using downloaded key
ssh -i LightsailDefaultKey-us-east-1.pem ubuntu@YOUR_STATIC_IP

# Or use Lightsail browser SSH (easier for beginners)
```

## 📦 Step 3: System Updates

### 3.1 Update System Packages
```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y software-properties-common curl wget git nano
```

## 🐘 Step 4: Install PostgreSQL Database

### 4.1 Install PostgreSQL
```bash
sudo apt install -y postgresql postgresql-contrib
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

### 4.2 Create Database and User
```bash
sudo -u postgres psql
CREATE DATABASE lotustcg;
CREATE USER ltcguser WITH ENCRYPTED PASSWORD 'ltcg_secure_password_2024';
GRANT ALL PRIVILEGES ON DATABASE lotustcg TO ltcguser;
ALTER DATABASE lotustcg OWNER TO ltcguser;
\q
```

### 4.3 Test Database Connection
```bash
psql -h localhost -U ltcguser -d lotustcg -c "SELECT current_database(), current_user;"
# Enter password when prompted: ltcg_secure_password_2024
```

## 📁 Step 5: Deploy Application Files

### 5.1 Create Project Directory
```bash
mkdir -p /home/ubuntu/lotustcg
cd /home/ubuntu/lotustcg
```

### 5.2 Upload Application Files
```bash
# Option 1: Use scp from your local machine
scp -i LightsailDefaultKey-us-east-1.pem -r /path/to/your/app/* ubuntu@YOUR_STATIC_IP:/home/ubuntu/lotustcg/

# Option 2: Use git clone
git clone YOUR_REPOSITORY_URL .

# Option 3: Manual file upload using Lightsail file manager
```

## 🐍 Step 6: Python Environment Setup

### 6.1 Install Python and Pip
```bash
sudo apt install -y python3 python3-pip python3-venv python3-dev
python3 --version  # Should show 3.8+
```

### 6.2 Create Virtual Environment
```bash
cd /home/ubuntu/lotustcg
python3 -m venv venv
source venv/bin/activate

# Install packages
pip install --upgrade pip
pip install flask flask-login flask-sqlalchemy flask-migrate werkzeug psycopg2-binary gunicorn

# Verify installation
which gunicorn
gunicorn --version
```

### 6.3 Set Environment Variables
```bash
# Create environment configuration file
cat > .env << EOF
DATABASE_URL=postgresql://ltcguser:password@localhost:5432/lotustcg
SESSION_SECRET=Kv1Sj4T5S734DvLA5idpe8RvSE6PhfAD
FLASK_APP=main.py
FLASK_ENV=production
PGHOST=localhost
PGPORT=5432
PGUSER=ltcguser
PGPASSWORD=ltcg_secure_password_2024
PGDATABASE=lotustcg
EOF

# Export environment variables for current session
export DATABASE_URL=postgresql://ltcguser:password@localhost:5432/lotustcg
export SESSION_SECRET=Kv1Sj4T5S734DvLA5idpe8RvSE6PhfAD

# Make permanent by adding to ~/.bashrc
echo 'export DATABASE_URL=postgresql://ltcguser:password@localhost:5432/lotustcg' >> ~/.bashrc
echo 'export SESSION_SECRET=Kv1Sj4T5S734DvLA5idpe8RvSE6PhfAD' >> ~/.bashrc
source ~/.bashrc

# Verify environment variables are set
echo "DATABASE_URL: $DATABASE_URL"
```

## 🗄️ Step 7: Initialize Database

### 7.1 Set up Database Schema
```bash
# Ensure you're in the app directory and venv is activated
cd /home/ubuntu/lotustcg
source venv/bin/activate

# Export environment variables (critical step)
export DATABASE_URL=postgresql://ltcguser:ltcg_secure_password_2024@localhost:5432/lotustcg
export SESSION_SECRET=your_super_secret_session_key_here_change_this

# Verify environment variable is set
echo "DATABASE_URL: $DATABASE_URL"

# Initialize database tables
python -c "
import os
print('DATABASE_URL:', os.environ.get('DATABASE_URL'))
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
sudo nano /etc/nginx/sites-available/lotustcg

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
        alias /home/ubuntu/lotustcg/static;
        expires 30d;
    }
}

# Enable the site
sudo ln -s /etc/nginx/sites-available/lotustcg /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default  # -f flag ignores if file doesn't exist

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
sudo nano /etc/systemd/system/lotustcg.service

# Add this configuration (copy exactly):
[Unit]
Description=LotusTCG Gunicorn Application
After=network.target

[Service]
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu/lotustcg
Environment=PATH=/home/ubuntu/lotustcg/venv/bin:/usr/bin:/bin
EnvironmentFile=/home/ubuntu/lotustcg/.env
ExecStart=/home/ubuntu/lotustcg/venv/bin/gunicorn --workers 1 --max-requests 1000 --preload --bind 127.0.0.1:5000 --timeout 30 main:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target

# Reload systemd and start service
sudo systemctl daemon-reload
sudo systemctl start lotustcg
sudo systemctl enable lotustcg

# Check service status
sudo systemctl status lotustcg
```

### 9.2 Verify Deployment
```bash
# Check if application is running
curl http://localhost:5000

# Check Nginx is serving the app
curl http://YOUR_STATIC_IP

# View application logs
sudo journalctl -u lotustcg -f
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

## 🎯 Step 11: Testing and Verification

### 11.1 Application Testing
```bash
# Test main endpoints
curl http://YOUR_STATIC_IP/
curl http://YOUR_STATIC_IP/catalog
curl http://YOUR_STATIC_IP/login

# Check database connectivity
python -c "
from app import app
from models import Card
with app.app_context():
    cards = Card.query.limit(3).all()
    print(f'Found {len(cards)} sample cards')
"
```

### 11.2 Performance Testing
```bash
# Install Apache Bench for load testing
sudo apt install -y apache2-utils

# Run simple load test
ab -n 100 -c 10 http://YOUR_STATIC_IP/
```

## 🔧 Step 12: Maintenance Commands

### 12.1 Service Management
```bash
# Restart services
sudo systemctl restart lotustcg
sudo systemctl restart nginx

# Check logs
sudo journalctl -u lotustcg -n 50
sudo journalctl -u nginx -n 50

# Check system resources
htop
df -h
free -m
```

### 12.2 Database Maintenance
```bash
# Backup database
pg_dump -h localhost -U ltcguser lotustcg > lotustcg_backup.sql

# Monitor database connections
psql -U ltcguser -d lotustcg -c "SELECT * FROM pg_stat_activity WHERE datname = 'lotustcg';"
```

## 🆘 Troubleshooting

### Common Issues:
1. **Database connection failed**: Check PostgreSQL service and credentials
2. **Gunicorn not found**: Ensure virtual environment is activated and packages installed
3. **Permission denied**: Check file ownership with `chown -R ubuntu:ubuntu /home/ubuntu/lotustcg`
4. **Service won't start**: Check logs with `sudo journalctl -u lotustcg -n 50`

### Emergency Commands:
```bash
# Stop all services
sudo systemctl stop lotustcg nginx

# Kill any hanging processes
sudo pkill -f gunicorn
sudo pkill -f nginx

# Restart from scratch
sudo systemctl start lotustcg nginx
```

## ✅ Deployment Complete!

Your LotusTCG application is now deployed and accessible at:
- **HTTP**: http://YOUR_STATIC_IP
- **Admin Panel**: http://YOUR_STATIC_IP/admin

### Default Login Credentials:
- **Admin**: admin@lotustcg.com / admin123
- **User**: user@lotustcg.com / user123

**🚨 Important**: Change these default passwords immediately after first login!