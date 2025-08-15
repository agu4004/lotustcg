"""
Tests for storage.py - InMemoryStorage functionality
"""

import pytest
from storage import InMemoryStorage
from typing import Dict, Any


class TestInMemoryStorage:
    """Test cases for InMemoryStorage class"""
    
    def test_init(self, storage):
        """Test storage initialization"""
        assert isinstance(storage.cards, dict)
        assert storage.next_id == 1
        assert len(storage.cards) == 0
    
    def test_add_card_basic(self, storage, sample_card_data):
        """Test adding a basic card"""
        card_id = storage.add_card(sample_card_data)
        
        assert card_id == "1"
        assert len(storage.cards) == 1
        assert storage.cards[card_id]['name'] == 'Lightning Bolt'
        assert storage.cards[card_id]['price'] == 1.50
        assert storage.next_id == 2
    
    def test_add_card_with_missing_fields(self, storage):
        """Test adding a card with minimal data"""
        card_data = {'name': 'Test Card'}
        card_id = storage.add_card(card_data)
        
        stored_card = storage.cards[card_id]
        assert stored_card['name'] == 'Test Card'
        assert stored_card['set_name'] == 'Unknown'
        assert stored_card['rarity'] == 'Common'
        assert stored_card['condition'] == 'Near Mint'
        assert stored_card['price'] == 0.0
        assert stored_card['quantity'] == 0
        assert stored_card['description'] == ''
    
    def test_add_multiple_cards(self, storage, sample_cards_list):
        """Test adding multiple cards"""
        card_ids = []
        for card_data in sample_cards_list:
            card_id = storage.add_card(card_data)
            card_ids.append(card_id)
        
        assert len(card_ids) == 3
        assert card_ids == ["1", "2", "3"]
        assert len(storage.cards) == 3
        assert storage.next_id == 4
    
    def test_get_card_existing(self, storage, sample_card_data):
        """Test getting an existing card"""
        card_id = storage.add_card(sample_card_data)
        retrieved_card = storage.get_card(card_id)
        
        assert retrieved_card is not None
        assert retrieved_card['name'] == 'Lightning Bolt'
        assert retrieved_card['price'] == 1.50
    
    def test_get_card_nonexistent(self, storage):
        """Test getting a non-existent card"""
        result = storage.get_card("999")
        assert result is None
    
    def test_get_all_cards_empty(self, storage):
        """Test getting all cards when storage is empty"""
        cards = storage.get_all_cards()
        assert cards == []
    
    def test_get_all_cards_with_data(self, storage, sample_cards_list):
        """Test getting all cards with data present"""
        for card_data in sample_cards_list:
            storage.add_card(card_data)
        
        all_cards = storage.get_all_cards()
        assert len(all_cards) == 3
        
        # Check that cards have id field added
        for card in all_cards:
            assert 'id' in card
            assert card['id'] in ['1', '2', '3']
    
    def test_search_cards_no_filters(self, storage, sample_cards_list):
        """Test searching cards without any filters"""
        for card_data in sample_cards_list:
            storage.add_card(card_data)
        
        results = storage.search_cards()
        assert len(results) == 3
    
    def test_search_cards_by_name(self, storage, sample_cards_list):
        """Test searching cards by name"""
        for card_data in sample_cards_list:
            storage.add_card(card_data)
        
        results = storage.search_cards(query="Lightning")
        assert len(results) == 1
        assert results[0]['name'] == 'Lightning Bolt'
        
        results = storage.search_cards(query="bolt")  # Case insensitive
        assert len(results) == 1
        
        results = storage.search_cards(query="Nonexistent")
        assert len(results) == 0
    
    def test_search_cards_by_set(self, storage, sample_cards_list):
        """Test searching cards by set"""
        for card_data in sample_cards_list:
            storage.add_card(card_data)
        
        results = storage.search_cards(set_filter="Alpha")
        assert len(results) == 2
        
        results = storage.search_cards(set_filter="Beta")
        assert len(results) == 1
        assert results[0]['name'] == 'Counterspell'
    
    def test_search_cards_by_rarity(self, storage, sample_cards_list):
        """Test searching cards by rarity"""
        for card_data in sample_cards_list:
            storage.add_card(card_data)
        
        results = storage.search_cards(rarity_filter="Common")
        assert len(results) == 2
        
        results = storage.search_cards(rarity_filter="Majestic")
        assert len(results) == 1
        assert results[0]['name'] == 'Black Lotus'
    
    def test_search_cards_by_price_range(self, storage, sample_cards_list):
        """Test searching cards by price range"""
        for card_data in sample_cards_list:
            storage.add_card(card_data)
        
        # Test min price filter
        results = storage.search_cards(min_price=20.0)
        assert len(results) == 2  # Black Lotus and Counterspell
        
        # Test max price filter
        results = storage.search_cards(max_price=30.0)
        assert len(results) == 2  # Lightning Bolt and Counterspell
        
        # Test price range
        results = storage.search_cards(min_price=1.0, max_price=50.0)
        assert len(results) == 2  # Lightning Bolt and Counterspell
    
    def test_search_cards_combined_filters(self, storage, sample_cards_list):
        """Test searching with multiple filters combined"""
        for card_data in sample_cards_list:
            storage.add_card(card_data)
        
        results = storage.search_cards(
            query="spell",
            rarity_filter="Common",
            max_price=30.0
        )
        assert len(results) == 1
        assert results[0]['name'] == 'Counterspell'
    
    def test_get_unique_sets(self, storage, sample_cards_list):
        """Test getting unique set names"""
        for card_data in sample_cards_list:
            storage.add_card(card_data)
        
        sets = storage.get_unique_sets()
        assert set(sets) == {'Alpha', 'Beta'}
        assert len(sets) == 2
    
    def test_get_unique_sets_empty(self, storage):
        """Test getting unique sets when storage is empty"""
        sets = storage.get_unique_sets()
        assert sets == []
    
    def test_get_unique_rarities(self, storage, sample_cards_list):
        """Test getting unique rarities"""
        for card_data in sample_cards_list:
            storage.add_card(card_data)
        
        rarities = storage.get_unique_rarities()
        assert set(rarities) == {'Common', 'Majestic'}
        assert len(rarities) == 2
    
    def test_get_unique_rarities_empty(self, storage):
        """Test getting unique rarities when storage is empty"""
        rarities = storage.get_unique_rarities()
        assert rarities == []
    
    def test_update_card_quantity_existing(self, storage, sample_card_data):
        """Test updating quantity of existing card"""
        card_id = storage.add_card(sample_card_data)
        
        result = storage.update_card_quantity(card_id, 25)
        assert result is True
        
        updated_card = storage.get_card(card_id)
        assert updated_card['quantity'] == 25
    
    def test_update_card_quantity_nonexistent(self, storage):
        """Test updating quantity of non-existent card"""
        result = storage.update_card_quantity("999", 10)
        assert result is False
    
    def test_clear_all_cards(self, storage, sample_cards_list):
        """Test clearing all cards"""
        for card_data in sample_cards_list:
            storage.add_card(card_data)
        
        assert len(storage.cards) == 3
        
        storage.clear_all_cards()
        
        assert len(storage.cards) == 0
        assert storage.next_id == 1  # Reset to 1
    
    def test_process_csv_upload_valid(self, storage, csv_content):
        """Test processing valid CSV content"""
        results = storage.process_csv_upload(csv_content)
        
        assert results['success'] == 3
        assert len(results['errors']) == 0
        assert len(storage.cards) == 3
        
        # Verify cards were added correctly
        all_cards = storage.get_all_cards()
        card_names = [card['name'] for card in all_cards]
        assert 'Lightning Bolt' in card_names
        assert 'Black Lotus' in card_names
        assert 'Counterspell' in card_names
    
    def test_process_csv_upload_invalid_price(self, storage):
        """Test processing CSV with invalid price"""
        csv_with_invalid_price = '''name,set_name,price
Test Card,Test Set,invalid_price'''
        
        results = storage.process_csv_upload(csv_with_invalid_price)
        
        assert results['success'] == 0
        assert len(results['errors']) == 1
        assert 'invalid price' in results['errors'][0].lower()
    
    def test_process_csv_upload_invalid_quantity(self, storage):
        """Test processing CSV with invalid quantity"""
        csv_with_invalid_quantity = '''name,set_name,quantity
Test Card,Test Set,invalid_quantity'''
        
        results = storage.process_csv_upload(csv_with_invalid_quantity)
        
        assert results['success'] == 0
        assert len(results['errors']) == 1
        assert 'invalid quantity' in results['errors'][0].lower()
    
    def test_process_csv_upload_missing_name(self, storage):
        """Test processing CSV with missing card name"""
        csv_missing_name = '''name,set_name
,Test Set'''
        
        results = storage.process_csv_upload(csv_missing_name)
        
        assert results['success'] == 0
        assert len(results['errors']) == 1
        assert 'missing card name' in results['errors'][0].lower()
    
    def test_process_csv_upload_empty_content(self, storage):
        """Test processing empty CSV content"""
        results = storage.process_csv_upload("")
        
        assert results['success'] == 0
        assert len(results['errors']) == 1
        assert 'no data' in results['errors'][0].lower()
    
    def test_process_csv_upload_header_only(self, storage):
        """Test processing CSV with only headers"""
        csv_header_only = "name,set_name,rarity"
        
        results = storage.process_csv_upload(csv_header_only)
        
        assert results['success'] == 0
        assert len(results['errors']) == 1
        assert 'no data' in results['errors'][0].lower()