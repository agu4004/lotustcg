#!/bin/bash

# Simple test watcher script
echo "🚀 Running Lotus TCG Test Suite"
echo "=================================="

# Run core module tests separately to avoid Flask context issues
echo ""
echo "📦 Testing Storage Module..."
python -m pytest tests/test_storage.py -v --tb=short

echo ""
echo "👤 Testing Models Module..."
python -m pytest tests/test_models.py -v --tb=short

echo ""
echo "🔐 Testing Auth Module..."
python -m pytest tests/test_auth.py -v --tb=short -x

echo ""
echo "🌐 Testing App Module..."
python -m pytest tests/test_app.py -v --tb=short -x

echo ""
echo "📈 Generating Coverage Report..."
python -m pytest tests/test_storage.py tests/test_models.py --cov=storage --cov=models --cov-report=term-missing

echo ""
echo "✅ Test run complete!"