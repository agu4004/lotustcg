"""
Tests for routes.py - Flask route handlers and application endpoints
"""

import pytest
import json
from unittest.mock import patch, Mock
from flask import session
from io import BytesIO


class TestPublicRoutes:
    """Test cases for public routes accessible to all users"""
    
    def test_index_route_empty_storage(self, client):
        """Test index route with no cards in storage"""
        with patch('routes.storage.get_all_cards', return_value=[]):
            response = client.get('/')
            
            assert response.status_code == 200
            assert b'No Cards Available' in response.data
            assert b'Lotus TCG' in response.data
    
    def test_index_route_with_cards(self, client, sample_cards_list):
        """Test index route with cards in storage"""
        with patch('routes.storage.get_all_cards', return_value=sample_cards_list):
            response = client.get('/')
            
            assert response.status_code == 200
            assert b'Lightning Bolt' in response.data
            assert b'Black Lotus' in response.data
    
    def test_catalog_route_empty(self, client):
        """Test catalog route with empty storage"""
        with patch('routes.storage.search_cards', return_value=[]):
            with patch('routes.storage.get_unique_sets', return_value=[]):
                with patch('routes.storage.get_unique_rarities', return_value=[]):
                    response = client.get('/catalog')
                    
                    assert response.status_code == 200
                    assert b'No cards found' in response.data
    
    def test_catalog_route_with_cards(self, client, sample_cards_list):
        """Test catalog route with cards"""
        with patch('routes.storage.search_cards', return_value=sample_cards_list):
            with patch('routes.storage.get_unique_sets', return_value=['Alpha', 'Beta']):
                with patch('routes.storage.get_unique_rarities', return_value=['Common', 'Rare']):
                    response = client.get('/catalog')
                    
                    assert response.status_code == 200
                    assert b'Lightning Bolt' in response.data
                    assert b'$1.50' in response.data
    
    def test_catalog_route_with_search(self, client, sample_cards_list):
        """Test catalog route with search parameters"""
        filtered_cards = [sample_cards_list[0]]  # Only Lightning Bolt
        
        with patch('routes.storage.search_cards', return_value=filtered_cards) as mock_search:
            with patch('routes.storage.get_unique_sets', return_value=['Alpha']):
                with patch('routes.storage.get_unique_rarities', return_value=['Common']):
                    response = client.get('/catalog?search=Lightning&set=Alpha&rarity=Common')
                    
                    assert response.status_code == 200
                    mock_search.assert_called_once_with(
                        query='Lightning',
                        set_filter='Alpha',
                        rarity_filter='Common',
                        min_price=None,
                        max_price=None
                    )
    
    def test_card_detail_existing(self, client, sample_card_data):
        """Test card detail route for existing card"""
        card = {**sample_card_data, 'id': '1'}
        
        with patch('routes.storage.get_card', return_value=card):
            response = client.get('/card/1')
            
            assert response.status_code == 200
            assert b'Lightning Bolt' in response.data
            assert b'$1.50' in response.data
    
    def test_card_detail_nonexistent(self, client):
        """Test card detail route for non-existent card"""
        with patch('routes.storage.get_card', return_value=None):
            response = client.get('/card/999')
            
            assert response.status_code == 404
    
    def test_view_cart_empty(self, client):
        """Test cart view with empty cart"""
        response = client.get('/cart')
        
        assert response.status_code == 200
        assert b'Your cart is empty' in response.data
    
    def test_view_cart_with_items(self, client, sample_cards_list):
        """Test cart view with items"""
        with client.session_transaction() as sess:
            sess['cart'] = {'1': 2, '2': 1}
        
        mock_cards = {card['name']: {**card, 'id': str(i+1)} for i, card in enumerate(sample_cards_list)}
        
        with patch('routes.storage.get_card') as mock_get_card:
            mock_get_card.side_effect = lambda card_id: next(
                (card for card in mock_cards.values() if card['id'] == card_id), None
            )
            
            response = client.get('/cart')
            
            assert response.status_code == 200
            assert b'Lightning Bolt' in response.data
            assert b'Quantity: 2' in response.data


class TestCartRoutes:
    """Test cases for shopping cart functionality"""
    
    def test_add_to_cart_existing_card(self, client, sample_card_data):
        """Test adding existing card to cart"""
        card = {**sample_card_data, 'id': '1'}
        
        with patch('routes.storage.get_card', return_value=card):
            response = client.post('/cart/add/1', data={'quantity': '2'})
            
            assert response.status_code == 302  # Redirect
            
            with client.session_transaction() as sess:
                assert sess['cart']['1'] == 2
    
    def test_add_to_cart_nonexistent_card(self, client):
        """Test adding non-existent card to cart"""
        with patch('routes.storage.get_card', return_value=None):
            response = client.post('/cart/add/999', data={'quantity': '1'})
            
            assert response.status_code == 404
    
    def test_add_to_cart_invalid_quantity(self, client, sample_card_data):
        """Test adding card with invalid quantity"""
        card = {**sample_card_data, 'id': '1'}
        
        with patch('routes.storage.get_card', return_value=card):
            response = client.post('/cart/add/1', data={'quantity': 'invalid'})
            
            assert response.status_code == 302  # Should redirect with error
    
    def test_update_cart_existing_item(self, client, sample_card_data):
        """Test updating cart item quantity"""
        card = {**sample_card_data, 'id': '1'}
        
        with client.session_transaction() as sess:
            sess['cart'] = {'1': 2}
        
        with patch('routes.storage.get_card', return_value=card):
            response = client.post('/cart/update/1', data={'quantity': '5'})
            
            assert response.status_code == 302
            
            with client.session_transaction() as sess:
                assert sess['cart']['1'] == 5
    
    def test_update_cart_remove_item(self, client, sample_card_data):
        """Test removing item from cart by setting quantity to 0"""
        card = {**sample_card_data, 'id': '1'}
        
        with client.session_transaction() as sess:
            sess['cart'] = {'1': 2, '2': 1}
        
        with patch('routes.storage.get_card', return_value=card):
            response = client.post('/cart/update/1', data={'quantity': '0'})
            
            assert response.status_code == 302
            
            with client.session_transaction() as sess:
                assert '1' not in sess['cart']
                assert '2' in sess['cart']
    
    def test_clear_cart(self, client):
        """Test clearing entire cart"""
        with client.session_transaction() as sess:
            sess['cart'] = {'1': 2, '2': 1, '3': 3}
        
        response = client.post('/cart/clear')
        
        assert response.status_code == 302
        
        with client.session_transaction() as sess:
            assert sess['cart'] == {}


class TestAuthRoutes:
    """Test cases for authentication routes"""
    
    def test_login_get(self, client):
        """Test GET request to login page"""
        response = client.get('/login')
        
        assert response.status_code == 200
        assert b'Login' in response.data
        assert b'Username' in response.data
        assert b'Password' in response.data
    
    def test_login_post_valid_credentials(self, client, admin_user):
        """Test POST to login with valid credentials"""
        with patch('routes.user_manager.authenticate_user', return_value=admin_user):
            response = client.post('/login', data={
                'username': 'admin',
                'password': 'admin123'
            })
            
            assert response.status_code == 302  # Redirect after successful login
    
    def test_login_post_invalid_credentials(self, client):
        """Test POST to login with invalid credentials"""
        with patch('routes.user_manager.authenticate_user', return_value=None):
            with patch('routes.flash') as mock_flash:
                response = client.post('/login', data={
                    'username': 'invalid',
                    'password': 'wrong'
                })
                
                assert response.status_code == 200  # Stay on login page
                mock_flash.assert_called_with('Invalid username or password', 'error')
    
    def test_login_post_empty_credentials(self, client):
        """Test POST to login with empty credentials"""
        with patch('routes.flash') as mock_flash:
            response = client.post('/login', data={
                'username': '',
                'password': ''
            })
            
            assert response.status_code == 200
            mock_flash.assert_called_with('Please enter both username and password', 'error')
    
    def test_logout_authenticated_user(self, authenticated_client):
        """Test logout for authenticated user"""
        response = authenticated_client.get('/logout')
        
        assert response.status_code == 302  # Redirect to home
    
    def test_logout_unauthenticated_user(self, client):
        """Test logout for unauthenticated user"""
        # Should redirect to login due to @login_required
        response = client.get('/logout')
        
        assert response.status_code == 302


class TestAdminRoutes:
    """Test cases for admin-only routes"""
    
    def test_admin_dashboard_as_admin(self, authenticated_client):
        """Test admin dashboard access as admin user"""
        with patch('routes.storage.get_all_cards', return_value=[]):
            with patch('routes.user_manager.get_all_users', return_value={}):
                response = authenticated_client.get('/admin')
                
                assert response.status_code == 200
                assert b'Admin Dashboard' in response.data
    
    def test_admin_dashboard_as_guest(self, client):
        """Test admin dashboard access as guest"""
        response = client.get('/admin')
        
        assert response.status_code == 302  # Redirect to login
    
    def test_admin_dashboard_as_regular_user(self, user_authenticated_client):
        """Test admin dashboard access as regular user"""
        response = user_authenticated_client.get('/admin')
        
        assert response.status_code == 403  # Forbidden
    
    def test_upload_csv_valid_file(self, authenticated_client, csv_content):
        """Test CSV upload with valid file"""
        csv_file = BytesIO(csv_content.encode('utf-8'))
        csv_file.name = 'test_cards.csv'
        
        with patch('routes.storage.process_csv_upload') as mock_process:
            mock_process.return_value = {'success': 3, 'errors': []}
            
            response = authenticated_client.post('/admin/upload_csv', data={
                'csv_file': (csv_file, 'test_cards.csv')
            })
            
            assert response.status_code == 302  # Redirect back to admin
            mock_process.assert_called_once()
    
    def test_upload_csv_no_file(self, authenticated_client):
        """Test CSV upload with no file"""
        with patch('routes.flash') as mock_flash:
            response = authenticated_client.post('/admin/upload_csv', data={})
            
            assert response.status_code == 302
            mock_flash.assert_called_with('No file selected', 'error')
    
    def test_upload_csv_invalid_file_type(self, authenticated_client):
        """Test CSV upload with invalid file type"""
        txt_file = BytesIO(b'not a csv')
        
        with patch('routes.flash') as mock_flash:
            response = authenticated_client.post('/admin/upload_csv', data={
                'csv_file': (txt_file, 'test.txt')
            })
            
            assert response.status_code == 302
            mock_flash.assert_called_with('Please upload a CSV file', 'error')
    
    def test_clear_cards_as_admin(self, authenticated_client):
        """Test clearing all cards as admin"""
        with patch('routes.storage.clear_all_cards') as mock_clear:
            with patch('routes.flash') as mock_flash:
                response = authenticated_client.post('/admin/clear_cards')
                
                assert response.status_code == 302
                mock_clear.assert_called_once()
                mock_flash.assert_called_with('All cards cleared', 'info')
    
    def test_download_sample_csv(self, authenticated_client):
        """Test downloading sample CSV file"""
        response = authenticated_client.get('/admin/sample_csv')
        
        assert response.status_code == 200
        assert response.headers['Content-Type'] == 'text/csv; charset=utf-8'
        assert b'Lightning Bolt' in response.data


class TestAPIRoutes:
    """Test cases for API endpoints"""
    
    def test_create_card_api_valid_data(self, authenticated_client, sample_card_data):
        """Test creating card via API with valid data"""
        with patch('routes.storage.add_card', return_value='1') as mock_add:
            with patch('routes.storage.get_card', return_value={**sample_card_data, 'id': '1'}):
                response = authenticated_client.post('/api/cards', 
                    json=sample_card_data,
                    content_type='application/json'
                )
                
                assert response.status_code == 201
                data = json.loads(response.data)
                assert data['success'] is True
                assert data['id'] == '1'
                mock_add.assert_called_once_with(sample_card_data)
    
    def test_create_card_api_missing_name(self, authenticated_client):
        """Test creating card via API without name"""
        response = authenticated_client.post('/api/cards', 
            json={'price': 10.0},
            content_type='application/json'
        )
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data
        assert 'required' in data['error'].lower()
    
    def test_update_card_api_existing(self, authenticated_client, sample_card_data):
        """Test updating existing card via API"""
        updated_data = {**sample_card_data, 'price': 2.00}
        
        with patch('routes.storage.get_card', return_value={**sample_card_data, 'id': '1'}):
            with patch('routes.storage.cards', {'1': updated_data}):
                response = authenticated_client.put('/api/cards/1',
                    json={'price': 2.00},
                    content_type='application/json'
                )
                
                assert response.status_code in [200, 204]
    
    def test_update_card_api_nonexistent(self, authenticated_client):
        """Test updating non-existent card via API"""
        with patch('routes.storage.get_card', return_value=None):
            response = authenticated_client.put('/api/cards/999',
                json={'price': 2.00},
                content_type='application/json'
            )
            
            assert response.status_code == 404
    
    def test_delete_card_api_existing(self, authenticated_client):
        """Test deleting existing card via API"""
        with patch('routes.storage.get_card', return_value={'id': '1', 'name': 'Test'}):
            with patch('routes.storage.cards', {'1': {'name': 'Test'}}) as mock_cards:
                response = authenticated_client.delete('/api/cards/1')
                
                assert response.status_code in [200, 204]
    
    def test_delete_card_api_nonexistent(self, authenticated_client):
        """Test deleting non-existent card via API"""
        with patch('routes.storage.get_card', return_value=None):
            response = authenticated_client.delete('/api/cards/999')
            
            assert response.status_code == 404
    
    def test_api_routes_require_admin(self, user_authenticated_client, sample_card_data):
        """Test that API routes require admin access"""
        # Test create
        response = user_authenticated_client.post('/api/cards',
            json=sample_card_data,
            content_type='application/json'
        )
        assert response.status_code == 403
        
        # Test update
        response = user_authenticated_client.put('/api/cards/1',
            json={'price': 2.00},
            content_type='application/json'
        )
        assert response.status_code == 403
        
        # Test delete
        response = user_authenticated_client.delete('/api/cards/1')
        assert response.status_code == 403


class TestErrorHandlers:
    """Test cases for error handling"""
    
    def test_404_error_handler(self, client):
        """Test 404 error handling"""
        response = client.get('/nonexistent-route')
        
        assert response.status_code == 404
        assert b'Page Not Found' in response.data or b'404' in response.data
    
    def test_500_error_handler(self, client):
        """Test 500 error handling"""
        # This is harder to test without actually causing a server error
        # Would need to create a route that intentionally raises an exception
        pass


class TestUtilityFunctions:
    """Test cases for utility functions"""
    
    def test_load_user_existing(self, app_instance, admin_user):
        """Test load_user function with existing user"""
        with patch('routes.user_manager.get_user', return_value=admin_user):
            user = app.load_user('admin')
            
            assert user is not None
            assert user.username == 'admin'
    
    def test_load_user_nonexistent(self, app_instance):
        """Test load_user function with non-existent user"""
        with patch('routes.user_manager.get_user', return_value=None):
            user = app.load_user('nonexistent')
            
            assert user is None