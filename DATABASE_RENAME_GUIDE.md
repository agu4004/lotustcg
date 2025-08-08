# Database Rename Guide: tcg_card_shop → cardmarketscan

## Quick Solution

Run these commands to rename your database:

### 1. Create New Database and User
```bash
sudo -u postgres psql
CREATE DATABASE cardmarketscan;
CREATE USER cmsuser WITH ENCRYPTED PASSWORD 'cms_secure_password_2024';
GRANT ALL PRIVILEGES ON DATABASE cardmarketscan TO cmsuser;
ALTER DATABASE cardmarketscan OWNER TO cmsuser;
\q
```

### 2. Migrate Data (if you have existing data)
```bash
# Backup existing database
pg_dump -h localhost -U tcguser tcg_card_shop > tcg_backup.sql

# Import to new database
psql -h localhost -U cmsuser -d cardmarketscan < tcg_backup.sql
```

### 3. Update Environment Variables
```bash
cd /home/ubuntu/cardmarketscan
source venv/bin/activate

export DATABASE_URL=postgresql://cmsuser:cms_secure_password_2024@localhost:5432/cardmarketscan
export SESSION_SECRET=your_super_secret_session_key_here_change_this

echo "Updated DATABASE_URL: $DATABASE_URL"
```

### 4. Test New Database
```bash
# Test connection
psql "$DATABASE_URL" -c "\dt"

# Initialize tables
python -c "
import os
print('DATABASE_URL:', os.environ.get('DATABASE_URL'))
from app import app, db
with app.app_context():
    db.create_all()
    print('Database tables created successfully')
"

# Seed with sample data
python seed_database.py
```

### 5. Make Environment Variables Permanent
```bash
echo 'export DATABASE_URL=postgresql://cmsuser:cms_secure_password_2024@localhost:5432/cardmarketscan' >> ~/.bashrc
source ~/.bashrc
```

## Alternative: Fresh Start (Recommended)

If you don't need existing data, simply create fresh database:

```bash
sudo -u postgres psql
CREATE DATABASE cardmarketscan;
CREATE USER cmsuser WITH ENCRYPTED PASSWORD 'cms_secure_password_2024';
GRANT ALL PRIVILEGES ON DATABASE cardmarketscan TO cmsuser;
ALTER DATABASE cardmarketscan OWNER TO cmsuser;
\q
```

Then continue with steps 3-5 above.