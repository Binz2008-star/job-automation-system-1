"""Update database to mark ELROI and Steadfast as applied."""
import sys
sys.path.append('.')

from src.db import mark_applied, get_db_connection

def update_elroi_and_steadfast():
    """Mark both ELROI and Steadfast jobs as applied in the database."""
    
    elroi_link = "https://ae.indeed.com/viewjob?jk=e4d2e2ab4cbe59f1"
    steadfast_link = "https://ae.indeed.com/viewjob?jk=f4a5c28f239970a5"
    
    print("Updating database applications table...")
    
    # Check if DB is available
    conn = get_db_connection()
    if not conn:
        print("⚠️ Database not available, skipping DB update")
        return False
    
    try:
        # Mark ELROI as applied
        if mark_applied(elroi_link, "Applied via Indeed Easy Apply"):
            print("✅ ELROI QHSE CONSULTANCY marked as applied")
        else:
            print("❌ Failed to mark ELROI as applied")
        
        # Mark Steadfast as applied
        if mark_applied(steadfast_link, "Applied via Indeed Easy Apply"):
            print("✅ Steadfast Trading and Contracting marked as applied")
        else:
            print("❌ Failed to mark Steadfast as applied")
        
        return True
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    update_elroi_and_steadfast()
