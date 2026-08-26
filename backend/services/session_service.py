"""
Session service for managing chat sessions and conversation history.
Replaces in-memory storage with database-backed sessions.
"""
from typing import Optional, Dict, List, Any
from datetime import datetime
import logging
import uuid

from supabase import create_client, Client
from backend.config import settings

logger = logging.getLogger(__name__)

# Supabase client
supabase: Client = create_client(
    settings.SUPABASE_URL,
    settings.SUPABASE_SERVICE_ROLE_KEY
)


class SessionService:
    """Service for managing chat sessions and conversation history."""
    
    @staticmethod
    async def get_or_create_conversation(
        business_id: str,
        session_id: Optional[str] = None,
        customer_id: Optional[str] = None,
        channel: str = "web"
    ) -> Dict[str, Any]:
        """
        Get existing conversation or create a new one.
        
        Args:
            business_id: Business identifier
            session_id: Optional session identifier (generates new if not provided)
            customer_id: Optional customer identifier
            channel: Communication channel (web, whatsapp, telegram, api)
            
        Returns:
            Conversation dict with id, session_id, etc.
        """
        try:
            # Generate session_id if not provided
            if not session_id:
                session_id = str(uuid.uuid4())
            
            # Try to find existing conversation
            result = supabase.table("conversations")\
                .select("*")\
                .eq("session_id", session_id)\
                .eq("business_id", business_id)\
                .execute()
            
            if result.data:
                conversation = result.data[0]
                logger.debug(f"Found existing conversation: {conversation['id']}")
                return conversation
            
            # Create new conversation
            conversation_data = {
                "business_id": business_id,
                "session_id": session_id,
                "customer_id": customer_id,
                "channel": channel,
                "status": "active",
                "started_at": datetime.utcnow().isoformat()
            }
            
            result = supabase.table("conversations")\
                .insert(conversation_data)\
                .execute()
            
            if result.data:
                conversation = result.data[0]
                logger.info(f"Created new conversation: {conversation['id']} for session {session_id}")
                return conversation
            
            raise Exception("Failed to create conversation")
        
        except Exception as e:
            logger.error(f"Error in get_or_create_conversation: {str(e)}", exc_info=True)
            raise
    
    @staticmethod
    async def get_conversation_history(
        conversation_id: str,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Get message history for a conversation.
        
        Args:
            conversation_id: Conversation identifier
            limit: Maximum number of messages to retrieve
            
        Returns:
            List of message dicts
        """
        try:
            result = supabase.table("messages")\
                .select("*")\
                .eq("conversation_id", conversation_id)\
                .order("created_at", desc=False)\
                .limit(limit)\
                .execute()
            
            return result.data if result.data else []
        
        except Exception as e:
            logger.error(f"Error fetching conversation history: {str(e)}")
            return []
    
    @staticmethod
    async def add_message(
        conversation_id: str,
        role: str,
        content: str,
        intent: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Add a message to a conversation.
        
        Args:
            conversation_id: Conversation identifier
            role: Message role (user, assistant, system)
            content: Message content
            intent: Optional intent classification
            metadata: Optional metadata dict
            
        Returns:
            Created message dict
        """
        try:
            message_data = {
                "conversation_id": conversation_id,
                "role": role,
                "content": content,
                "intent": intent,
                "metadata": metadata or {},
                "created_at": datetime.utcnow().isoformat()
            }
            
            result = supabase.table("messages")\
                .insert(message_data)\
                .execute()
            
            if result.data:
                return result.data[0]
            
            raise Exception("Failed to create message")
        
        except Exception as e:
            logger.error(f"Error adding message: {str(e)}", exc_info=True)
            raise
    
    @staticmethod
    async def close_conversation(conversation_id: str) -> bool:
        """
        Close a conversation.
        
        Args:
            conversation_id: Conversation identifier
            
        Returns:
            True if successful
        """
        try:
            result = supabase.table("conversations")\
                .update({
                    "status": "closed",
                    "ended_at": datetime.utcnow().isoformat()
                })\
                .eq("id", conversation_id)\
                .execute()
            
            if result.data:
                logger.info(f"Closed conversation: {conversation_id}")
                return True
            
            return False
        
        except Exception as e:
            logger.error(f"Error closing conversation: {str(e)}")
            return False
    
    @staticmethod
    async def get_recent_conversations(
        business_id: str,
        limit: int = 50,
        status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get recent conversations for a business.
        
        Args:
            business_id: Business identifier
            limit: Maximum number of conversations to retrieve
            status: Optional status filter
            
        Returns:
            List of conversation dicts
        """
        try:
            query = supabase.table("conversations")\
                .select("*")\
                .eq("business_id", business_id)\
                .order("started_at", desc=True)\
                .limit(limit)
            
            if status:
                query = query.eq("status", status)
            
            result = query.execute()
            return result.data if result.data else []
        
        except Exception as e:
            logger.error(f"Error fetching recent conversations: {str(e)}")
            return []
    
    @staticmethod
    async def get_conversation_stats(
        business_id: str,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Get conversation statistics for a business.
        
        Args:
            business_id: Business identifier
            days: Number of days to look back
            
        Returns:
            Dict with stats
        """
        try:
            # Calculate date threshold
            from datetime import timedelta
            threshold = (datetime.utcnow() - timedelta(days=days)).isoformat()
            
            # Get total conversations
            result = supabase.table("conversations")\
                .select("id", count="exact")\
                .eq("business_id", business_id)\
                .gte("started_at", threshold)\
                .execute()
            
            total_conversations = result.count if hasattr(result, 'count') else len(result.data)
            
            # Get total messages
            # This requires a join, so we'll do it in two queries for simplicity
            conversations = supabase.table("conversations")\
                .select("id")\
                .eq("business_id", business_id)\
                .gte("started_at", threshold)\
                .execute()
            
            conversation_ids = [c['id'] for c in conversations.data] if conversations.data else []
            
            total_messages = 0
            if conversation_ids:
                messages_result = supabase.table("messages")\
                    .select("id", count="exact")\
                    .in_("conversation_id", conversation_ids)\
                    .execute()
                total_messages = messages_result.count if hasattr(messages_result, 'count') else len(messages_result.data)
            
            return {
                "total_conversations": total_conversations,
                "total_messages": total_messages,
                "period_days": days,
                "average_messages_per_conversation": round(total_messages / total_conversations, 2) if total_conversations > 0 else 0
            }
        
        except Exception as e:
            logger.error(f"Error fetching conversation stats: {str(e)}")
            return {
                "total_conversations": 0,
                "total_messages": 0,
                "period_days": days,
                "average_messages_per_conversation": 0
            }
    
    @staticmethod
    async def get_or_create_customer(
        business_id: str,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        name: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get existing customer or create a new one.
        
        Args:
            business_id: Business identifier
            email: Customer email
            phone: Customer phone
            name: Customer name
            
        Returns:
            Customer dict or None
        """
        try:
            # Try to find by email first
            if email:
                result = supabase.table("customers")\
                    .select("*")\
                    .eq("business_id", business_id)\
                    .eq("email", email)\
                    .execute()
                
                if result.data:
                    return result.data[0]
            
            # Try to find by phone
            if phone:
                result = supabase.table("customers")\
                    .select("*")\
                    .eq("business_id", business_id)\
                    .eq("phone", phone)\
                    .execute()
                
                if result.data:
                    return result.data[0]
            
            # Create new customer if we have at least one identifier
            if email or phone or name:
                customer_data = {
                    "business_id": business_id,
                    "email": email,
                    "phone": phone,
                    "name": name,
                    "created_at": datetime.utcnow().isoformat()
                }
                
                result = supabase.table("customers")\
                    .insert(customer_data)\
                    .execute()
                
                if result.data:
                    return result.data[0]
            
            return None
        
        except Exception as e:
            logger.error(f"Error in get_or_create_customer: {str(e)}")
            return None


# Global service instance
session_service = SessionService()