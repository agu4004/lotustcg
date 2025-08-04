"""
User models and authentication classes for Flask-Login
"""
import os
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from typing import Dict, Optional


class User(UserMixin):
    def __init__(self, username: str, password_hash: str, role: str = 'user'):
        self.id = username
        self.username = username
        self.password_hash = password_hash
        self.role = role
    
    def check_password(self, password: str) -> bool:
        """Check if provided password matches hash"""
        return check_password_hash(self.password_hash, password)
    
    def is_admin(self) -> bool:
        """Check if user has admin role"""
        return self.role == 'admin'
    
    def __str__(self) -> str:
        """String representation of user"""
        return f"User: {self.username} ({self.role})"


class UserManager:
    def __init__(self):
        self.users: Dict[str, User] = {}
        self._initialize_admin_user()
    
    def _initialize_admin_user(self):
        """Initialize admin user from environment variables"""
        admin_username = os.environ.get('ADMIN_USERNAME', 'admin')
        admin_password = os.environ.get('ADMIN_PASSWORD', 'admin123')
        
        # Create admin user
        admin_hash = generate_password_hash(admin_password)
        self.users[admin_username] = User(admin_username, admin_hash, 'admin')
        
        # Add a default regular user for testing
        user_hash = generate_password_hash('user123')
        self.users['user'] = User('user', user_hash, 'user')
    
    def get_user(self, username: str) -> Optional[User]:
        """Get user by username"""
        return self.users.get(username)
    
    def create_user(self, username: str, password: str, role: str = 'user') -> bool:
        """Create a new user"""
        if username in self.users:
            return False
        
        password_hash = generate_password_hash(password)
        self.users[username] = User(username, password_hash, role)
        return True
    
    def authenticate_user(self, username: str, password: str) -> Optional[User]:
        """Authenticate user with username and password"""
        user = self.get_user(username)
        if user and user.check_password(password):
            return user
        return None
    
    def get_all_users(self) -> Dict[str, User]:
        """Get all users (admin only)"""
        return self.users.copy()


# Global user manager instance
user_manager = UserManager()