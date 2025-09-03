"""
SQLAlchemy models for The Lotus TCG
"""
import os
from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import String, Integer, Numeric, DateTime, Text, func, ForeignKey
from sqlalchemy.orm import relationship
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
    image_url: Mapped[str] = mapped_column(String(500), nullable=True)
    foiling: Mapped[str] = mapped_column(String(20), nullable=False, default='NF')
    art_style: Mapped[str] = mapped_column(String(20), nullable=False, default='normal')
    is_deleted: Mapped[bool] = mapped_column(db.Boolean, nullable=False, default=False)
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
            'image_url': self.image_url or '',
            'foiling': self.foiling,
            'art_style': self.art_style,
            'is_deleted': self.is_deleted,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

    def soft_delete(self):
        """Mark card as deleted without removing from database"""
        self.is_deleted = True
        self.updated_at = func.now()
    
    def __str__(self) -> str:
        """String representation of card"""
        return f"Card: {self.name} ({self.set_name}) - {self.price} VND"


class Order(db.Model):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)  # e.g., ORD-20240101-001
    customer_name: Mapped[str] = mapped_column(String(100), nullable=False)
    contact_number: Mapped[str] = mapped_column(String(20), nullable=False)
    facebook_details: Mapped[str] = mapped_column(Text, nullable=True)
    shipment_method: Mapped[str] = mapped_column(String(20), nullable=False)  # 'shipping' or 'pickup'
    pickup_location: Mapped[str] = mapped_column(String(50), nullable=True)  # 'Iron Hammer' or 'Floating Dojo'
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='pending')
    total_amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)

    # Shipping address fields (required when shipment_method is 'shipping')
    shipping_address: Mapped[str] = mapped_column(Text, nullable=True)
    shipping_city: Mapped[str] = mapped_column(String(100), nullable=True)
    shipping_province: Mapped[str] = mapped_column(String(100), nullable=True)
    shipping_postal_code: Mapped[str] = mapped_column(String(20), nullable=True)
    shipping_country: Mapped[str] = mapped_column(String(100), nullable=True, default='Vietnam')

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationship to order items
    items = relationship('OrderItem', backref='order', lazy=True, cascade='all, delete-orphan')

    def to_dict(self):
        """Convert order to dictionary for templates"""
        return {
            'id': self.id,
            'customer_name': self.customer_name,
            'contact_number': self.contact_number,
            'facebook_details': self.facebook_details,
            'shipment_method': self.shipment_method,
            'pickup_location': self.pickup_location,
            'status': self.status,
            'total_amount': float(self.total_amount),
            'shipping_address': self.shipping_address,
            'shipping_city': self.shipping_city,
            'shipping_province': self.shipping_province,
            'shipping_postal_code': self.shipping_postal_code,
            'shipping_country': self.shipping_country,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

    def __str__(self) -> str:
        """String representation of order"""
        return f"Order: {self.id} - {self.customer_name} - {self.total_amount} VND"


class OrderItem(db.Model):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[str] = mapped_column(String(20), ForeignKey('orders.id'), nullable=False)
    card_id: Mapped[int] = mapped_column(Integer, ForeignKey('cards.id'), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    total_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)

    # Relationship to card
    card = relationship('Card', backref='order_items')

    def to_dict(self):
        """Convert order item to dictionary for templates"""
        return {
            'id': self.id,
            'order_id': self.order_id,
            'card_id': self.card_id,
            'quantity': self.quantity,
            'unit_price': float(self.unit_price),
            'total_price': float(self.total_price),
            'card': self.card.to_dict() if self.card else None
        }

    def __str__(self) -> str:
        """String representation of order item"""
        return f"OrderItem: {self.card.name if self.card else 'Unknown Card'} x{self.quantity}"


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