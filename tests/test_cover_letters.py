"""Tests for cover letter generation with user-scoped profiles."""
import pytest
from src.cover_letter_writer import (
    generate_cover_letter,
    generate_batch_cover_letters,
    _truncate,
    MAX_FIELD_LEN,
    MAX_DESCRIPTION_LEN,
    MAX_BATCH_SIZE,
)


class TestProfileScoping:
    """Test that cover letters use provided profile data."""

    def test_generate_cover_letter_uses_provided_profile_name(self):
        """generate_cover_letter uses provided profile name instead of global."""
        job = {"title": "HSE Manager", "company": "Test Co", "location": "Dubai"}
        profile = {"name": "John Doe", "location": "Abu Dhabi", "profile_line": "Experienced HSE professional"}

        letter = generate_cover_letter(job, profile=profile)
        assert "John Doe" in letter
        assert "Abu Dhabi" in letter
        assert "Experienced HSE professional" in letter

    def test_generate_cover_letter_does_not_output_your_name_when_env_missing(self):
        """generate_cover_letter uses 'Candidate' fallback when env is missing."""
        job = {"title": "HSE Manager", "company": "Test Co", "location": "Dubai"}

        letter = generate_cover_letter(job, profile={})
        assert "Candidate" in letter
        assert "Your Name" not in letter
        assert "Your Location" not in letter

    def test_generate_cover_letter_uses_default_profile_when_not_provided(self):
        """generate_cover_letter uses DEFAULT_* when profile fields are missing."""
        job = {"title": "HSE Manager", "company": "Test Co", "location": "Dubai"}
        profile = {"name": "John Doe"}  # Only name provided

        letter = generate_cover_letter(job, profile=profile)
        assert "John Doe" in letter
        assert "relevant experience in environmental compliance" in letter  # Default profile_line

    def test_generate_cover_letter_handles_empty_location(self):
        """generate_cover_letter handles empty location gracefully."""
        job = {"title": "HSE Manager", "company": "Test Co", "location": "Dubai"}
        profile = {"name": "John Doe", "location": ""}

        letter = generate_cover_letter(job, profile=profile)
        assert "John Doe" in letter
        # Should not have an extra blank line for location
        assert "John Doe\n\n" not in letter  # No double newline after name


class TestInputLimits:
    """Test that input fields are truncated to safe limits."""

    def test_generate_cover_letter_truncates_huge_title(self):
        """generate_cover_letter truncates huge title to MAX_FIELD_LEN."""
        job = {
            "title": "A" * 1000,
            "company": "Test Co",
            "location": "Dubai"
        }

        letter = generate_cover_letter(job, profile={"name": "John"})
        assert "A" * (MAX_FIELD_LEN - 1) + "…" in letter
        assert len("A" * 1000) > MAX_FIELD_LEN

    def test_generate_cover_letter_truncates_huge_company(self):
        """generate_cover_letter truncates huge company to MAX_FIELD_LEN."""
        job = {
            "title": "HSE Manager",
            "company": "B" * 1000,
            "location": "Dubai"
        }

        letter = generate_cover_letter(job, profile={"name": "John"})
        assert "B" * (MAX_FIELD_LEN - 1) + "…" in letter

    def test_generate_cover_letter_truncates_huge_location(self):
        """generate_cover_letter truncates huge location to MAX_FIELD_LEN."""
        job = {
            "title": "HSE Manager",
            "company": "Test Co",
            "location": "C" * 1000
        }

        letter = generate_cover_letter(job, profile={"name": "John"})
        assert "C" * (MAX_FIELD_LEN - 1) + "…" in letter

    def test_truncate_function(self):
        """_truncate function works correctly."""
        assert _truncate("short", 10) == "short"
        assert _truncate("exactlyten", 10) == "exactlyten"
        assert _truncate("toolong" * 10, 10) == "toolongto…"
        assert len(_truncate("a" * 100, 50)) == 50


class TestBatchGeneration:
    """Test batch cover letter generation."""

    def test_generate_batch_cover_letters_preserves_duplicate_jobs_with_unique_keys(self):
        """generate_batch_cover_letters preserves duplicate jobs with unique keys."""
        job1 = {"title": "HSE Manager", "company": "Test Co", "link": "https://example.com/job1"}
        job2 = {"title": "HSE Manager", "company": "Test Co", "link": "https://example.com/job1"}  # Same link

        profile = {"name": "John"}
        letters = generate_batch_cover_letters([job1, job2], profile=profile)

        # Should have 2 entries with different keys
        assert len(letters) == 2
        keys = list(letters.keys())
        assert keys[0] != keys[1]
        assert "#2" in keys[1]  # Second entry should have suffix

    def test_generate_batch_cover_letters_rejects_more_than_max_batch_size(self):
        """generate_batch_cover_letters raises ValueError for too many jobs."""
        jobs = [{"title": f"Job {i}", "company": "Co"} for i in range(MAX_BATCH_SIZE + 1)]

        with pytest.raises(ValueError) as exc_info:
            generate_batch_cover_letters(jobs)
        assert f"Cannot generate more than {MAX_BATCH_SIZE}" in str(exc_info.value)

    def test_generate_batch_cover_letters_passes_profile_to_each_letter(self):
        """generate_batch_cover_letters passes profile to each generated letter."""
        jobs = [
            {"title": "Job 1", "company": "Co 1"},
            {"title": "Job 2", "company": "Co 2"}
        ]
        profile = {"name": "Jane Doe"}

        letters = generate_batch_cover_letters(jobs, profile=profile)

        assert len(letters) == 2
        for letter in letters.values():
            assert "Jane Doe" in letter


class TestRoleSpecificKeywords:
    """Test that role-specific ESG/HSE/environment keywords still work."""

    def test_esg_keywords_generate_esg_focused_letter(self):
        """ESG keywords generate ESG-focused cover letter."""
        job = {"title": "ESG Manager", "company": "Test Co", "location": "Dubai"}

        letter = generate_cover_letter(job, profile={"name": "John"})
        assert "ESG, sustainability strategy" in letter

    def test_hse_keywords_generate_hse_focused_letter(self):
        """HSE keywords generate HSE-focused cover letter."""
        job = {"title": "HSE Manager", "company": "Test Co", "location": "Dubai"}

        letter = generate_cover_letter(job, profile={"name": "John"})
        assert "HSE leadership" in letter

    def test_environment_keywords_generate_environment_focused_letter(self):
        """Environment keywords generate environment-focused cover letter."""
        job = {"title": "Environmental Manager", "company": "Test Co", "location": "Dubai"}

        letter = generate_cover_letter(job, profile={"name": "John"})
        assert "environmental compliance" in letter
