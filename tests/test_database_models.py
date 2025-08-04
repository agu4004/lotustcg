"""
Test suite for PostgreSQL database models and operations
"""
import pytest
from app import app, db
from models import User, Card, initialize_default_users
from storage_db import DatabaseStorage
from werkzeug.security import generate_password_hash


@pytest.fixture
def app_context():
    """Create application context for database tests"""
    with app.app_context():
        yield app


@pytest.fixture
def db_session(app_context):
    """Create fresh database session for each test"""
    # Create all tables
    db.create_all()
    
    # Initialize default users
    initialize_default_users()
    
    yield db.session
    
    # Clean up after test
    db.session.rollback()
    Card.query.delete()
    User.query.filter(User.username.notin_(['admin', 'user'])).delete()
    db.session.commit()


@pytest.fixture
def storage(db_session):
    """Create DatabaseStorage instance"""
    return DatabaseStorage()


@pytest.fixture
def sample_card_data():
    """Sample card data for testing"""
    return {
        'name': 'Test Card',
        'set_name': 'Test Set',
        'rarity': 'Common',
        'condition': 'Near Mint',
        'price': 1.50,
        'quantity': 10,
        'description': 'A test card for unit testing'
    }


class TestDatabaseModels:
    """Test database model functionality"""
    
    def test_user_creation(self, db_session):
        """Test creating a new user"""
        user = User(
            username='testuser',
            password_hash=generate_password_hash('testpass'),
            role='user'
        )
        db_session.add(user)
        db_session.commit()
        
        # Verify user was created
        saved_user = User.query.filter_by(username='testuser').first()
        assert saved_user is not None
        assert saved_user.username == 'testuser'
        assert saved_user.role == 'user'
        assert saved_user.check_password('testpass')
        assert not saved_user.is_admin()
    
    def test_admin_user_creation(self, db_session):
        """Test creating an admin user"""
        admin = User(
            username='testadmin',
            password_hash=generate_password_hash('adminpass'),
            role='admin'
        )
        db_session.add(admin)
        db_session.commit()
        
        # Verify admin was created
        saved_admin = User.query.filter_by(username='testadmin').first()
        assert saved_admin is not None
        assert saved_admin.is_admin()
    
    def test_card_creation(self, db_session, sample_card_data):
        """Test creating a new card"""
        card = Card(**sample_card_data)
        db_session.add(card)
        db_session.commit()
        
        # Verify card was created
        saved_card = Card.query.filter_by(name='Test Card').first()
        assert saved_card is not None
        assert saved_card.name == 'Test Card'
        assert saved_card.price == 1.50
        assert saved_card.quantity == 10
    
    def test_card_to_dict(self, db_session, sample_card_data):
        """Test card serialization to dictionary"""
        card = Card(**sample_card_data)
        db_session.add(card)
        db_session.commit()
        
        card_dict = card.to_dict()
        assert isinstance(card_dict, dict)
        assert card_dict['name'] == 'Test Card'
        assert card_dict['price'] == 1.50
        assert 'id' in card_dict
        assert 'created_at' in card_dict


class TestDatabaseStorage:
    """Test database storage operations"""
    
    def test_add_card(self, storage, sample_card_data):
        """Test adding a card through storage"""
        card_id = storage.add_card(sample_card_data)
        
        assert card_id is not None
        assert card_id.isdigit()
        
        # Verify card exists
        card = storage.get_card(card_id)
        assert card is not None
        assert card['name'] == 'Test Card'
    
    def test_get_card_existing(self, storage, sample_card_data):
        """Test retrieving an existing card"""
        card_id = storage.add_card(sample_card_data)
        card = storage.get_card(card_id)
        
        assert card is not None
        assert card['name'] == 'Test Card'
        assert card['price'] == 1.50
    
    def test_get_card_nonexistent(self, storage):
        """Test retrieving a non-existent card"""
        card = storage.get_card('999999')
        assert card is None
    
    def test_get_all_cards(self, storage, sample_card_data):
        """Test retrieving all cards"""
        # Add multiple cards
        storage.add_card(sample_card_data)
        
        card_data_2 = sample_card_data.copy()
        card_data_2['name'] = 'Test Card 2'
        storage.add_card(card_data_2)
        
        cards = storage.get_all_cards()
        assert len(cards) >= 2
        card_names = [card['name'] for card in cards]
        assert 'Test Card' in card_names
        assert 'Test Card 2' in card_names
    
    def test_search_cards_by_name(self, storage, sample_card_data):
        """Test searching cards by name"""
        storage.add_card(sample_card_data)
        
        results = storage.search_cards(query='Test')
        assert len(results) >= 1
        assert results[0]['name'] == 'Test Card'
    
    def test_search_cards_by_set(self, storage, sample_card_data):
        """Test searching cards by set"""
        storage.add_card(sample_card_data)
        
        results = storage.search_cards(set_filter='Test Set')
        assert len(results) >= 1
        assert results[0]['set_name'] == 'Test Set'
    
    def test_search_cards_by_rarity(self, storage, sample_card_data):
        """Test searching cards by rarity"""
        storage.add_card(sample_card_data)
        
        results = storage.search_cards(rarity_filter='Common')
        assert len(results) >= 1
        found_common = any(card['rarity'] == 'Common' for card in results)
        assert found_common
    
    def test_search_cards_by_price_range(self, storage, sample_card_data):
        """Test searching cards by price range"""
        storage.add_card(sample_card_data)
        
        results = storage.search_cards(min_price=1.0, max_price=2.0)
        assert len(results) >= 1
        for card in results:
            assert 1.0 <= card['price'] <= 2.0
    
    def test_get_unique_sets(self, storage, sample_card_data):
        """Test getting unique set names"""
        storage.add_card(sample_card_data)
        
        sets = storage.get_unique_sets()
        assert 'Test Set' in sets
    
    def test_get_unique_rarities(self, storage, sample_card_data):
        """Test getting unique rarities"""
        storage.add_card(sample_card_data)
        
        rarities = storage.get_unique_rarities()
        assert 'Common' in rarities
    
    def test_update_card_quantity(self, storage, sample_card_data):
        """Test updating card quantity"""
        card_id = storage.add_card(sample_card_data)
        
        success = storage.update_card_quantity(card_id, 25)
        assert success
        
        card = storage.get_card(card_id)
        assert card['quantity'] == 25
    
    def test_clear_all_cards(self, storage, sample_card_data):
        """Test clearing all cards"""
        storage.add_card(sample_card_data)
        
        # Verify card exists
        cards_before = storage.get_all_cards()
        initial_count = len(cards_before)
        
        storage.clear_all_cards()
        
        # Verify cards are cleared
        cards_after = storage.get_all_cards()
        assert len(cards_after) < initial_count
    
    def test_csv_processing_valid(self, storage):
        """Test processing valid CSV data"""
        csv_content = '''name,set_name,rarity,price,quantity
Test Card,Test Set,Common,1.50,10
Another Card,Another Set,Rare,5.00,3'''
        
        results = storage.process_csv_upload(csv_content)
        
        assert results['success'] == 2
        assert len(results['errors']) == 0
        
        # Verify cards were added
        cards = storage.search_cards(query='Test Card')
        assert len(cards) >= 1
    
    def test_csv_processing_invalid_price(self, storage):
        """Test processing CSV with invalid price"""
        csv_content = '''name,set_name,price
Test Card,Test Set,invalid_price'''
        
        results = storage.process_csv_upload(csv_content)
        
        assert results['success'] == 0
        assert len(results['errors']) >= 1
        assert 'invalid price' in results['errors'][0].lower()
    
    def test_csv_processing_missing_name(self, storage):
        """Test processing CSV with missing card name"""
        csv_content = '''name,set_name
,Test Set'''
        
        results = storage.process_csv_upload(csv_content)
        
        assert results['success'] == 0
        assert len(results['errors']) >= 1
        assert 'missing card name' in results['errors'][0].lower()


class TestDefaultUsers:
    """Test default user initialization"""
    
    def test_default_users_exist(self, db_session):
        """Test that default admin and user accounts exist"""
        admin = User.query.filter_by(username='admin').first()
        user = User.query.filter_by(username='user').first()
        
        assert admin is not None
        assert admin.is_admin()
        
        assert user is not None
        assert not user.is_admin()
    
    def test_admin_can_authenticate(self, db_session):
        """Test admin user authentication"""
        admin = User.query.filter_by(username='admin').first()
        
        # Test with default password
        assert admin.check_password('admin123')
        assert not admin.check_password('wrong_password')
    
    def test_user_can_authenticate(self, db_session):
        """Test regular user authentication"""
        user = User.query.filter_by(username='user').first()
        
        # Test with default password
        assert user.check_password('user123')
        assert not user.check_password('wrong_password')


if __name__ == '__main__':
    pytest.main([__file__, '-v'])