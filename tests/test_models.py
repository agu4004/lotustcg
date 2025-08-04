"""
Tests for models.py - User and UserManager functionality
"""

import pytest
from models import User, UserManager
from werkzeug.security import check_password_hash


class TestUser:
    """Test cases for User class"""
    
    def test_user_init(self):
        """Test user initialization"""
        user = User("testuser", "hashed_password", "admin")
        
        assert user.username == "testuser"
        assert user.password_hash == "hashed_password"
        assert user.role == "admin"
        assert user.is_authenticated is True
        assert user.is_active is True
        assert user.is_anonymous is False
    
    def test_user_init_default_role(self):
        """Test user initialization with default role"""
        user = User("testuser", "hashed_password")
        
        assert user.role == "user"
        assert user.is_admin() is False
    
    def test_user_get_id(self):
        """Test user get_id method"""
        user = User("testuser", "hashed_password")
        assert user.get_id() == "testuser"
    
    def test_user_is_admin_true(self):
        """Test is_admin method for admin user"""
        user = User("admin_user", "hashed_password", "admin")
        assert user.is_admin() is True
    
    def test_user_is_admin_false(self):
        """Test is_admin method for regular user"""
        user = User("regular_user", "hashed_password", "user")
        assert user.is_admin() is False
    
    def test_user_check_password_correct(self):
        """Test password checking with correct password"""
        # Create user with properly hashed password
        from werkzeug.security import generate_password_hash
        password = "test_password123"
        password_hash = generate_password_hash(password)
        
        user = User("testuser", password_hash)
        assert user.check_password(password) is True
    
    def test_user_check_password_incorrect(self):
        """Test password checking with incorrect password"""
        from werkzeug.security import generate_password_hash
        password = "test_password123"
        password_hash = generate_password_hash(password)
        
        user = User("testuser", password_hash)
        assert user.check_password("wrong_password") is False
    
    def test_user_str_representation(self):
        """Test string representation of user"""
        user = User("testuser", "hashed_password", "admin")
        assert str(user) == "User: testuser (admin)"


class TestUserManager:
    """Test cases for UserManager class"""
    
    def test_user_manager_init(self, user_manager):
        """Test UserManager initialization"""
        assert isinstance(user_manager.users, dict)
        assert len(user_manager.users) >= 2  # Admin and user should be created
        assert "admin" in user_manager.users
        assert "user" in user_manager.users
    
    def test_create_user_success(self, user_manager):
        """Test creating a new user successfully"""
        result = user_manager.create_user("newuser", "password123", "user")
        
        assert result is True
        assert "newuser" in user_manager.users
        
        user = user_manager.users["newuser"]
        assert user.username == "newuser"
        assert user.role == "user"
        assert user.check_password("password123") is True
    
    def test_create_user_duplicate_username(self, user_manager):
        """Test creating user with duplicate username"""
        # First user should succeed
        result1 = user_manager.create_user("testuser", "password123")
        assert result1 is True
        
        # Second user with same username should fail
        result2 = user_manager.create_user("testuser", "different_password")
        assert result2 is False
        
        # Original user should be unchanged
        user = user_manager.get_user("testuser")
        assert user.check_password("password123") is True
        assert user.check_password("different_password") is False
    
    def test_create_user_admin_role(self, user_manager):
        """Test creating admin user"""
        result = user_manager.create_user("admin_test", "admin_pass", "admin")
        
        assert result is True
        user = user_manager.get_user("admin_test")
        assert user.is_admin() is True
    
    def test_get_user_existing(self, user_manager):
        """Test getting existing user"""
        user_manager.create_user("gettest", "password123")
        
        user = user_manager.get_user("gettest")
        assert user is not None
        assert user.username == "gettest"
    
    def test_get_user_nonexistent(self, user_manager):
        """Test getting non-existent user"""
        user = user_manager.get_user("nonexistent")
        assert user is None
    
    def test_get_user_case_sensitive(self, user_manager):
        """Test that usernames are case sensitive"""
        user_manager.create_user("TestUser", "password123")
        
        user1 = user_manager.get_user("TestUser")
        user2 = user_manager.get_user("testuser")
        user3 = user_manager.get_user("TESTUSER")
        
        assert user1 is not None
        assert user2 is None
        assert user3 is None
    
    def test_authenticate_user_success(self, user_manager):
        """Test successful user authentication"""
        user_manager.create_user("authtest", "correct_password")
        
        user = user_manager.authenticate_user("authtest", "correct_password")
        assert user is not None
        assert user.username == "authtest"
    
    def test_authenticate_user_wrong_password(self, user_manager):
        """Test authentication with wrong password"""
        user_manager.create_user("authtest", "correct_password")
        
        user = user_manager.authenticate_user("authtest", "wrong_password")
        assert user is None
    
    def test_authenticate_user_nonexistent(self, user_manager):
        """Test authentication with non-existent user"""
        user = user_manager.authenticate_user("nonexistent", "password")
        assert user is None
    
    def test_authenticate_user_empty_credentials(self, user_manager):
        """Test authentication with empty credentials"""
        user1 = user_manager.authenticate_user("", "password")
        user2 = user_manager.authenticate_user("username", "")
        user3 = user_manager.authenticate_user("", "")
        
        assert user1 is None
        assert user2 is None
        assert user3 is None
    
    def test_get_all_users(self, user_manager):
        """Test getting all users"""
        # Add some test users
        user_manager.create_user("user1", "pass1")
        user_manager.create_user("user2", "pass2", "admin")
        
        all_users = user_manager.get_all_users()
        
        assert isinstance(all_users, dict)
        assert len(all_users) >= 4  # At least admin, user, user1, user2
        assert "admin" in all_users
        assert "user" in all_users
        assert "user1" in all_users
        assert "user2" in all_users
        
        # Verify user objects
        assert all_users["user1"].username == "user1"
        assert all_users["user2"].is_admin() is True
    
    def test_get_all_users_immutable(self, user_manager):
        """Test that get_all_users returns a copy, not the original dict"""
        all_users = user_manager.get_all_users()
        original_count = len(all_users)
        
        # Modify the returned dict
        all_users["fake_user"] = "fake_data"
        
        # Original should be unchanged
        all_users_again = user_manager.get_all_users()
        assert len(all_users_again) == original_count
        assert "fake_user" not in all_users_again
    
    def test_default_admin_user_exists(self, user_manager):
        """Test that default admin user is created"""
        admin_user = user_manager.get_user("admin")
        
        assert admin_user is not None
        assert admin_user.is_admin() is True
        assert admin_user.check_password("admin123") is True
    
    def test_default_regular_user_exists(self, user_manager):
        """Test that default regular user is created"""
        regular_user = user_manager.get_user("user")
        
        assert regular_user is not None
        assert regular_user.is_admin() is False
        assert regular_user.check_password("user123") is True
    
    def test_password_hashing_security(self, user_manager):
        """Test that passwords are properly hashed and not stored in plain text"""
        password = "test_password_security"
        user_manager.create_user("security_test", password)
        
        user = user_manager.get_user("security_test")
        
        # Password hash should not equal the original password
        assert user.password_hash != password
        
        # But check_password should still work
        assert user.check_password(password) is True
        
        # Hash should look like a proper bcrypt/werkzeug hash
        assert len(user.password_hash) > 50  # Hashes are typically quite long
        assert user.password_hash.startswith(('$', 'pbkdf2:', 'scrypt:'))  # Common hash prefixes