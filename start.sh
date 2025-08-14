#!/bin/bash
# Quick start script for Lotus TCG

echo "🚀 Starting Lotus TCG..."

# Activate virtual environment
source venv/bin/activate

# Load environment variables
export $(cat .env | xargs)

# Start application with Gunicorn
gunicorn --bind 0.0.0.0:5000 --workers 3 main:app

echo "✅ Application started on http://localhost:5000"
echo "📚 Admin login: admin/admin123"
echo "👤 User login: user/user123"
