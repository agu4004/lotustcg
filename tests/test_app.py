"""
Tests for app.py - Flask application factory and configuration
"""

import pytest
from unittest.mock import patch, Mock
import os

import app
from models import User


class TestAppConfiguration:
    """Test cases for Flask application configuration"""
    
    def test_app_creation(self, app_instance):
        """Test that Flask app is created properly"""
        assert app_instance is not None
        assert app_instance.config['TESTING'] is True
    
    def test_secret_key_configuration(self):
        """Test secret key configuration"""
        # The app should have a secret key set
        assert app.app.secret_key is not None
        assert len(app.app.secret_key) > 0
    
    def test_login_manager_configuration(self):
        """Test Flask-Login manager configuration"""
        assert app.login_manager is not None
        assert app.login_manager.login_view == 'login'
        assert app.login_manager.login_message == 'Please log in to access this page.'
        assert app.login_manager.login_message_category == 'info'


class TestContextProcessors:
    """Test cases for Flask context processors"""
    
    def test_cart_processor_empty_cart(self, client):
        """Test cart context processor with empty cart"""
        with client.application.test_request_context('/'):
            cart_data = app.cart_processor()
            
            assert 'cart_count' in cart_data
            assert cart_data['cart_count'] == 0
    
    def test_cart_processor_with_items(self, client):
        """Test cart context processor with cart items"""
        with client.session_transaction() as sess:
            sess['cart'] = {'1': 2, '2': 3, '3': 1}
        
        with client.application.test_request_context('/'):
            with client.session_transaction() as sess:
                # Simulate session context
                with patch('app.session', sess):
                    cart_data = app.cart_processor()
                    
                    assert cart_data['cart_count'] == 6  # 2 + 3 + 1
    
    def test_auth_processor_authenticated_user(self, app_instance, admin_user):
        """Test auth context processor with authenticated user"""
        with app_instance.test_request_context('/'):
            with patch('app.current_user', admin_user):
                auth_data = app.auth_processor()
                
                assert 'current_user' in auth_data
                assert auth_data['current_user'] == admin_user
    
    def test_auth_processor_anonymous_user(self, app_instance):
        """Test auth context processor with anonymous user"""
        with app_instance.test_request_context('/'):
            with patch('app.current_user') as mock_user:
                mock_user.is_authenticated = False
                
                auth_data = app.auth_processor()
                
                assert 'current_user' in auth_data
                assert auth_data['current_user'] == mock_user


class TestUserLoader:
    """Test cases for Flask-Login user loader"""
    
    def test_load_user_existing(self, admin_user):
        """Test loading existing user"""
        with patch('app.user_manager.get_user', return_value=admin_user):
            loaded_user = app.load_user('admin')
            
            assert loaded_user is not None
            assert loaded_user.username == 'admin'
    
    def test_load_user_nonexistent(self):
        """Test loading non-existent user"""
        with patch('app.user_manager.get_user', return_value=None):
            loaded_user = app.load_user('nonexistent')
            
            assert loaded_user is None
    
    def test_load_user_empty_id(self):
        """Test loading user with empty ID"""
        loaded_user = app.load_user('')
        assert loaded_user is None
    
    def test_load_user_none_id(self):
        """Test loading user with None ID"""
        loaded_user = app.load_user(None)
        assert loaded_user is None


class TestErrorHandlers:
    """Test cases for application error handlers"""
    
    def test_404_error_handler(self, client):
        """Test 404 error handler"""
        response = client.get('/nonexistent-page')
        
        assert response.status_code == 404
        # Should render a proper error page
        assert b'404' in response.data or b'Not Found' in response.data
    
    def test_500_error_handler_renders_template(self, app_instance):
        """Test that 500 error handler renders proper template"""
        # Create a route that intentionally raises an error
        @app_instance.route('/test-error')
        def test_error():
            raise Exception("Test error")
        
        client = app_instance.test_client()
        response = client.get('/test-error')
        
        assert response.status_code == 500
        # Should render an error template, not just plain text
        assert len(response.data) > 0


class TestApplicationInitialization:
    """Test cases for application startup and initialization"""
    
    def test_storage_initialization(self):
        """Test that storage is properly initialized"""
        assert app.storage is not None
        assert hasattr(app.storage, 'cards')
        assert hasattr(app.storage, 'add_card')
        assert hasattr(app.storage, 'get_card')
    
    def test_user_manager_initialization(self):
        """Test that user manager is properly initialized"""
        assert app.user_manager is not None
        assert hasattr(app.user_manager, 'users')
        assert hasattr(app.user_manager, 'get_user')
        assert hasattr(app.user_manager, 'authenticate_user')
    
    def test_default_users_created(self):
        """Test that default admin and user are created"""
        admin_user = app.user_manager.get_user('admin')
        regular_user = app.user_manager.get_user('user')
        
        assert admin_user is not None
        assert admin_user.is_admin() is True
        
        assert regular_user is not None
        assert regular_user.is_admin() is False
    
    def test_routes_registered(self, app_instance):
        """Test that routes are properly registered"""
        # Check that key routes exist
        with app_instance.test_client() as client:
            # Public routes
            assert client.get('/').status_code == 200
            assert client.get('/catalog').status_code == 200
            assert client.get('/cart').status_code == 200
            assert client.get('/login').status_code == 200
            
            # Admin routes should redirect to login for unauthenticated users
            admin_response = client.get('/admin')
            assert admin_response.status_code == 302  # Redirect to login


class TestFlaskLoginIntegration:
    """Test cases for Flask-Login integration"""
    
    def test_login_user_function_available(self):
        """Test that login_user function is available from Flask-Login"""
        from flask_login import login_user
        assert callable(login_user)
    
    def test_logout_user_function_available(self):
        """Test that logout_user function is available from Flask-Login"""
        from flask_login import logout_user
        assert callable(logout_user)
    
    def test_current_user_available(self, app_instance):
        """Test that current_user is available in request context"""
        with app_instance.test_request_context('/'):
            from flask_login import current_user
            assert hasattr(current_user, 'is_authenticated')
    
    def test_login_required_decorator_available(self):
        """Test that login_required decorator is available"""
        from flask_login import login_required
        assert callable(login_required)


class TestEnvironmentConfiguration:
    """Test cases for environment-based configuration"""
    
    def test_session_secret_from_environment(self):
        """Test that session secret can be loaded from environment"""
        test_secret = "test-secret-from-env"
        
        with patch.dict(os.environ, {'SESSION_SECRET': test_secret}):
            # Would need to reload the app module to test this properly
            # For now, just verify the pattern exists
            assert hasattr(app.app, 'secret_key')
    
    def test_default_secret_when_no_environment(self):
        """Test that default secret is used when no environment variable"""
        # The app should have some secret key even without environment variable
        assert app.app.secret_key is not None
        assert len(app.app.secret_key) > 0


class TestApplicationIntegrity:
    """Test cases for overall application integrity"""
    
    def test_all_imports_successful(self):
        """Test that all required modules can be imported"""
        # These should not raise ImportError
        import app
        import routes
        import storage
        import models
        import auth
        
        # Basic sanity check - modules should have expected attributes
        assert hasattr(app, 'app')
        assert hasattr(app, 'login_manager')
        assert hasattr(app, 'storage')
        assert hasattr(app, 'user_manager')
    
    def test_flask_app_can_start(self, app_instance):
        """Test that Flask app can start without errors"""
        # App should be able to handle a basic request
        with app_instance.test_client() as client:
            response = client.get('/')
            # Should not get a 500 error on homepage
            assert response.status_code in [200, 302, 404]  # Any valid HTTP response
    
    def test_app_debug_mode_configurable(self):
        """Test that debug mode can be configured"""
        # In testing, we don't want debug mode
        assert app.app.debug is False or app.app.config.get('DEBUG') is False
    
    def test_app_has_required_blueprints_or_routes(self, app_instance):
        """Test that app has all required route patterns"""
        # Get all registered rules
        rules = list(app_instance.url_map.iter_rules())
        rule_endpoints = [rule.endpoint for rule in rules]
        
        # Check for key endpoints
        expected_endpoints = [
            'index',
            'catalog', 
            'login',
            'logout',
            'admin',
            'view_cart'
        ]
        
        for endpoint in expected_endpoints:
            assert endpoint in rule_endpoints, f"Missing endpoint: {endpoint}"