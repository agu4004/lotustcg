"""
SQLAlchemy models for Lotus TCG
"""
import os
from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import String, Integer, Numeric, DateTime, Text, func
from sqlalchemy.orm import Mapped, mapped_column

# Import db from app - will be available after app initialization
from app import db


class User(UserMixin, db.Model):
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default='user')
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    
    def check_password(self, password: str) -> bool:
        """Check if provided password matches hash"""
        return check_password_hash(self.password_hash, password)
    
    def is_admin(self) -> bool:
        """Check if user has admin role"""
        return self.role == 'admin'
    
    def __str__(self) -> str:
        """String representation of user"""
        return f"User: {self.username} ({self.role})"


class Card(db.Model):
    __tablename__ = "cards"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    set_name: Mapped[str] = mapped_column(String(80), nullable=False, default='Unknown')
    rarity: Mapped[str] = mapped_column(String(20), nullable=False, default='Common')
    condition: Mapped[str] = mapped_column(String(20), nullable=False, default='Near Mint')
    price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0.0)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    
    def to_dict(self):
        """Convert card to dictionary for templates"""
        return {
            'id': str(self.id),
            'name': self.name,
            'set_name': self.set_name,
            'rarity': self.rarity,
            'condition': self.condition,
            'price': float(self.price),
            'quantity': self.quantity,
            'description': self.description or '',
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
    
    def __str__(self) -> str:
        """String representation of card"""
        return f"Card: {self.name} ({self.set_name}) - {self.price} VND"


def initialize_default_users():
    """Initialize default admin and test users if they don't exist"""
    # Check if admin user exists
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        admin_password = os.environ.get('ADMIN_PASSWORD', 'admin123')
        admin_hash = generate_password_hash(admin_password)
        admin = User(username='admin', password_hash=admin_hash, role='admin')
        db.session.add(admin)
    
    # Check if test user exists
    user = User.query.filter_by(username='user').first()
    if not user:
        user_hash = generate_password_hash('user123')
        user = User(username='user', password_hash=user_hash, role='user')
        db.session.add(user)
    
    # Commit changes
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Error initializing users: {e}")