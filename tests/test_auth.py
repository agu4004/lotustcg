"""
Tests for auth.py - Authentication decorators and utilities
"""

import pytest
from unittest.mock import Mock, patch
from flask import Flask, request, session, url_for
from werkzeug.test import Client
from werkzeug.wrappers import Response

import auth
from models import User


class TestAuthDecorators:
    """Test cases for authentication decorators"""
    
    def test_admin_required_with_admin_user(self, app_instance, authenticated_client):
        """Test admin_required decorator with admin user"""
        
        @auth.admin_required
        def test_view():
            return "success"
        
        # Mock current_user as admin
        with patch('auth.current_user') as mock_user:
            mock_user.is_authenticated = True
            mock_user.is_admin.return_value = True
            
            result = test_view()
            assert result == "success"
    
    def test_admin_required_with_regular_user(self, app_instance):
        """Test admin_required decorator with regular user"""
        
        @auth.admin_required
        def test_view():
            return "success"
        
        with app_instance.test_request_context():
            with patch('auth.current_user') as mock_user:
                mock_user.is_authenticated = True
                mock_user.is_admin.return_value = False
                
                with patch('auth.abort') as mock_abort:
                    test_view()
                    mock_abort.assert_called_once_with(403)
    
    def test_admin_required_with_unauthenticated_user(self, app_instance):
        """Test admin_required decorator with unauthenticated user"""
        
        @auth.admin_required
        def test_view():
            return "success"
        
        with app_instance.test_request_context():
            with patch('auth.current_user') as mock_user:
                mock_user.is_authenticated = False
                
                with patch('auth.abort') as mock_abort:
                    test_view()
                    mock_abort.assert_called_once_with(401)
    
    def test_guest_or_user_required_with_authenticated_user(self, app_instance):
        """Test guest_or_user_required decorator with authenticated user"""
        
        @auth.guest_or_user_required
        def test_view():
            return "success"
        
        with patch('auth.current_user') as mock_user:
            mock_user.is_authenticated = True
            
            result = test_view()
            assert result == "success"
    
    def test_guest_or_user_required_with_guest(self, app_instance):
        """Test guest_or_user_required decorator with guest user"""
        
        @auth.guest_or_user_required
        def test_view():
            return "success"
        
        with patch('auth.current_user') as mock_user:
            mock_user.is_authenticated = False
            
            result = test_view()
            assert result == "success"
    
    def test_login_required_with_authenticated_user(self, app_instance):
        """Test login_required decorator with authenticated user"""
        
        @auth.login_required
        def test_view():
            return "success"
        
        with patch('auth.current_user') as mock_user:
            mock_user.is_authenticated = True
            
            result = test_view()
            assert result == "success"
    
    def test_login_required_with_unauthenticated_user(self, app_instance):
        """Test login_required decorator with unauthenticated user"""
        
        @auth.login_required  
        def test_view():
            return "success"
        
        with app_instance.test_request_context():
            with patch('auth.current_user') as mock_user:
                mock_user.is_authenticated = False
                
                with patch('flask_login.unauthorized') as mock_unauthorized:
                    test_view()
                    mock_unauthorized.assert_called_once()


class TestGetRedirectTarget:
    """Test cases for get_redirect_target utility function"""
    
    def test_get_redirect_target_with_next_param(self, app_instance):
        """Test getting redirect target from 'next' parameter"""
        with app_instance.test_request_context('/?next=/catalog'):
            target = auth.get_redirect_target()
            assert target == '/catalog'
    
    def test_get_redirect_target_with_referrer(self, app_instance):
        """Test getting redirect target from referrer header"""
        with app_instance.test_request_context('/', headers={'Referer': 'http://localhost/admin'}):
            with patch('auth.request') as mock_request:
                mock_request.args.get.return_value = None  # No 'next' param
                mock_request.referrer = 'http://localhost/admin'
                mock_request.host_url = 'http://localhost/'
                
                target = auth.get_redirect_target()
                assert target == '/admin'
    
    def test_get_redirect_target_external_referrer(self, app_instance):
        """Test that external referrers are ignored"""
        with app_instance.test_request_context('/'):
            with patch('auth.request') as mock_request:
                mock_request.args.get.return_value = None
                mock_request.referrer = 'http://evil.com/malicious'
                mock_request.host_url = 'http://localhost/'
                
                target = auth.get_redirect_target()
                assert target is None
    
    def test_get_redirect_target_no_referrer(self, app_instance):
        """Test getting redirect target with no referrer"""
        with app_instance.test_request_context('/'):
            with patch('auth.request') as mock_request:
                mock_request.args.get.return_value = None
                mock_request.referrer = None
                
                target = auth.get_redirect_target()
                assert target is None
    
    def test_get_redirect_target_absolute_next_param(self, app_instance):
        """Test that absolute URLs in next param are handled correctly"""
        with app_instance.test_request_context('/?next=http://localhost/admin'):
            with patch('auth.request') as mock_request:
                mock_request.args.get.return_value = 'http://localhost/admin'
                mock_request.host_url = 'http://localhost/'
                
                target = auth.get_redirect_target()
                assert target == '/admin'
    
    def test_get_redirect_target_external_next_param(self, app_instance):
        """Test that external URLs in next param are ignored"""
        with app_instance.test_request_context('/?next=http://evil.com/malicious'):
            with patch('auth.request') as mock_request:
                mock_request.args.get.return_value = 'http://evil.com/malicious'
                mock_request.host_url = 'http://localhost/'
                
                target = auth.get_redirect_target()
                assert target is None
    
    def test_get_redirect_target_malformed_url(self, app_instance):
        """Test handling of malformed URLs"""
        with app_instance.test_request_context('/'):
            with patch('auth.request') as mock_request:
                mock_request.args.get.return_value = 'not-a-valid-url'
                
                # Should not raise exception, should return the relative path
                target = auth.get_redirect_target()
                assert target == 'not-a-valid-url'


class TestAuthIntegration:
    """Integration tests for authentication functionality"""
    
    def test_decorator_preserves_function_metadata(self):
        """Test that decorators preserve original function metadata"""
        
        @auth.admin_required
        def test_function():
            """Test docstring"""
            return "test"
        
        assert test_function.__name__ == "test_function"
        assert test_function.__doc__ == "Test docstring"
    
    def test_multiple_decorators_work_together(self, app_instance):
        """Test that multiple auth decorators can be combined"""
        
        @auth.admin_required
        @auth.login_required
        def test_view():
            return "success"
        
        with patch('auth.current_user') as mock_user:
            mock_user.is_authenticated = True
            mock_user.is_admin.return_value = True
            
            result = test_view()
            assert result == "success"
    
    def test_auth_decorator_error_handling(self, app_instance):
        """Test that auth decorators handle exceptions properly"""
        
        @auth.admin_required
        def failing_view():
            raise ValueError("Test error")
        
        with app_instance.test_request_context():
            with patch('auth.current_user') as mock_user:
                mock_user.is_authenticated = True
                mock_user.is_admin.return_value = True
                
                with pytest.raises(ValueError, match="Test error"):
                    failing_view()
    
    def test_auth_context_availability(self, app_instance):
        """Test that auth decorators work within Flask request context"""
        
        @auth.admin_required
        def context_view():
            # Should be able to access Flask context
            from flask import request
            return f"Method: {request.method}"
        
        with app_instance.test_request_context('/', method='GET'):
            with patch('auth.current_user') as mock_user:
                mock_user.is_authenticated = True
                mock_user.is_admin.return_value = True
                
                result = context_view()
                assert result == "Method: GET"