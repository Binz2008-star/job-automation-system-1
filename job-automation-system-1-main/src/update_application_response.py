"""
Application Response Update CLI
Command-line tool for updating application response status and notes.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.applications import load_applied_jobs, save_applied_jobs
from src.response_intelligence import ResponseType


def find_application_by_link(applications: List[Dict[str, Any]], link: str) -> Dict[str, Any]:
    """Find application by job link."""
    for app in applications:
        if app.get("link") == link:
            return app
    return None


def update_application_status(link: str, status: str, notes: str = None) -> bool:
    """Update application status and notes."""
    try:
        # Load existing applications
        applications = load_applied_jobs()
        
        # Find the application
        app = find_application_by_link(applications, link)
        if not app:
            print(f"❌ Application not found for link: {link}")
            print("   Available links:")
            for app in applications[:10]:  # Show first 10
                print(f"   - {app.get('link', 'No link')}")
            if len(applications) > 10:
                print(f"   ... and {len(applications) - 10} more")
            return False
        
        # Validate status using ResponseType
        try:
            response_type = ResponseType.from_raw(status)
            normalized_status = response_type.value
            print(f"✅ Status '{status}' normalized to '{normalized_status}'")
        except Exception as e:
            print(f"⚠️ Could not normalize status '{status}': {e}")
            normalized_status = status
        
        # Update the application
        old_status = app.get("status", "unknown")
        app["status"] = normalized_status
        app["date_updated"] = datetime.now().isoformat()
        
        if notes:
            app["notes"] = notes
            print(f"📝 Added notes: {notes}")
        
        # Save updated applications
        save_applied_jobs(applications)
        
        print(f"✅ Updated application:")
        print(f"   Title: {app.get('title', 'Unknown')}")
        print(f"   Company: {app.get('company', 'Unknown')}")
        print(f"   Status: {old_status} → {normalized_status}")
        print(f"   Updated: {app.get('date_updated')}")
        
        return True
        
    except Exception as e:
        print(f"❌ Failed to update application: {e}")
        return False


def list_applications():
    """List all applications with their current status."""
    try:
        applications = load_applied_jobs()
        
        if not applications:
            print("📝 No applications found.")
            return
        
        print(f"📋 Found {len(applications)} applications:")
        print("=" * 80)
        
        for i, app in enumerate(applications, 1):
            title = app.get("title", "Unknown")
            company = app.get("company", "Unknown")
            link = app.get("link", "No link")
            status = app.get("status", "unknown")
            date_applied = app.get("date_applied", "Unknown")
            notes = app.get("notes", "")
            
            print(f"{i:2d}. {title}")
            print(f"    Company: {company}")
            print(f"    Status: {status}")
            print(f"    Applied: {date_applied}")
            if notes:
                print(f"    Notes: {notes}")
            print(f"    Link: {link}")
            print()
            
    except Exception as e:
        print(f"❌ Failed to list applications: {e}")


def search_applications(query: str):
    """Search applications by title, company, or notes."""
    try:
        applications = load_applied_jobs()
        query_lower = query.lower()
        
        matches = []
        for app in applications:
            title = app.get("title", "").lower()
            company = app.get("company", "").lower()
            notes = app.get("notes", "").lower()
            link = app.get("link", "").lower()
            
            if (query_lower in title or query_lower in company or 
                query_lower in notes or query_lower in link):
                matches.append(app)
        
        if not matches:
            print(f"🔍 No applications found matching: {query}")
            return
        
        print(f"🔍 Found {len(matches)} applications matching '{query}':")
        print("=" * 80)
        
        for i, app in enumerate(matches, 1):
            title = app.get("title", "Unknown")
            company = app.get("company", "Unknown")
            link = app.get("link", "No link")
            status = app.get("status", "unknown")
            date_applied = app.get("date_applied", "Unknown")
            notes = app.get("notes", "")
            
            print(f"{i:2d}. {title}")
            print(f"    Company: {company}")
            print(f"    Status: {status}")
            print(f"    Applied: {date_applied}")
            if notes:
                print(f"    Notes: {notes}")
            print(f"    Link: {link}")
            print()
            
    except Exception as e:
        print(f"❌ Failed to search applications: {e}")


def show_status_options():
    """Show available status options."""
    print("📊 Available Status Options:")
    print("=" * 40)
    
    status_descriptions = {
        "rejected": "Application rejected by company",
        "no_response": "No response received (default)",
        "screening": "Application under review/ screening",
        "interview": "Interview scheduled (alias for interview_scheduled)",
        "interview_scheduled": "Interview scheduled",
        "interview_completed": "Interview completed",
        "technical_assessment": "Technical assessment required/completed",
        "offer": "Offer received (alias for offer_extended)",
        "offer_extended": "Offer extended",
        "offer_accepted": "Offer accepted",
        "offer_declined": "Offer declined",
        "follow_up_required": "Follow-up action needed"
    }
    
    for status, description in status_descriptions.items():
        print(f"  {status:<20} - {description}")
    
    print("\n💡 Tip: Use aliases like 'interview' instead of 'interview_scheduled'")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Update job application response status and notes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.update_application_response --link "https://example.com/job/123" --status interview
  python -m src.update_application_response --link "https://example.com/job/123" --status rejected --notes "Didn't match culture"
  python -m src.update_application_response --list
  python -m src.update_application_response --search "Google"
  python -m src.update_application_response --status-options
        """
    )
    
    parser.add_argument("--link", help="Job link to update")
    parser.add_argument("--status", help="New status (use --status-options to see available)")
    parser.add_argument("--notes", help="Optional notes about the application")
    parser.add_argument("--list", action="store_true", help="List all applications")
    parser.add_argument("--search", help="Search applications by title, company, or notes")
    parser.add_argument("--status-options", action="store_true", help="Show available status options")
    
    args = parser.parse_args()
    
    if args.status_options:
        show_status_options()
        return
    
    if args.list:
        list_applications()
        return
    
    if args.search:
        search_applications(args.search)
        return
    
    if not args.link:
        print("❌ --link is required when updating an application")
        print("   Use --list to see all applications")
        print("   Use --search to find specific applications")
        print("   Use --status-options to see available statuses")
        sys.exit(1)
    
    if not args.status:
        print("❌ --status is required when updating an application")
        print("   Use --status-options to see available statuses")
        sys.exit(1)
    
    success = update_application_status(args.link, args.status, args.notes)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
