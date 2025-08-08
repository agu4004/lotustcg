# 🔧 LotusTCG Deployment Troubleshooting Guide

## Environment Variables Fix

### Issue: DATABASE_URL not found
```bash
cd /home/ubuntu/lotustcg
source venv/bin/activate

# Export environment variables
export DATABASE_URL=postgresql://ltcguser:ltcg_secure_password_2024@localhost:5432/lotustcg
export SESSION_SECRET=your_super_secret_session_key_here_change_this

# Verify
echo "DATABASE_URL: $DATABASE_URL"

# Test database connection
psql "$DATABASE_URL" -c "SELECT current_database();"
```

## Database Connection Issues

### Create Database and User
```bash
sudo -u postgres psql
DROP DATABASE IF EXISTS lotustcg;
DROP USER IF EXISTS ltcguser;
CREATE DATABASE lotustcg;
CREATE USER ltcguser WITH ENCRYPTED PASSWORD 'ltcg_secure_password_2024';
GRANT ALL PRIVILEGES ON DATABASE lotustcg TO ltcguser;
ALTER DATABASE lotustcg OWNER TO ltcguser;
\q
```

### Test Database
```bash
psql -h localhost -U ltcguser -d lotustcg -c "\dt"
```

## Virtual Environment Issues

### Rebuild Virtual Environment
```bash
cd /home/ubuntu/lotustcg
rm -rf venv/
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install flask flask-login flask-sqlalchemy flask-migrate werkzeug psycopg2-binary gunicorn
which gunicorn
gunicorn --version
```

## Systemd Service Issues

### Check Service Status
```bash
sudo systemctl status lotustcg --no-pager
sudo journalctl -u lotustcg -n 50 --no-pager
```

### Fix Service Configuration
```bash
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
ExecStart=/home/ubuntu/lotustcg/venv/bin/gunicorn --workers 3 --bind 127.0.0.1:5000 --timeout 30 main:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl restart lotustcg
```

## Application Testing

### Manual Application Test
```bash
cd /home/ubuntu/lotustcg
source venv/bin/activate
export $(cat .env | xargs)

# Test import
python -c "from main import app; print('App loads successfully')"

# Test gunicorn
gunicorn --bind 0.0.0.0:5000 --workers 1 --timeout 30 main:app &
sleep 3
curl http://localhost:5000
pkill gunicorn
```

## Database Initialization

### Initialize Database Tables
```bash
cd /home/ubuntu/lotustcg
source venv/bin/activate
export $(cat .env | xargs)

python -c "
from app import app, db
with app.app_context():
    db.create_all()
    print('Database tables created successfully')
"

python seed_database.py
```

## Port and Connection Issues

### Check Port Usage
```bash
sudo netstat -tlnp | grep 5000
sudo ss -tlnp | grep 5000
```

### Kill Hanging Processes
```bash
sudo pkill -f gunicorn
sudo pkill -f nginx
```

### Test Different Port
```bash
cd /home/ubuntu/lotustcg
source venv/bin/activate
export $(cat .env | xargs)
gunicorn --bind 0.0.0.0:8080 main:app &
curl http://localhost:8080
pkill gunicorn
```

## File Permissions

### Fix File Ownership
```bash
sudo chown -R ubuntu:ubuntu /home/ubuntu/lotustcg/
chmod +x /home/ubuntu/lotustcg/venv/bin/gunicorn
```

## Emergency Reset

### Complete Service Reset
```bash
# Stop services
sudo systemctl stop lotustcg nginx

# Kill processes
sudo pkill -f gunicorn
sudo pkill -f nginx

# Restart services
sudo systemctl start postgresql
sudo systemctl start lotustcg
sudo systemctl start nginx

# Check status
sudo systemctl status lotustcg nginx
```

## Common Error Solutions

### Error: "No such file or directory" for gunicorn
```bash
# Rebuild virtual environment (see above)
# Verify gunicorn installation
which gunicorn
ls -la /home/ubuntu/lotustcg/venv/bin/gunicorn
```

### Error: "Connection refused"
```bash
# Check if service is running
sudo systemctl status lotustcg
# Check port binding
sudo netstat -tlnp | grep 5000
```

### Error: "Database does not exist"
```bash
# Recreate database (see database section above)
# Check DATABASE_URL variable
echo $DATABASE_URL
```

### Error: "Permission denied"
```bash
# Fix file permissions
sudo chown -R ubuntu:ubuntu /home/ubuntu/lotustcg/
# Check service user in systemd file
grep User /etc/systemd/system/lotustcg.service
```

## Verification Checklist

- [ ] Database `lotustcg` exists and `ltcguser` has access
- [ ] Virtual environment has all packages installed
- [ ] Environment variables are set in .env file
- [ ] Systemd service file syntax is correct
- [ ] Application files are owned by ubuntu user
- [ ] Nginx configuration is valid
- [ ] Services are enabled and started
- [ ] Application responds on localhost:5000
- [ ] Nginx serves application on port 80

## Port 80 Connection Issues

### Diagnostic Commands
```bash
# Check if services are running
sudo systemctl status nginx lotustcg --no-pager

# Check port binding
sudo ss -tlnp | grep :80
sudo ss -tlnp | grep :5000

# Test local connections
curl http://localhost:80
curl http://localhost:5000
```

### Fix Steps
```bash
# Ensure services are started
sudo systemctl start nginx lotustcg
sudo systemctl enable nginx lotustcg

# Check nginx configuration
sudo nginx -t

# Test external connection
curl http://YOUR_STATIC_IP
```

### AWS Lightsail Firewall Check
Ensure these ports are open in AWS Lightsail Networking tab:
- HTTP (80) 
- HTTPS (443)
- Custom (5000) for testing

## Success Indicators

When everything works correctly, you should see:
```bash
# Service status shows active
sudo systemctl status lotustcg nginx

# Application responds locally
curl http://localhost:5000     # LotusTCG app direct
curl http://localhost:80       # Through nginx proxy

# External access works
curl http://YOUR_STATIC_IP     # Should return HTML content

# Database has data
psql -U ltcguser -d lotustcg -c "SELECT COUNT(*) FROM card;"
# Should show number of cards
```