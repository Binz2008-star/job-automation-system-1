"""
LinkedIn Data Integration Module
Parses LinkedIn export data and integrates with job automation system
"""

import csv
import os
from typing import List, Dict, Set, Optional, Tuple
from dataclasses import dataclass, field
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class Profile:
    """User profile data"""
    first_name: str
    last_name: str
    headline: str
    summary: str
    industry: str
    location: str
    websites: List[str] = field(default_factory=list)


@dataclass
class Position:
    """Work experience"""
    company_name: str
    title: str
    description: str
    location: str
    started_on: str
    finished_on: Optional[str] = None


@dataclass
class Skill:
    """Professional skill"""
    name: str


@dataclass
class Connection:
    """LinkedIn connection"""
    first_name: str
    last_name: str
    url: str
    email: Optional[str]
    company: str
    position: str
    connected_on: str


@dataclass
class CompanyFollow:
    """Company the user follows"""
    organization: str
    followed_on: str


@dataclass
class JobApplication:
    """Past job application"""
    application_date: str
    contact_email: str
    contact_phone: str
    company_name: str
    job_title: str
    job_url: str
    resume_name: str
    question_and_answers: str


@dataclass
class SavedJob:
    """Saved job"""
    saved_date: str
    job_url: str
    job_title: str
    company_name: str


class LinkedInDataLoader:
    """Load and parse LinkedIn export data"""

    def __init__(self, export_path: str = "linkedin_export_clean"):
        self.export_path = Path(export_path)
        self.profile: Optional[Profile] = None
        self.positions: List[Position] = []
        self.skills: List[Skill] = []
        self.connections: List[Connection] = []
        self.company_follows: List[CompanyFollow] = []
        self.job_applications: List[JobApplication] = []
        self.saved_jobs: List[SavedJob] = []
        self.saved_answers: Dict[str, str] = {}

    def load_all(self) -> None:
        """Load all LinkedIn data"""
        logger.info("Loading LinkedIn data...")
        self._load_profile()
        self._load_positions()
        self._load_skills()
        self._load_connections()
        self._load_company_follows()
        self._load_job_applications()
        self._load_saved_jobs()
        self._load_saved_answers()
        logger.info(f"Loaded {len(self.skills)} skills, {len(self.company_follows)} companies, "
                   f"{len(self.connections)} connections, {len(self.job_applications)} applications")

    def _load_profile(self) -> None:
        """Load profile data"""
        profile_path = self.export_path / "Profile.csv"
        if not profile_path.exists():
            logger.warning(f"Profile.csv not found at {profile_path}")
            return

        try:
            with open(profile_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    websites = []
                    if row.get('Websites'):
                        websites = [w.strip() for w in row['Websites'].split(',') if w.strip()]

                    self.profile = Profile(
                        first_name=row.get('First Name', ''),
                        last_name=row.get('Last Name', ''),
                        headline=row.get('Headline', ''),
                        summary=row.get('Summary', ''),
                        industry=row.get('Industry', ''),
                        location=row.get('Geo Location', ''),
                        websites=websites
                    )
                    break
            logger.info("Profile loaded")
        except Exception as e:
            logger.error(f"Error loading profile: {e}")

    def _load_positions(self) -> None:
        """Load work experience"""
        positions_path = self.export_path / "Positions.csv"
        if not positions_path.exists():
            logger.warning(f"Positions.csv not found")
            return

        try:
            with open(positions_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if not row.get('Company Name'):
                        continue

                    position = Position(
                        company_name=row.get('Company Name', ''),
                        title=row.get('Title', ''),
                        description=row.get('Description', ''),
                        location=row.get('Location', ''),
                        started_on=row.get('Started On', ''),
                        finished_on=row.get('Finished On') if row.get('Finished On') else None
                    )
                    self.positions.append(position)
            logger.info(f"Loaded {len(self.positions)} positions")
        except Exception as e:
            logger.error(f"Error loading positions: {e}")

    def _load_skills(self) -> None:
        """Load skills"""
        skills_path = self.export_path / "Skills.csv"
        if not skills_path.exists():
            logger.warning(f"Skills.csv not found")
            return

        try:
            with open(skills_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    skill_name = row.get('Name', '').strip()
                    if skill_name:
                        self.skills.append(Skill(name=skill_name))
            logger.info(f"Loaded {len(self.skills)} skills")
        except Exception as e:
            logger.error(f"Error loading skills: {e}")

    def _load_connections(self) -> None:
        """Load connections"""
        connections_path = self.export_path / "Connections.csv"
        if not connections_path.exists():
            logger.warning(f"Connections.csv not found")
            return

        try:
            with open(connections_path, 'r', encoding='utf-8') as f:
                # Skip the first 3 lines (notes) before the header
                for _ in range(3):
                    next(f)
                reader = csv.DictReader(f)
                for row in reader:
                    if not row.get('First Name'):
                        continue

                    connection = Connection(
                        first_name=row.get('First Name', ''),
                        last_name=row.get('Last Name', ''),
                        url=row.get('URL', ''),
                        email=row.get('Email Address') if row.get('Email Address') else None,
                        company=row.get('Company', ''),
                        position=row.get('Position', ''),
                        connected_on=row.get('Connected On', '')
                    )
                    self.connections.append(connection)
            logger.info(f"Loaded {len(self.connections)} connections")
        except Exception as e:
            logger.error(f"Error loading connections: {e}")

    def _load_company_follows(self) -> None:
        """Load company follows"""
        follows_path = self.export_path / "Company Follows.csv"
        if not follows_path.exists():
            logger.warning(f"Company Follows.csv not found")
            return

        try:
            with open(follows_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if not row.get('Organization'):
                        continue

                    follow = CompanyFollow(
                        organization=row.get('Organization', ''),
                        followed_on=row.get('Followed On', '')
                    )
                    self.company_follows.append(follow)
            logger.info(f"Loaded {len(self.company_follows)} company follows")
        except Exception as e:
            logger.error(f"Error loading company follows: {e}")

    def _load_job_applications(self) -> None:
        """Load job applications"""
        jobs_path = self.export_path / "Jobs" / "Job Applications.csv"
        if not jobs_path.exists():
            logger.warning(f"Job Applications.csv not found")
            return

        try:
            with open(jobs_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    application = JobApplication(
                        application_date=row.get('Application Date', ''),
                        contact_email=row.get('Contact Email', ''),
                        contact_phone=row.get('Contact Phone Number', ''),
                        company_name=row.get('Company Name', ''),
                        job_title=row.get('Job Title', ''),
                        job_url=row.get('Job Url', ''),
                        resume_name=row.get('Resume Name', ''),
                        question_and_answers=row.get('Question And Answers', '')
                    )
                    self.job_applications.append(application)
            logger.info(f"Loaded {len(self.job_applications)} job applications")
        except Exception as e:
            logger.error(f"Error loading job applications: {e}")

    def _load_saved_jobs(self) -> None:
        """Load saved jobs"""
        saved_path = self.export_path / "Jobs" / "Saved Jobs.csv"
        if not saved_path.exists():
            logger.warning(f"Saved Jobs.csv not found")
            return

        try:
            with open(saved_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if not row.get('Job Title'):
                        continue

                    saved_job = SavedJob(
                        saved_date=row.get('Saved Date', ''),
                        job_url=row.get('Job Url', ''),
                        job_title=row.get('Job Title', ''),
                        company_name=row.get('Company Name', '')
                    )
                    self.saved_jobs.append(saved_job)
            logger.info(f"Loaded {len(self.saved_jobs)} saved jobs")
        except Exception as e:
            logger.error(f"Error loading saved jobs: {e}")

    def _load_saved_answers(self) -> None:
        """Load saved screening question answers"""
        answers_path = self.export_path / "Jobs" / "Job Applicant Saved Answers.csv"
        if not answers_path.exists():
            logger.warning(f"Job Applicant Saved Answers.csv not found")
            return

        try:
            with open(answers_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    question = row.get('Question', '')
                    answer = row.get('Answer', '')
                    if question and answer:
                        self.saved_answers[question] = answer
            logger.info(f"Loaded {len(self.saved_answers)} saved answers")
        except Exception as e:
            logger.error(f"Error loading saved answers: {e}")


class SkillMatcher:
    """Match skills to job requirements"""

    def __init__(self, skills: List[Skill]):
        self.skill_names = {skill.name.lower() for skill in skills}
        self.skills = skills

    def calculate_match_score(self, job_description: str, required_skills: List[str]) -> float:
        """Calculate how well job matches user's skills (0-1)"""
        if not required_skills and not job_description:
            return 0.0

        matched_skills = set()
        job_text = job_description.lower()

        # Check against explicitly required skills
        for req_skill in required_skills:
            req_lower = req_skill.lower()
            if any(req_lower in skill_name or skill_name in req_lower
                   for skill_name in self.skill_names):
                matched_skills.add(req_skill)

        # Extract skills from job description
        for skill in self.skills:
            skill_lower = skill.name.lower()
            if skill_lower in job_text:
                matched_skills.add(skill.name)

        if not required_skills:
            # If no explicit requirements, match against description
            return len(matched_skills) / max(len(self.skills), 1) * 0.5

        return len(matched_skills) / max(len(required_skills), 1)

    def get_matching_skills(self, job_description: str) -> List[str]:
        """Get list of user's skills that match job description"""
        job_text = job_description.lower()
        matching = []

        for skill in self.skills:
            if skill.name.lower() in job_text:
                matching.append(skill.name)

        return matching

    def get_missing_skills(self, required_skills: List[str]) -> List[str]:
        """Get skills required but not in user's profile"""
        missing = []
        for req_skill in required_skills:
            req_lower = req_skill.lower()
            if not any(req_lower in skill_name or skill_name in req_lower
                       for skill_name in self.skill_names):
                missing.append(req_skill)
        return missing


class CompanyTargeter:
    """Target companies for job applications"""

    def __init__(self, company_follows: List[CompanyFollow]):
        self.target_companies = {follow.organization.lower(): follow
                                for follow in company_follows}

    def is_target_company(self, company_name: str) -> bool:
        """Check if company is a target (followed) company"""
        return company_name.lower() in self.target_companies

    def get_target_companies(self) -> List[str]:
        """Get list of all target companies"""
        return list(self.target_companies.keys())

    def prioritize_job(self, company_name: str) -> float:
        """Return priority score for job at company (0-1)"""
        if self.is_target_company(company_name):
            return 1.0
        return 0.3  # Lower priority for non-target companies


class ApplicationAnalyzer:
    """Analyze past applications for patterns"""

    def __init__(self, applications: List[JobApplication]):
        self.applications = applications

    def get_salary_range(self) -> Tuple[int, int]:
        """Extract salary range from applications"""
        salaries = []
        for app in self.applications:
            qa = app.question_and_answers.lower()
            # Extract salary mentions
            if 'salary' in qa or 'aed' in qa:
                # Simple extraction - can be enhanced
                import re
                matches = re.findall(r'\d{4,6}', qa)
                for match in matches:
                    try:
                        salary = int(match)
                        if 5000 <= salary <= 100000:  # Reasonable range
                            salaries.append(salary)
                    except ValueError:
                        continue

        if salaries:
            return min(salaries), max(salaries)
        return 10000, 25000  # Default range

    def get_common_roles(self) -> Dict[str, int]:
        """Get most common job titles applied to"""
        roles = {}
        for app in self.applications:
            title = app.job_title.strip()
            if title:
                roles[title] = roles.get(title, 0) + 1
        return dict(sorted(roles.items(), key=lambda x: x[1], reverse=True)[:10])

    def get_successful_templates(self) -> Dict[str, str]:
        """Extract common answer patterns"""
        # This would need feedback on which applications were successful
        # For now, return all Q&A patterns
        templates = {}
        for app in self.applications:
            if app.question_and_answers:
                templates[app.job_title] = app.question_and_answers
        return templates


class ResumeGenerator:
    """Generate resume from LinkedIn data"""

    def __init__(self, profile: Profile, positions: List[Position], skills: List[Skill]):
        self.profile = profile
        self.positions = positions
        self.skills = skills

    def generate_resume_text(self) -> str:
        """Generate formatted resume text"""
        lines = []

        # Header
        lines.append(f"{self.profile.first_name} {self.profile.last_name}")
        lines.append(self.profile.headline)
        lines.append(self.profile.location)
        lines.append("")

        # Summary
        lines.append("PROFESSIONAL SUMMARY")
        lines.append(self.profile.summary)
        lines.append("")

        # Experience
        lines.append("WORK EXPERIENCE")
        for position in sorted(self.positions, key=lambda x: x.started_on, reverse=True):
            lines.append(f"{position.title} | {position.company_name}")
            lines.append(f"{position.started_on} - {position.finished_on or 'Present'}")
            lines.append(f"{position.location}")
            lines.append(position.description)
            lines.append("")

        # Skills
        lines.append("SKILLS")
        skill_list = [skill.name for skill in self.skills[:20]]  # Top 20
        lines.append(", ".join(skill_list))
        lines.append("")

        return "\n".join(lines)


class ScreeningResponseAutoFill:
    """Auto-fill screening questions"""

    def __init__(self, saved_answers: Dict[str, str], applications: List[JobApplication]):
        self.saved_answers = saved_answers
        self.applications = applications

    def find_answer(self, question: str) -> Optional[str]:
        """Find pre-written answer for question"""
        question_lower = question.lower()

        # Check exact matches
        if question in self.saved_answers:
            return self.saved_answers[question]

        # Check partial matches
        for saved_q, answer in self.saved_answers.items():
            if question_lower in saved_q.lower() or saved_q.lower() in question_lower:
                return answer

        # Search in past applications
        for app in self.applications:
            if question_lower in app.question_and_answers.lower():
                # Extract answer from Q&A string
                qa_pairs = app.question_and_answers.split('|')
                for pair in qa_pairs:
                    if question_lower in pair.lower():
                        # Return the value part
                        parts = pair.split(':')
                        if len(parts) > 1:
                            return ':'.join(parts[1:]).strip()

        return None


class NetworkOutreach:
    """Find connections at target companies"""

    def __init__(self, connections: List[Connection], target_companies: Set[str]):
        self.connections = connections
        self.target_companies = target_companies

    def get_connections_at_company(self, company_name: str) -> List[Connection]:
        """Get connections who work at specific company"""
        company_lower = company_name.lower()
        matching = []

        for conn in self.connections:
            if company_lower in conn.company.lower():
                matching.append(conn)

        return matching

    def get_all_target_connections(self) -> Dict[str, List[Connection]]:
        """Get all connections at target companies"""
        result = {}

        for company in self.target_companies:
            connections = self.get_connections_at_company(company)
            if connections:
                result[company] = connections

        return result


def main():
    """Test the LinkedIn integration"""
    loader = LinkedInDataLoader()
    loader.load_all()

    if loader.profile:
        print(f"Profile: {loader.profile.first_name} {loader.profile.last_name}")
        print(f"Headline: {loader.profile.headline}")

    print(f"\nSkills: {len(loader.skills)}")
    print(f"Companies followed: {len(loader.company_follows)}")
    print(f"Connections: {len(loader.connections)}")
    print(f"Applications: {len(loader.job_applications)}")

    # Test skill matching
    matcher = SkillMatcher(loader.skills)
    test_desc = "Looking for Project Manager with ESG and Sustainability experience"
    print(f"\nMatching skills for: {test_desc}")
    print(matcher.get_matching_skills(test_desc))

    # Test company targeting
    targeter = CompanyTargeter(loader.company_follows)
    print(f"\nTarget companies: {targeter.get_target_companies()[:5]}")
    print(f"Is TAQA a target? {targeter.is_target_company('TAQA Group')}")

    # Test resume generation
    if loader.profile:
        generator = ResumeGenerator(loader.profile, loader.positions, loader.skills)
        print(f"\nResume preview:")
        print(generator.generate_resume_text()[:500])


if __name__ == "__main__":
    main()
