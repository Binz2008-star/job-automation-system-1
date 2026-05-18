from __future__ import annotations

from unittest.mock import patch

from src.services import chat_service


def test_open_ended_question_routes_to_ai_boundary() -> None:
    with patch("src.repositories.profile_repo.get_profile", return_value={"cv_status": "parsed"}), \
         patch(
             "src.rico_chat_api.RicoChatAPI.answer_conversationally",
             return_value={"message": "AI", "type": "openai_response", "response_source": "openai"},
         ) as ai_path, \
         patch(
             "src.rico_chat_api.RicoChatAPI.process_message",
             return_value={"message": "legacy", "type": "legacy"},
         ) as legacy_path:
        result = chat_service.send_message(
            user_id="test_user_phase1@example.com",
            message="how can you help me",
        )

    ai_path.assert_called_once()
    legacy_path.assert_not_called()
    assert result["intent"] == "conversational"


def test_bare_role_routes_to_legacy_boundary() -> None:
    with patch("src.repositories.profile_repo.get_profile", return_value={"cv_status": "parsed"}), \
         patch(
             "src.rico_chat_api.RicoChatAPI.answer_conversationally",
             return_value={"message": "AI", "type": "openai_response"},
         ) as ai_path, \
         patch(
             "src.rico_chat_api.RicoChatAPI.process_message",
             return_value={"message": "legacy", "type": "role_candidate"},
         ) as legacy_path:
        chat_service.send_message(
            user_id="test_user_phase1@example.com",
            message="HSE Manager",
        )

    legacy_path.assert_called_once()
    ai_path.assert_not_called()


def test_explicit_role_search_routes_to_legacy_boundary() -> None:
    with patch("src.repositories.profile_repo.get_profile", return_value={"cv_status": "parsed"}), \
         patch(
             "src.rico_chat_api.RicoChatAPI.answer_conversationally",
             return_value={"message": "AI", "type": "openai_response"},
         ) as ai_path, \
         patch(
             "src.rico_chat_api.RicoChatAPI.process_message",
             return_value={"message": "legacy", "type": "explicit_search"},
         ) as legacy_path:
        chat_service.send_message(
            user_id="test_user_phase1@example.com",
            message="find HSE Manager jobs",
        )

    legacy_path.assert_called_once()
    ai_path.assert_not_called()
