"""tests/integration/test_chat_conversation_state.py

Integration tests for chat conversation state management:
- Pending confirmations (user says "yes please" to confirmation prompts)
- Active search continuation (user says "ok" after search with no results)

These tests verify the three-layer defense for conversation state:
1. Intent-first routing (confirmation/negation detection)
2. Conversation state storage (RicoMemoryStore)
3. State-aware response handling (rico_chat_api.py)
"""
import pytest
from pathlib import Path
import tempfile
import shutil

from src.rico_chat_api import RicoChatAPI
from src.rico_memory import RicoMemoryStore
from src.agent.intelligence.intent_classifier import classify_intent
from src.repositories.profile_repo import upsert_profile


@pytest.fixture
def temp_data_dir():
    """Create a temporary data directory for test isolation."""
    original_data_dir = None
    temp_dir = tempfile.mkdtemp()
    
    try:
        from src import rico_memory
        original_data_dir = rico_memory.DATA_DIR
        original_rico_dir = rico_memory.RICO_MEMORY_DIR
        
        # Patch the data directory
        rico_memory.DATA_DIR = Path(temp_dir)
        rico_memory.RICO_MEMORY_DIR = Path(temp_dir) / "rico"
        rico_memory.RICO_MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        
        yield temp_dir
    finally:
        # Restore original
        if original_data_dir:
            rico_memory.DATA_DIR = original_data_dir
            rico_memory.RICO_MEMORY_DIR = original_rico_dir
        shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def chat_api(temp_data_dir):
    """Create a fresh RicoChatAPI instance for each test."""
    return RicoChatAPI()


@pytest.fixture
def test_user_id():
    """Test user ID."""
    return "test_conversation_state_user@example.com"


@pytest.fixture
def test_profile(test_user_id):
    """Create a test profile with CV data."""
    profile = upsert_profile(
        user_id=test_user_id,
        updates={
            "email": test_user_id,
            "skills": ["ISO 9001", "Internal Audit", "Compliance", "Risk Assessment"],
            "years_experience": 8,
            "preferred_cities": ["Dubai", "Abu Dhabi"],
            "target_roles": ["HSE Manager", "Compliance Officer"],
            "cv_status": "parsed",
            "cv_filename": "test_cv.pdf",
        }
    )
    return profile


class TestPendingConfirmation:
    """Test pending confirmation state management."""
    
    def test_set_and_get_pending_confirmation(self, temp_data_dir, test_user_id):
        """Test setting and retrieving pending confirmation state."""
        memory = RicoMemoryStore()
        
        # Set pending confirmation
        memory.set_pending_confirmation(
            user_id=test_user_id,
            action="confirm_search",
            role="Sales Manager",
            reason="known_but_off_profile"
        )
        
        # Retrieve pending confirmation
        pending = memory.get_pending_confirmation(test_user_id)
        
        assert pending is not None
        assert pending["pending_action"] == "confirm_search"
        assert pending["pending_role"] == "Sales Manager"
        assert pending["pending_reason"] == "known_but_off_profile"
        assert "created_at" in pending
        
        # Verify it was cleared after retrieval
        pending_after = memory.get_pending_confirmation(test_user_id)
        assert pending_after is None
    
    def test_confirmation_intent_classification(self):
        """Test that confirmation phrases are classified correctly."""
        confirmation_phrases = ["yes", "yes please", "yeah", "yep", "sure", "okay", "ok"]
        
        for phrase in confirmation_phrases:
            result = classify_intent(phrase)
            assert result.intent == "confirmation"
            assert result.confidence == 1.0
            assert result.source == "exact"
    
    def test_negation_intent_classification(self):
        """Test that negation phrases are classified correctly."""
        negation_phrases = ["no", "no thanks", "nope", "don't", "cancel"]
        
        for phrase in negation_phrases:
            result = classify_intent(phrase)
            assert result.intent == "negation"
            assert result.confidence == 1.0
            assert result.source == "exact"
    
    def test_pending_confirmation_flow(self, chat_api, test_user_id, test_profile):
        """Test full pending confirmation flow:
        1. User searches for off-profile role
        2. System asks for confirmation and sets state
        3. User confirms with "yes please"
        4. System executes the pending search
        """
        # Step 1: User searches for off-profile role
        response1 = chat_api.process_message(
            user_id=test_user_id,
            message="Sales Manager"
        )
        
        # Should ask for confirmation
        assert response1["type"] == "clarification"
        assert "pending_action" in response1
        assert response1["pending_action"] == "confirm_search"
        assert response1["pending_role"] == "Sales Manager"
        assert response1["pending_reason"] == "known_but_off_profile"
        
        # Verify state was set
        pending = chat_api.memory.get_pending_confirmation(test_user_id)
        assert pending is not None
        assert pending["pending_role"] == "Sales Manager"
        
        # Step 2: User confirms
        response2 = chat_api.process_message(
            user_id=test_user_id,
            message="yes please"
        )
        
        # Should execute the search
        assert response2["type"] in ["job_matches", "search_fallback_options"]
        assert "confirmed_action" in response2
        assert response2["confirmed_action"] == "confirm_search"
        assert response2["confirmed_role"] == "Sales Manager"
    
    def test_pending_confirmation_declined(self, chat_api, test_user_id, test_profile):
        """Test declining a pending confirmation."""
        # Set up pending confirmation
        chat_api.memory.set_pending_confirmation(
            user_id=test_user_id,
            action="confirm_search",
            role="Sales Manager",
            reason="known_but_off_profile"
        )
        
        # User declines
        response = chat_api.process_message(
            user_id=test_user_id,
            message="no thanks"
        )
        
        assert response["type"] == "confirmation_declined"
        assert "pending_action" in response
        assert response["pending_action"] == "confirm_search"
        assert "won't proceed" in response["message"].lower()


class TestActiveSearchContinuation:
    """Test active search continuation state management."""
    
    def test_set_and_get_active_search_context(self, temp_data_dir, test_user_id):
        """Test setting and retrieving active search context."""
        memory = RicoMemoryStore()
        
        # Set active search context
        memory.set_active_search_context(
            user_id=test_user_id,
            role="HSE Manager",
            result_count=0,
            fallback_roles=["HSE Officer", "QHSE Coordinator", "Compliance Officer"],
            next_action="broaden_search_or_show_profile_roles"
        )
        
        # Retrieve active search context
        active_search = memory.get_active_search_context(test_user_id)
        
        assert active_search is not None
        assert active_search["active_role"] == "HSE Manager"
        assert active_search["last_result_count"] == 0
        assert len(active_search["fallback_roles"]) == 3
        assert active_search["next_action"] == "broaden_search_or_show_profile_roles"
        assert "created_at" in active_search
    
    def test_clear_active_search_context(self, temp_data_dir, test_user_id):
        """Test clearing active search context."""
        memory = RicoMemoryStore()
        
        # Set active search context
        memory.set_active_search_context(
            user_id=test_user_id,
            role="HSE Manager",
            result_count=0,
            fallback_roles=["HSE Officer"],
            next_action="broaden_search"
        )
        
        # Verify it's set
        active_search = memory.get_active_search_context(test_user_id)
        assert active_search is not None
        
        # Clear it
        memory.clear_active_search_context(test_user_id)
        
        # Verify it's cleared
        active_search_after = memory.get_active_search_context(test_user_id)
        assert active_search_after is None
    
    def test_active_search_continuation_flow(self, chat_api, test_user_id, test_profile):
        """Test active search continuation flow:
        1. User searches for role with no results
        2. System sets active search context with fallback roles
        3. User acknowledges with "ok"
        4. System offers fallback role options
        """
        # Set up active search context (simulating a search with no results)
        chat_api.memory.set_active_search_context(
            user_id=test_user_id,
            role="HSE Manager",
            result_count=0,
            fallback_roles=["HSE Officer", "QHSE Coordinator", "Compliance Officer"],
            next_action="broaden_search_or_show_profile_roles"
        )
        
        # User acknowledges
        response = chat_api.process_message(
            user_id=test_user_id,
            message="ok"
        )
        
        # Should offer fallback options
        assert response["type"] == "search_fallback_options"
        assert response["active_role"] == "HSE Manager"
        assert response["last_result_count"] == 0
        assert len(response["fallback_roles"]) == 3
        assert "options" in response
        assert len(response["options"]) == 3
        assert "HSE Officer" in response["message"]
    
    def test_smalltalk_acknowledges_active_search(self, chat_api, test_user_id, test_profile):
        """Test that 'ok' smalltalk acknowledges active search context."""
        # Set up active search context
        chat_api.memory.set_active_search_context(
            user_id=test_user_id,
            role="HSE Manager",
            result_count=0,
            fallback_roles=["HSE Officer"],
            next_action="broaden_search"
        )
        
        # User says "ok"
        response = chat_api.process_message(
            user_id=test_user_id,
            message="ok"
        )
        
        # Should handle as continuation, not generic smalltalk
        assert response["type"] == "search_fallback_options"
        assert response["active_role"] == "HSE Manager"


class TestConversationStateIntegration:
    """Integration tests for complete conversation state workflows."""
    
    def test_confirmation_then_search_continuation(self, chat_api, test_user_id, test_profile):
        """Test workflow: confirmation → search with no results → continuation."""
        # Step 1: Off-profile role search triggers confirmation
        response1 = chat_api.process_message(
            user_id=test_user_id,
            message="Sales Manager"
        )
        assert response1["type"] == "clarification"
        assert response1["pending_action"] == "confirm_search"
        
        # Step 2: User confirms
        response2 = chat_api.process_message(
            user_id=test_user_id,
            message="yes please"
        )
        # Search executes (may have results or not)
        assert response2["type"] in ["job_matches", "search_fallback_options"]
        
        # If no results, active search context should be set
        if response2.get("active_search_context"):
            # Step 3: User acknowledges
            response3 = chat_api.process_message(
                user_id=test_user_id,
                message="ok"
            )
            assert response3["type"] == "search_fallback_options"
    
    def test_conversation_state_isolation(self, chat_api, test_user_id, test_profile):
        """Test that conversation state is isolated per user."""
        user2_id = "user2@example.com"
        
        # Set pending confirmation for user1
        chat_api.memory.set_pending_confirmation(
            user_id=test_user_id,
            action="confirm_search",
            role="Sales Manager",
            reason="known_but_off_profile"
        )
        
        # Set different state for user2
        chat_api.memory.set_pending_confirmation(
            user_id=user2_id,
            action="confirm_search",
            role="HSE Officer",
            reason="known_but_off_profile"
        )
        
        # Verify isolation
        pending1 = chat_api.memory.get_pending_confirmation(test_user_id)
        pending2 = chat_api.memory.get_pending_confirmation(user2_id)
        
        assert pending1["pending_role"] == "Sales Manager"
        assert pending2["pending_role"] == "HSE Officer"
    
    def test_state_clearing_after_completion(self, chat_api, test_user_id, test_profile):
        """Test that conversation state is cleared after completion."""
        # Set pending confirmation
        chat_api.memory.set_pending_confirmation(
            user_id=test_user_id,
            action="confirm_search",
            role="Sales Manager",
            reason="known_but_off_profile"
        )
        
        # Confirm and execute
        response = chat_api.process_message(
            user_id=test_user_id,
            message="yes"
        )
        
        # Verify state was cleared
        pending_after = chat_api.memory.get_pending_confirmation(test_user_id)
        assert pending_after is None


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_confirmation_without_pending_state(self, chat_api, test_user_id, test_profile):
        """Test confirmation when no pending state exists."""
        response = chat_api.process_message(
            user_id=test_user_id,
            message="yes please"
        )
        # Should fall through to normal smalltalk handling
        assert response["type"] in ["clarification", "smalltalk"]
    
    def test_negation_without_pending_state(self, chat_api, test_user_id, test_profile):
        """Test negation when no pending state exists."""
        response = chat_api.process_message(
            user_id=test_user_id,
            message="no"
        )
        # Should fall through to normal handling
        assert response["type"] in ["clarification", "smalltalk"]
    
    def test_ok_without_active_search_context(self, chat_api, test_user_id, test_profile):
        """Test 'ok' when no active search context exists."""
        response = chat_api.process_message(
            user_id=test_user_id,
            message="ok"
        )
        # Should fall through to normal smalltalk handling
        assert response["type"] in ["clarification", "smalltalk"]
    
    def test_conversation_state_persistence(self, temp_data_dir, test_user_id):
        """Test that conversation state persists across memory store instances."""
        # Set state with first instance
        memory1 = RicoMemoryStore()
        memory1.set_pending_confirmation(
            user_id=test_user_id,
            action="confirm_search",
            role="Test Role",
            reason="test"
        )
        
        # Retrieve with new instance
        memory2 = RicoMemoryStore()
        pending = memory2.get_pending_confirmation(test_user_id)
        
        assert pending is not None
        assert pending["pending_role"] == "Test Role"
