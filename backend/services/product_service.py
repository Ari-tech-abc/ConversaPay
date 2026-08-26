"""
Product service for intelligent product search and matching.
Provides semantic search and simple keyword matching for products.
"""
from typing import List, Dict, Any, Optional
import logging
import re
from supabase import create_client, Client

from backend.config import settings

logger = logging.getLogger(__name__)


class ProductService:
    """Service for product search and matching operations."""
    
    def __init__(self):
        """Initialize Supabase client."""
        self.client: Client = create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_SERVICE_ROLE_KEY
        )
    
    def search_products(
        self,
        business_id: str,
        query: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Search products for a business using semantic and keyword matching.
        
        Args:
            business_id: Business UUID
            query: Search query (product name, description, or keywords)
            limit: Maximum number of results to return
            
        Returns:
            List of matching products
        """
        try:
            # Get all active products for the business
            result = self.client.table("products")\
                .select("*")\
                .eq("business_id", business_id)\
                .eq("is_active", True)\
                .execute()
            
            if not result.data:
                return []
            
            products = result.data
            
            # Score each product based on query relevance
            scored_products = []
            query_lower = query.lower()
            
            for product in products:
                score = 0
                
                # Exact name match (highest score)
                if query_lower == product['name'].lower():
                    score += 100
                # Name contains query
                elif query_lower in product['name'].lower():
                    score += 50
                
                # Item key match
                if query_lower == product['item_key'].lower():
                    score += 80
                elif query_lower in product['item_key'].lower():
                    score += 40
                
                # Description match
                if product.get('description'):
                    desc_lower = product['description'].lower()
                    if query_lower in desc_lower:
                        score += 30
                
                # Word-based matching in name
                query_words = set(query_lower.split())
                name_words = set(product['name'].lower().split())
                word_matches = query_words & name_words
                if word_matches:
                    score += len(word_matches) * 15
                
                # Add product with score
                product['search_score'] = score
                scored_products.append(product)
            
            # Sort by score (descending) and limit results
            scored_products.sort(key=lambda x: x['search_score'], reverse=True)
            
            # Filter out products with score 0 (no match)
            matched_products = [p for p in scored_products if p['search_score'] > 0]
            
            return matched_products[:limit]
        
        except Exception as e:
            logger.error(f"Error searching products: {str(e)}", exc_info=True)
            return []
    
    def get_product_by_item_key(
        self,
        business_id: str,
        item_key: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get a specific product by item key.
        
        Args:
            business_id: Business UUID
            item_key: Product item key
            
        Returns:
            Product dict or None if not found
        """
        try:
            result = self.client.table("products")\
                .select("*")\
                .eq("business_id", business_id)\
                .eq("item_key", item_key.upper())\
                .eq("is_active", True)\
                .execute()
            
            if result.data:
                return result.data[0]
            return None
        
        except Exception as e:
            logger.error(f"Error getting product by item key: {str(e)}", exc_info=True)
            return None
    
    def get_product_by_id(
        self,
        business_id: str,
        product_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get a specific product by ID.
        
        Args:
            business_id: Business UUID
            product_id: Product UUID
            
        Returns:
            Product dict or None if not found
        """
        try:
            result = self.client.table("products")\
                .select("*")\
                .eq("business_id", business_id)\
                .eq("id", product_id)\
                .eq("is_active", True)\
                .execute()
            
            if result.data:
                return result.data[0]
            return None
        
        except Exception as e:
            logger.error(f"Error getting product by ID: {str(e)}", exc_info=True)
            return None
    
    def get_all_products(
        self,
        business_id: str,
        active_only: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Get all products for a business.
        
        Args:
            business_id: Business UUID
            active_only: Whether to return only active products
            
        Returns:
            List of products
        """
        try:
            query = self.client.table("products")\
                .select("*")\
                .eq("business_id", business_id)
            
            if active_only:
                query = query.eq("is_active", True)
            
            result = query.execute()
            return result.data if result.data else []
        
        except Exception as e:
            logger.error(f"Error getting all products: {str(e)}", exc_info=True)
            return []
    
    def format_product_for_ai(
        self,
        product: Dict[str, Any]
    ) -> str:
        """
        Format product information for AI consumption.
        
        Args:
            product: Product dict
            
        Returns:
            Formatted string
        """
        lines = [
            f"קוד: {product['item_key']}",
            f"שם: {product['name']}",
            f"מחיר: ₪{product['price']}",
        ]
        
        if product.get('description'):
            lines.append(f"תיאור: {product['description']}")
        
        if product.get('image_url'):
            lines.append(f"תמונה: {product['image_url']}")
        
        return " | ".join(lines)


# Global service instance
product_service = ProductService()
