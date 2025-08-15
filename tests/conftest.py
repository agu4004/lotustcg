"""
Pytest configuration and fixtures for The Lotus TCG tests
"""

import pytest
import tempfile
import os
from unittest.mock import patch

# Import the main application
import sys
sys.path.insert(0, '.')

import app
from storage import InMemoryStorage
from storage_db import DatabaseStorage
from models import User


@pytest.fixture
def app_instance():
    """Create and configure a test Flask application"""
    # Create a temporary secret key for testing
    app.app.config['TESTING'] = True
    app.app.config['WTF_CSRF_ENABLED'] = False
    app.app.config['SECRET_KEY'] = 'test-secret-key'
    
    with app.app.app_context():
        yield app.app


@pytest.fixture
def client(app_instance):
    """Create a test client for the Flask application"""
    return app_instance.test_client()


@pytest.fixture
def storage():
    """Create a fresh InMemoryStorage instance for testing (legacy tests)"""
    return InMemoryStorage()


@pytest.fixture
def db_storage():
    """Create a DatabaseStorage instance for database tests"""
    return DatabaseStorage()


@pytest.fixture
def sample_card_data():
    """Sample card data for testing"""
    return {
        'name': 'Lightning Bolt',
        'set_name': 'Alpha',
        'rarity': 'Common',
        'condition': 'Near Mint',
        'price': 1.50,
        'quantity': 10,
        'description': 'Classic red instant spell'
    }


@pytest.fixture
def sample_cards_list():
    """List of sample cards for testing"""
    return [
        {
            'name': 'Lightning Bolt',
            'set_name': 'Alpha',
            'rarity': 'Common',
            'condition': 'Near Mint',
            'price': 1.50,
            'quantity': 10,
            'description': 'Classic red instant spell'
        },
        {
            'name': 'Black Lotus',
            'set_name': 'Alpha',
            'rarity': 'Majestic',
            'condition': 'Light Play',
            'price': 5000.00,
            'quantity': 1,
            'description': 'The most powerful mox'
        },
        {
            'name': 'Counterspell',
            'set_name': 'Beta',
            'rarity': 'Common',
            'condition': 'Near Mint',
            'price': 25.00,
            'quantity': 5,
            'description': 'Counter target spell'
        }
    ]


@pytest.fixture
def csv_content():
    """Sample CSV content for testing uploads"""
    return '''name,set_name,rarity,condition,price,quantity,description
Lightning Bolt,Alpha,Common,Near Mint,1.50,10,Classic red instant spell
Black Lotus,Alpha,Majestic,Light Play,5000.00,1,The most powerful mox
Counterspell,Beta,Common,Near Mint,25.00,5,Counter target spell'''


@pytest.fixture
def admin_user(user_manager):
    """Create an admin user for testing"""
    user_manager.create_user('test_admin', 'password123', role='admin')
    return user_manager.get_user('test_admin')


@pytest.fixture
def regular_user(user_manager):
    """Create a regular user for testing"""
    user_manager.create_user('test_user', 'password123', role='user')
    return user_manager.get_user('test_user')


@pytest.fixture
def authenticated_client(client, admin_user):
    """Create a client with authenticated admin user"""
    with patch('flask_login.current_user', admin_user):
        with client.session_transaction() as sess:
            sess['_user_id'] = admin_user.get_id()
            sess['_fresh'] = True
        yield client


@pytest.fixture
def user_authenticated_client(client, regular_user):
    """Create a client with authenticated regular user"""
    with client.session_transaction() as sess:
        sess['_user_id'] = regular_user.get_id()
        sess['_fresh'] = True
    return client


class MockFlashMessages:
    """Mock flash messages for testing"""
    def __init__(self):
        self.messages = []
    
    def add(self, message, category='message'):
        self.messages.append((category, message))
    
    def get(self, with_categories=False):
        if with_categories:
            return self.messages[:]
        return [msg[1] for msg in self.messages]
    
    def clear(self):
        self.messages.clear()


@pytest.fixture
def mock_flash():
    """Mock flash function for testing"""
    flash_mock = MockFlashMessages()
    
    def flash_func(message, category='message'):
        flash_mock.add(message, category)
    
    with patch('flask.flash', side_effect=flash_func):
        yield flash_mock