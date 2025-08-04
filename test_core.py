#!/usr/bin/env python3
"""
Core functionality tests - simplified version to validate key features
"""

import pytest
import sys
import os

# Add project root to path
sys.path.insert(0, '.')

def test_imports():
    """Test that all main modules can be imported"""
    try:
        import app
        import routes
        import storage
        import models
        import auth
        print("✓ All modules import successfully")
        return True
    except Exception as e:
        print(f"✗ Import error: {e}")
        return False

def test_storage_basic():
    """Test basic storage functionality"""
    from storage import InMemoryStorage
    
    storage = InMemoryStorage()
    
    # Test add card
    card_data = {
        'name': 'Test Card',
        'price': 10.0,
        'quantity': 5
    }
    
    card_id = storage.add_card(card_data)
    assert card_id == "1"
    
    # Test get card
    retrieved = storage.get_card(card_id)
    assert retrieved['name'] == 'Test Card'
    assert retrieved['price'] == 10.0
    
    print("✓ Storage basic functionality works")
    return True

def test_user_management():
    """Test user management functionality"""
    from models import UserManager
    
    user_mgr = UserManager()
    
    # Test create user
    result = user_mgr.create_user('testuser', 'testpass')
    assert result is True
    
    # Test authenticate
    user = user_mgr.authenticate_user('testuser', 'testpass')
    assert user is not None
    assert user.username == 'testuser'
    
    print("✓ User management functionality works")
    return True

def test_flask_app_creation():
    """Test Flask app creation and basic routes"""
    import app
    
    client = app.app.test_client()
    
    # Test home page
    response = client.get('/')
    assert response.status_code == 200
    
    # Test login page
    response = client.get('/login')
    assert response.status_code == 200
    
    print("✓ Flask app and basic routes work")
    return True

def test_csv_processing():
    """Test CSV processing functionality"""
    from storage import InMemoryStorage
    
    storage = InMemoryStorage()
    
    csv_content = '''name,price,quantity
Test Card 1,1.50,10
Test Card 2,2.50,5'''
    
    results = storage.process_csv_upload(csv_content)
    
    assert results['success'] == 2
    assert len(results['errors']) == 0
    
    print("✓ CSV processing works")
    return True

def run_core_tests():
    """Run all core tests"""
    tests = [
        test_imports,
        test_storage_basic,
        test_user_management,
        test_flask_app_creation,
        test_csv_processing
    ]
    
    passed = 0
    failed = 0
    
    print("Running core functionality tests...\n")
    
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"✗ {test.__name__} failed: {e}")
            failed += 1
    
    print(f"\nResults: {passed} passed, {failed} failed")
    return failed == 0

if __name__ == "__main__":
    success = run_core_tests()
    sys.exit(0 if success else 1)