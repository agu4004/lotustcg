# Environment Variables Fix

## Issue
Getting this error when initializing database:
```
RuntimeError: Either 'SQLALCHEMY_DATABASE_URI' or 'SQLALCHEMY_BINDS' must be set.
```

## Root Cause
The `DATABASE_URL` environment variable is not being loaded properly when running Python commands.

## Quick Fix

Run these commands in your terminal:

```bash
cd /home/ubuntu/cardmarketscan
source venv/bin/activate

# Export environment variables for current session
export DATABASE_URL=postgresql://cmsuser:cms_secure_password_2024@localhost:5432/cardmarketscan
export SESSION_SECRET=your_super_secret_session_key_here_change_this

# Verify the variable is set
echo "DATABASE_URL: $DATABASE_URL"

# Now try database initialization again
python -c "
import os
print('DATABASE_URL:', os.environ.get('DATABASE_URL'))
from app import app, db
with app.app_context():
    db.create_all()
    print('Database tables created successfully')
"
```

## Make Environment Variables Permanent

Add to your shell profile so they persist:

```bash
echo 'export DATABASE_URL=postgresql://cmsuser:cms_secure_password_2024@localhost:5432/cardmarketscan' >> ~/.bashrc
echo 'export SESSION_SECRET=your_super_secret_session_key_here_change_this' >> ~/.bashrc
source ~/.bashrc
```

## Alternative: Use python-dotenv

If the above doesn't work, install python-dotenv to automatically load .env files:

```bash
pip install python-dotenv

# Create .env file
cat > .env << EOF
DATABASE_URL=postgresql://cmsuser:cms_secure_password_2024@localhost:5432/cardmarketscan
SESSION_SECRET=your_super_secret_session_key_here_change_this
FLASK_APP=main.py
FLASK_ENV=production
EOF

# Test with dotenv
python -c "
from dotenv import load_dotenv
load_dotenv()
import os
print('DATABASE_URL:', os.environ.get('DATABASE_URL'))
from app import app, db
with app.app_context():
    db.create_all()
    print('Database tables created successfully')
"
```

## Verification Steps

1. Check environment variable is set:
   ```bash
   echo $DATABASE_URL
   ```

2. Test database connection:
   ```bash
   psql $DATABASE_URL -c "\dt"
   ```

3. Verify Flask can read the variable:
   ```bash
   python -c "import os; print('DATABASE_URL found:', 'DATABASE_URL' in os.environ)"
   ```

The key is ensuring the `DATABASE_URL` environment variable is properly exported before running any Python commands that import the Flask app.