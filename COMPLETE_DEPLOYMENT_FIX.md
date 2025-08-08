# Complete Deployment Fix - Virtual Environment Corruption

## Issue Confirmed
"Pipe to stdout was broken" indicates the virtual environment is completely corrupted and needs full rebuild.

## Complete Solution

### 1. Clean Slate - Remove Corrupted Environment
```bash
cd /home/ubuntu/cardmarketscan
rm -rf venv/
```

### 2. Rebuild Virtual Environment
```bash
# Create new virtual environment
python3 -m venv venv

# Activate and verify
source venv/bin/activate
echo "Python: $(which python)"
echo "Pip: $(which pip)"

# Upgrade pip first
pip install --upgrade pip
```

### 3. Install All Required Packages
```bash
# Install core Flask packages
pip install flask==2.3.3 flask-login==0.6.3 flask-sqlalchemy==3.0.5 flask-migrate==4.0.5

# Install database and server packages  
pip install psycopg2-binary==2.9.7 gunicorn==21.2.0 werkzeug==2.3.7

# Verify critical packages
pip show gunicorn
pip show flask
```

### 4. Test Application Manually
```bash
# Load environment variables
export $(cat .env | xargs)

# Test Python import
python -c "
try:
    from main import app
    print('✓ Application imports successfully')
    print('✓ Database URL:', app.config.get('SQLALCHEMY_DATABASE_URI')[:30] + '...')
except Exception as e:
    print('✗ Import error:', str(e))
"

# Test Gunicorn
gunicorn --bind 127.0.0.1:8000 --timeout 30 main:app &
GUNICORN_PID=$!
sleep 3
curl -s http://127.0.0.1:8000 && echo "✓ Gunicorn test successful" || echo "✗ Gunicorn test failed"
kill $GUNICORN_PID 2>/dev/null
```

### 5. Update Systemd Service with Correct Paths
```bash
sudo tee /etc/systemd/system/cardmarketscan.service > /dev/null << EOF
[Unit]
Description=CardMarketScan Gunicorn Application
After=network.target

[Service]
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu/cardmarketscan
Environment=PATH=/home/ubuntu/cardmarketscan/venv/bin:/usr/bin:/bin
EnvironmentFile=/home/ubuntu/cardmarketscan/.env
ExecStart=/home/ubuntu/cardmarketscan/venv/bin/gunicorn --workers 3 --bind 127.0.0.1:5000 --timeout 30 main:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
```

### 6. Start Service
```bash
sudo systemctl daemon-reload
sudo systemctl enable cardmarketscan
sudo systemctl start cardmarketscan

# Check status
sudo systemctl status cardmarketscan --no-pager
```

### 7. Verify Deployment
```bash
# Test local connection
curl -s http://127.0.0.1:5000 || echo "Service not responding"

# Check logs
sudo journalctl -u cardmarketscan -n 20 --no-pager
```

## Emergency Fallback - System Installation
If virtual environment continues to fail:

```bash
# Install system-wide
sudo apt update
sudo apt install -y python3-pip python3-dev
sudo pip3 install flask gunicorn psycopg2-binary flask-sqlalchemy flask-login werkzeug flask-migrate

# Use system paths in service
sudo sed -i 's|/home/ubuntu/cardmarketscan/venv/bin/gunicorn|/usr/local/bin/gunicorn|g' /etc/systemd/system/cardmarketscan.service
sudo sed -i 's|Environment=PATH=.*|Environment=PATH=/usr/local/bin:/usr/bin:/bin|g' /etc/systemd/system/cardmarketscan.service

sudo systemctl daemon-reload
sudo systemctl restart cardmarketscan
```