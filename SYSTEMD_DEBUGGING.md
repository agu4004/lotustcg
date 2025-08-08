# Systemd Service Debugging - Application Exit Codes

## Issue
Service keeps restarting and failing with exit-code errors. This means the application itself is crashing, not a systemd configuration issue.

## Debugging Steps

### 1. Check Detailed Service Logs
```bash
sudo journalctl -u cardmarketscan -n 50 --no-pager
```

### 2. Check Application Logs with More Detail
```bash
sudo journalctl -u cardmarketscan -f --no-pager
```

### 3. Test Application Manually
```bash
cd /home/ubuntu/cardmarketscan
source venv/bin/activate

# Load environment variables from .env file
export $(cat .env | xargs)

# Test if the app can start
python main.py
```

### 4. Test Gunicorn Command Directly
```bash
cd /home/ubuntu/cardmarketscan
source venv/bin/activate
export $(cat .env | xargs)

# Run the exact command from systemd
/home/ubuntu/cardmarketscan/venv/bin/gunicorn --workers 3 --bind 127.0.0.1:5000 main:app
```

### 5. Common Issues and Fixes

**Database Connection Issues:**
```bash
# Test database connectivity
psql "$DATABASE_URL" -c "SELECT 1;"
```

**Python Path Issues:**
```bash
# Check if main.py can be imported
cd /home/ubuntu/cardmarketscan
python -c "import main; print('main.py imports successfully')"
```

**Missing Dependencies:**
```bash
# Check all packages are installed
pip list | grep -E "(flask|gunicorn|psycopg2)"
```

**Permission Issues:**
```bash
# Check file ownership
ls -la /home/ubuntu/cardmarketscan/
```

### 6. Temporary Fix - Run with More Verbose Logging
Edit the systemd service to add debugging:
```bash
sudo nano /etc/systemd/system/cardmarketscan.service
```

Change ExecStart line to:
```
ExecStart=/home/ubuntu/cardmarketscan/venv/bin/gunicorn --workers 1 --bind 127.0.0.1:5000 --log-level debug --access-logfile - --error-logfile - main:app
```

Then:
```bash
sudo systemctl daemon-reload
sudo systemctl restart cardmarketscan
sudo journalctl -u cardmarketscan -f
```

## Expected Results
- Step 3 should show if the app can start at all
- Step 4 should show if gunicorn can serve the app
- Step 6 should provide detailed error messages