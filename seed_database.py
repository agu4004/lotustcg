#!/usr/bin/env python3
"""
Seed database with sample trading cards
"""
from app import app, db
from models import Card, User
from werkzeug.security import generate_password_hash


def seed_cards():
    """Add sample cards to the database"""
    sample_cards = [
        {
            'name': 'Lightning Bolt',
            'set_name': 'Core Set 2021',
            'rarity': 'Common',
            'condition': 'Near Mint',
            'price': 1.50,
            'quantity': 25,
            'description': 'Deal 3 damage to any target'
        },
        {
            'name': 'Black Lotus',
            'set_name': 'Alpha',
            'rarity': 'Mythic Rare',
            'condition': 'Light Play',
            'price': 15000.00,
            'quantity': 1,
            'description': 'The most powerful artifact in Magic history'
        },
        {
            'name': 'Counterspell',
            'set_name': 'Beta',
            'rarity': 'Common',
            'condition': 'Near Mint',
            'price': 25.00,
            'quantity': 8,
            'description': 'Counter target spell'
        },
        {
            'name': 'Force of Will',
            'set_name': 'Alliances',
            'rarity': 'Rare',
            'condition': 'Near Mint',
            'price': 85.00,
            'quantity': 3,
            'description': 'Counter target spell by paying 1 life and exiling a blue card'
        },
        {
            'name': 'Mox Ruby',
            'set_name': 'Alpha',
            'rarity': 'Mythic Rare',
            'condition': 'Moderate Play',
            'price': 8500.00,
            'quantity': 1,
            'description': 'Adds one red mana to your mana pool'
        },
        {
            'name': 'Serra Angel',
            'set_name': 'Core Set 2020',
            'rarity': 'Uncommon',
            'condition': 'Near Mint',
            'price': 0.75,
            'quantity': 50,
            'description': 'Flying, vigilance 4/4 Angel'
        },
        {
            'name': 'Shivan Dragon',
            'set_name': 'Core Set 2019',
            'rarity': 'Rare',
            'condition': 'Near Mint',
            'price': 2.25,
            'quantity': 12,
            'description': 'Flying 5/5 Dragon'
        },
        {
            'name': 'Tarmogoyf',
            'set_name': 'Modern Masters 2017',
            'rarity': 'Mythic Rare',
            'condition': 'Near Mint',
            'price': 45.00,
            'quantity': 4,
            'description': 'Power and toughness equal to number of card types in all graveyards'
        }
    ]
    
    # Check if cards already exist
    existing_cards = Card.query.count()
    if existing_cards > 0:
        print(f"Database already has {existing_cards} cards. Skipping seeding.")
        return
    
    # Add sample cards
    cards_added = 0
    for card_data in sample_cards:
        card = Card(**card_data)
        db.session.add(card)
        cards_added += 1
        print(f"Added: {card_data['name']} - {card_data['price']} VND")
    
    try:
        db.session.commit()
        print(f"\n✅ Successfully seeded {cards_added} cards to the database!")
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error seeding cards: {e}")


def verify_users():
    """Verify default users exist"""
    admin = User.query.filter_by(username='admin').first()
    user = User.query.filter_by(username='user').first()
    
    if admin:
        print(f"✅ Admin user exists: {admin.username} (role: {admin.role})")
    else:
        print("❌ Admin user not found")
    
    if user:
        print(f"✅ Regular user exists: {user.username} (role: {user.role})")
    else:
        print("❌ Regular user not found")


if __name__ == '__main__':
    with app.app_context():
        print("🌱 Seeding The Lotus TCG Database...")
        print("=" * 40)
        
        # Verify users
        print("\n👤 Checking users...")
        verify_users()
        
        # Seed cards
        print("\n🃏 Seeding cards...")
        seed_cards()
        
        print("\n🎉 Seeding complete!")
        print(f"Total cards in database: {Card.query.count()}")
        print(f"Total users in database: {User.query.count()}")