# Service Status and Connection Troubleshooting

## Check Service Status
```bash
# Check if service is actually running
sudo systemctl status cardmarketscan --no-pager

# Check recent logs
sudo journalctl -u cardmarketscan -n 20 --no-pager

# Check if anything is listening on port 5000
sudo netstat -tlnp | grep 5000
# OR
sudo ss -tlnp | grep 5000
```

## Test Application Components
```bash
cd /home/ubuntu/cardmarketscan
source venv/bin/activate
export $(cat .env | xargs)

# Test database connection
python -c "
from app import app, db
with app.app_context():
    try:
        db.engine.execute('SELECT 1')
        print('✓ Database connection successful')
    except Exception as e:
        print('✗ Database connection failed:', str(e))
"

# Test if main.py can start
python main.py
```

## Manual Gunicorn Test
```bash
cd /home/ubuntu/cardmarketscan
source venv/bin/activate
export $(cat .env | xargs)

# Start gunicorn manually with verbose logging
gunicorn --bind 0.0.0.0:5000 --log-level debug --access-logfile - --error-logfile - main:app
```

## Common Issues and Solutions

### Issue 1: Service Not Starting
If systemctl status shows "inactive" or "failed":
```bash
# Check detailed error logs
sudo journalctl -u cardmarketscan -f --no-pager
```

### Issue 2: Port Binding Issues
If port is in use:
```bash
# Find what's using port 5000
sudo lsof -i :5000
# Kill if necessary
sudo pkill -f gunicorn
```

### Issue 3: Database Connection Problems
```bash
# Test database directly
psql "$DATABASE_URL" -c "SELECT current_database();"
```

### Issue 4: Environment Variables Not Loading
```bash
# Verify .env file contents
cat .env
# Test loading
export $(cat .env | xargs) && echo "DATABASE_URL: $DATABASE_URL"
```