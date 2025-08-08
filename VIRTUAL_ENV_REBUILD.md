# Virtual Environment Rebuild Guide

## Issue
Gunicorn still not found after pip install, indicating virtual environment issues.

## Complete Virtual Environment Rebuild

### 1. Remove and Recreate Virtual Environment
```bash
cd /home/ubuntu/cardmarketscan
rm -rf venv/
python3 -m venv venv
source venv/bin/activate
```

### 2. Upgrade pip and Install Packages
```bash
pip install --upgrade pip
pip install flask flask-login flask-sqlalchemy flask-migrate werkzeug psycopg2-binary gunicorn
```

### 3. Verify Installation
```bash
which python
which pip  
which gunicorn
python --version
gunicorn --version
```

### 4. Test Application
```bash
export $(cat .env | xargs)
python -c "from main import app; print('App imports successfully')"
gunicorn --bind 127.0.0.1:5000 main:app &
sleep 2
curl http://127.0.0.1:5000
pkill gunicorn
```

### 5. Alternative: Use System Python if Virtual Env Fails
If virtual environment keeps failing:
```bash
# Install packages system-wide (temporary fix)
sudo apt update
sudo apt install -y python3-pip python3-flask python3-psycopg2
sudo pip3 install gunicorn flask-login flask-sqlalchemy flask-migrate

# Update systemd service to use system python
sudo nano /etc/systemd/system/cardmarketscan.service
```

Change ExecStart to:
```
ExecStart=/usr/local/bin/gunicorn --workers 3 --bind 127.0.0.1:5000 main:app
```

### 6. Check File Permissions
```bash
ls -la /home/ubuntu/cardmarketscan/
chown -R ubuntu:ubuntu /home/ubuntu/cardmarketscan/
```