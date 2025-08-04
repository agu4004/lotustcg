"""
In-memory storage for TCG cards and application data
"""
import csv
import io
import logging
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

class InMemoryStorage:
    def __init__(self):
        self.cards: Dict[str, Dict[str, Any]] = {}
        self.next_id = 1
        self._initialize_sample_data()
    
    def _initialize_sample_data(self):
        """Initialize with empty data structure"""
        logger.info("Initializing empty card storage")
    
    def add_card(self, card_data: Dict[str, Any]) -> str:
        """Add a card to storage and return its ID"""
        card_id = str(self.next_id)
        self.next_id += 1
        
        # Ensure required fields have defaults
        card_data.setdefault('id', card_id)
        card_data.setdefault('name', 'Unknown Card')
        card_data.setdefault('set_name', 'Unknown')
        card_data.setdefault('rarity', 'Common')
        card_data.setdefault('condition', 'Near Mint')
        card_data.setdefault('price', 0.0)
        card_data.setdefault('quantity', 0)
        card_data.setdefault('description', '')
        
        self.cards[card_id] = card_data
        logger.debug(f"Added card: {card_data['name']} (ID: {card_id})")
        return card_id
    
    def get_card(self, card_id: str) -> Optional[Dict[str, Any]]:
        """Get a card by ID"""
        return self.cards.get(card_id)
    
    def get_all_cards(self) -> List[Dict[str, Any]]:
        """Get all cards"""
        return list(self.cards.values())
    
    def search_cards(self, query: str = "", set_filter: str = "", rarity_filter: str = "", 
                    min_price: Optional[float] = None, max_price: Optional[float] = None) -> List[Dict[str, Any]]:
        """Search cards with filters"""
        results = []
        
        for card in self.cards.values():
            # Text search
            if query and query.lower() not in card['name'].lower():
                continue
            
            # Set filter
            if set_filter and set_filter != card['set_name']:
                continue
            
            # Rarity filter
            if rarity_filter and rarity_filter != card['rarity']:
                continue
            
            # Price range filter
            card_price = float(card.get('price', 0))
            if min_price is not None and card_price < min_price:
                continue
            if max_price is not None and card_price > max_price:
                continue
            
            results.append(card)
        
        return results
    
    def get_unique_sets(self) -> List[str]:
        """Get list of unique set names"""
        sets = set()
        for card in self.cards.values():
            sets.add(card['set_name'])
        return sorted(list(sets))
    
    def get_unique_rarities(self) -> List[str]:
        """Get list of unique rarities"""
        rarities = set()
        for card in self.cards.values():
            rarities.add(card['rarity'])
        return sorted(list(rarities))
    
    def update_card_quantity(self, card_id: str, new_quantity: int) -> bool:
        """Update card quantity"""
        if card_id in self.cards:
            self.cards[card_id]['quantity'] = new_quantity
            logger.debug(f"Updated card {card_id} quantity to {new_quantity}")
            return True
        return False
    
    def process_csv_upload(self, csv_content: str) -> Dict[str, Any]:
        """Process CSV upload and add cards to storage"""
        results = {
            'success': 0,
            'errors': [],
            'total_rows': 0
        }
        
        if not csv_content.strip():
            results['errors'].append("CSV file is empty or contains no data")
            return results
        
        try:
            csv_file = io.StringIO(csv_content)
            reader = csv.DictReader(csv_file)
            
            rows_processed = 0
            for row_num, row in enumerate(reader, start=2):  # Start at 2 for header
                rows_processed += 1
                results['total_rows'] += 1
                
                try:
                    # Validate required fields
                    if not row.get('name', '').strip():
                        results['errors'].append(f"row {row_num}: missing card name")
                        continue
                    
                    # Convert price to float with error handling
                    price_str = row.get('price', '0')
                    try:
                        if price_str.strip():
                            price = float(price_str)
                        else:
                            price = 0.0
                    except (ValueError, TypeError):
                        results['errors'].append(f"row {row_num}: invalid price '{price_str}'")
                        continue
                    
                    # Convert quantity to int with error handling
                    quantity_str = row.get('quantity', '0')
                    try:
                        if quantity_str.strip():
                            quantity = int(quantity_str)
                        else:
                            quantity = 0
                    except (ValueError, TypeError):
                        results['errors'].append(f"row {row_num}: invalid quantity '{quantity_str}'")
                        continue
                    
                    card_data = {
                        'name': row.get('name', '').strip(),
                        'set_name': row.get('set_name', 'Unknown').strip(),
                        'rarity': row.get('rarity', 'Common').strip(),
                        'condition': row.get('condition', 'Near Mint').strip(),
                        'price': price,
                        'quantity': quantity,
                        'description': row.get('description', '').strip()
                    }
                    
                    self.add_card(card_data)
                    results['success'] += 1
                    
                except Exception as e:
                    results['errors'].append(f"row {row_num}: {str(e)}")
                    logger.error(f"Error processing row {row_num}: {e}")
            
            # Check if we have no data rows (only headers)
            if rows_processed == 0:
                results['errors'].append("CSV file contains no data rows")
        
        except Exception as e:
            results['errors'].append(f"CSV parsing error: {str(e)}")
            logger.error(f"CSV parsing error: {e}")
        
        return results
    
    def clear_all_cards(self):
        """Clear all cards from storage"""
        self.cards.clear()
        self.next_id = 1
        logger.info("Cleared all cards from storage")

# Global storage instance
storage = InMemoryStorage()
