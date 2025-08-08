# 🚀 LotusTCG Quick Setup Commands

## Complete Deployment Script
Copy and paste these commands in sequence on your AWS Lightsail Ubuntu server:

```bash
# Step 1: System Setup
sudo apt update && sudo apt upgrade -y
sudo apt install -y software-properties-common curl wget git nano postgresql postgresql-contrib python3 python3-pip python3-venv python3-dev nginx

# Step 2: Database Setup
sudo systemctl start postgresql
sudo systemctl enable postgresql
sudo -u postgres psql << EOF
CREATE DATABASE lotustcg;
CREATE USER ltcguser WITH ENCRYPTED PASSWORD 'ltcg_secure_password_2024';
GRANT ALL PRIVILEGES ON DATABASE lotustcg TO ltcguser;
ALTER DATABASE lotustcg OWNER TO ltcguser;
\q
EOF

# Step 3: Application Setup
mkdir -p /home/ubuntu/lotustcg
cd /home/ubuntu/lotustcg

# Upload your application files here before continuing

# Step 4: Python Environment
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install flask flask-login flask-sqlalchemy flask-migrate werkzeug psycopg2-binary gunicorn

# Step 5: Environment Variables
cat > .env << EOF
DATABASE_URL=postgresql://ltcguser:ltcg_secure_password_2024@localhost:5432/lotustcg
SESSION_SECRET=your_super_secret_session_key_here_change_this
FLASK_APP=main.py
FLASK_ENV=production
EOF

# Step 6: Database Initialization
export $(cat .env | xargs)
python -c "
from app import app, db
with app.app_context():
    db.create_all()
    print('Database tables created successfully')
"
python seed_database.py

# Step 7: Systemd Service
sudo tee /etc/systemd/system/lotustcg.service > /dev/null << 'EOF'
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
EOF

# Step 8: Nginx Configuration
sudo tee /etc/nginx/sites-available/lotustcg > /dev/null << 'EOF'
server {
    listen 80;
    server_name _;

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
EOF

# Step 9: Enable Services
sudo ln -s /etc/nginx/sites-available/lotustcg /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default  # -f flag prevents error if file doesn't exist
sudo nginx -t
sudo systemctl daemon-reload
sudo systemctl enable lotustcg nginx
sudo systemctl start lotustcg nginx

# Step 10: Verify Deployment
echo "=== Checking Services ==="
sudo systemctl status lotustcg --no-pager
sudo systemctl status nginx --no-pager

echo "=== Testing Application ==="
curl -s http://localhost:5000 && echo "✓ Application responding" || echo "✗ Application not responding"

echo "=== Deployment Complete! ==="
echo "Your LotusTCG application should be accessible at your server's IP address"
```

## Quick Verification Commands
```bash
# Check service status
sudo systemctl status lotustcg nginx

# Check logs
sudo journalctl -u lotustcg -n 20
sudo journalctl -u nginx -n 20

# Test application
curl http://localhost:5000

# Check database
psql -h localhost -U ltcguser -d lotustcg -c "SELECT current_database(), current_user;"
```

## Troubleshooting Commands
```bash
# Restart services
sudo systemctl restart lotustcg nginx

# Check what's running on port 5000
sudo netstat -tlnp | grep 5000

# Manual application test
cd /home/ubuntu/lotustcg
source venv/bin/activate
export $(cat .env | xargs)
gunicorn --bind 0.0.0.0:5000 --workers 1 main:app
```