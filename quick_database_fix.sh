#!/bin/bash
echo "🔄 Creating cardmarketscan database..."

# Create new database and user
sudo -u postgres psql << SQL
CREATE DATABASE cardmarketscan;
CREATE USER cmsuser WITH ENCRYPTED PASSWORD 'cms_secure_password_2024';
GRANT ALL PRIVILEGES ON DATABASE cardmarketscan TO cmsuser;
ALTER DATABASE cardmarketscan OWNER TO cmsuser;
\q
SQL

echo "✅ Database created successfully"

# Test connection
echo "🔍 Testing database connection..."
psql -h localhost -U cmsuser -d cardmarketscan -c "SELECT current_database(), current_user;"

echo "🎉 Database setup complete!"
echo "Use this DATABASE_URL:"
echo "postgresql://cmsuser:cms_secure_password_2024@localhost:5432/cardmarketscan"
