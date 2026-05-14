"""
LinkedIn Integration Demo Script
Demonstrates all LinkedIn data integration features
"""

from linkedin_integration import (
    LinkedInDataLoader,
    SkillMatcher,
    CompanyTargeter,
    ApplicationAnalyzer,
    ResumeGenerator,
    ScreeningResponseAutoFill,
    NetworkOutreach
)


def main():
    print("=" * 80)
    print("LINKEDIN DATA INTEGRATION DEMO")
    print("=" * 80)
    
    # Load all LinkedIn data
    print("\n1. Loading LinkedIn data...")
    loader = LinkedInDataLoader()
    loader.load_all()
    
    print(f"   ✓ Profile: {loader.profile.first_name} {loader.profile.last_name}")
    print(f"   ✓ Skills: {len(loader.skills)}")
    print(f"   ✓ Companies followed: {len(loader.company_follows)}")
    print(f"   ✓ Connections: {len(loader.connections)}")
    print(f"   ✓ Job applications: {len(loader.job_applications)}")
    print(f"   ✓ Saved jobs: {len(loader.saved_jobs)}")
    print(f"   ✓ Saved answers: {len(loader.saved_answers)}")
    
    # Skill Matching Demo
    print("\n2. Skill Matching Engine")
    print("-" * 80)
    matcher = SkillMatcher(loader.skills)
    
    test_jobs = [
        "Project Manager with ESG and Sustainability experience",
        "HSE Manager for waste management operations",
        "Operations Director with environmental compliance",
        "Software Engineer for web development"
    ]
    
    for job_desc in test_jobs:
        matching_skills = matcher.get_matching_skills(job_desc)
        score = matcher.calculate_match_score(job_desc, [])
        print(f"   Job: {job_desc[:60]}...")
        print(f"   Matched skills: {', '.join(matching_skills[:5])}")
        print(f"   Score: {score:.2f}")
        print()
    
    # Company Targeting Demo
    print("\n3. Company Targeting System")
    print("-" * 80)
    targeter = CompanyTargeter(loader.company_follows)
    
    test_companies = [
        "TAQA Group",
        "Masdar",
        "BEEAH Group",
        "Environment Agency – Abu Dhabi",
        "Random Company XYZ"
    ]
    
    for company in test_companies:
        is_target = targeter.is_target_company(company)
        priority = targeter.prioritize_job(company)
        status = "✓ TARGET" if is_target else "✗ NOT TARGET"
        print(f"   {company}: {status} (priority: {priority})")
    
    print(f"\n   Top 5 target companies:")
    for company in targeter.get_target_companies()[:5]:
        print(f"   - {company}")
    
    # Application Analysis Demo
    print("\n4. Application History Analysis")
    print("-" * 80)
    analyzer = ApplicationAnalyzer(loader.job_applications)
    
    salary_min, salary_max = analyzer.get_salary_range()
    print(f"   Salary range: {salary_min:,} - {salary_max:,} AED")
    
    common_roles = analyzer.get_common_roles()
    print(f"\n   Top applied roles:")
    for role, count in list(common_roles.items())[:5]:
        print(f"   - {role}: {count} applications")
    
    # Resume Generation Demo
    print("\n5. Resume Generator")
    print("-" * 80)
    if loader.profile:
        generator = ResumeGenerator(loader.profile, loader.positions, loader.skills)
        resume = generator.generate_resume_text()
        print(f"   Resume preview (first 500 chars):")
        print(f"   {resume[:500]}...")
    
    # Screening Response Auto-fill Demo
    print("\n6. Screening Response Auto-fill")
    print("-" * 80)
    autofill = ScreeningResponseAutoFill(loader.saved_answers, loader.job_applications)
    
    test_questions = [
        "How many years of experience do you have?",
        "What is your current salary?",
        "Do you have a valid driver's license?"
    ]
    
    for question in test_questions:
        answer = autofill.find_answer(question)
        if answer:
            print(f"   Q: {question}")
            print(f"   A: {answer[:100]}...")
        else:
            print(f"   Q: {question}")
            print(f"   A: No saved answer found")
        print()
    
    # Network Outreach Demo
    print("\n7. Network Outreach")
    print("-" * 80)
    target_companies = {"taqa group", "masdar", "beeah group"}
    outreach = NetworkOutreach(loader.connections, target_companies)
    
    connections_at_targets = outreach.get_all_target_connections()
    print(f"   Found connections at {len(connections_at_targets)} target companies:")
    
    for company, connections in list(connections_at_targets.items())[:3]:
        print(f"\n   {company}:")
        for conn in connections[:3]:
            print(f"   - {conn.first_name} {conn.last_name} - {conn.position}")
            if conn.email:
                print(f"     Email: {conn.email}")
    
    # Summary
    print("\n" + "=" * 80)
    print("LINKEDIN INTEGRATION SUMMARY")
    print("=" * 80)
    print("All LinkedIn data features are now integrated and operational:")
    print("  ✓ Skill matching for job descriptions")
    print("  ✓ Company targeting from followed companies")
    print("  ✓ Application history analysis")
    print("  ✓ Resume generation from profile data")
    print("  ✓ Screening response auto-fill")
    print("  ✓ Network outreach for referrals")
    print("\nThe LinkedIn data is automatically loaded and used in job_agent.py")
    print("to enhance job matching and application decisions.")
    print("=" * 80)


if __name__ == "__main__":
    main()
