"""
PDF Document Manager for Job Automation System
Handles PDF file operations, metadata extraction, and viewer integration.
"""

from __future__ import annotations

import os
import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
PDF_DIR = DATA_DIR / "pdfs"
METADATA_FILE = DATA_DIR / "pdf_metadata.json"

class PDFManager:
    """Manages PDF documents in the job automation system."""
    
    def __init__(self):
        self.ensure_directories()
        self.metadata = self.load_metadata()
    
    def ensure_directories(self):
        """Create necessary directories if they don't exist."""
        PDF_DIR.mkdir(exist_ok=True)
        DATA_DIR.mkdir(exist_ok=True)
    
    def load_metadata(self) -> Dict[str, Any]:
        """Load PDF metadata from JSON file."""
        try:
            if METADATA_FILE.exists():
                with open(METADATA_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        return {}
    
    def save_metadata(self):
        """Save PDF metadata to JSON file."""
        try:
            with open(METADATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.metadata, f, indent=2, default=str)
        except Exception as e:
            print(f"⚠️ Failed to save PDF metadata: {e}")
    
    def register_pdf(self, file_path: str, title: str, description: str = "", tags: List[str] = None) -> Dict[str, Any]:
        """Register a PDF file in the system."""
        pdf_path = Path(file_path)
        
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {file_path}")
        
        file_id = pdf_path.stem.lower().replace(" ", "_")
        relative_path = str(pdf_path.relative_to(BASE_DIR))
        
        pdf_info = {
            "id": file_id,
            "title": title,
            "description": description,
            "file_path": relative_path,
            "absolute_path": str(pdf_path.absolute()),
            "file_size": pdf_path.stat().st_size,
            "created_at": datetime.fromtimestamp(pdf_path.stat().st_ctime).isoformat(),
            "modified_at": datetime.fromtimestamp(pdf_path.stat().st_mtime).isoformat(),
            "registered_at": datetime.now().isoformat(),
            "tags": tags or [],
            "type": "document"
        }
        
        self.metadata[file_id] = pdf_info
        self.save_metadata()
        
        return pdf_info
    
    def get_pdf_info(self, file_id: str) -> Optional[Dict[str, Any]]:
        """Get PDF information by ID."""
        return self.metadata.get(file_id)
    
    def list_pdfs(self, tag_filter: str = None) -> List[Dict[str, Any]]:
        """List all registered PDFs, optionally filtered by tag."""
        pdfs = list(self.metadata.values())
        
        if tag_filter:
            pdfs = [pdf for pdf in pdfs if tag_filter in pdf.get("tags", [])]
        
        return sorted(pdfs, key=lambda x: x.get("registered_at", ""), reverse=True)
    
    def get_cv_pdf(self) -> Optional[Dict[str, Any]]:
        """Get the primary CV/Resume PDF."""
        cv_pdfs = [pdf for pdf in self.metadata.values() 
                  if "cv" in pdf.get("tags", []) or "resume" in pdf.get("tags", [])]
        
        if cv_pdfs:
            return sorted(cv_pdfs, key=lambda x: x.get("registered_at", ""), reverse=True)[0]
        
        # Fallback to default cv.pdf if it exists
        default_cv = DATA_DIR / "cv.pdf"
        if default_cv.exists():
            return self.register_pdf(
                str(default_cv),
                "Current CV",
                "Primary curriculum vitae document",
                ["cv", "resume", "primary"]
            )
        
        return None
    
    def generate_viewer_url(self, file_id: str, base_url: str = "") -> str:
        """Generate URL for PDF viewer."""
        pdf_info = self.get_pdf_info(file_id)
        if not pdf_info:
            return ""
        
        return f"{base_url}static/pdf_viewer.html?file={pdf_info['file_path']}&name={pdf_info['title'].replace(' ', '%20')}"

def initialize_pdf_system():
    """Initialize the PDF management system with default documents."""
    manager = PDFManager()
    
    # Check for default CV
    cv_path = DATA_DIR / "cv.pdf"
    if cv_path.exists() and not manager.get_cv_pdf():
        manager.register_pdf(
            str(cv_path),
            "Current CV",
            "Primary curriculum vitae document for job applications",
            ["cv", "resume", "primary"]
        )
        print("✅ Registered default CV document")
    
    return manager

if __name__ == "__main__":
    # Initialize PDF system
    manager = initialize_pdf_system()
    
    # List all PDFs
    pdfs = manager.list_pdfs()
    print(f"\n📄 Found {len(pdfs)} PDF documents:")
    for pdf in pdfs:
        print(f"  - {pdf['title']} ({pdf['file_path']})")
    
    # Show CV info
    cv = manager.get_cv_pdf()
    if cv:
        print(f"\n🎯 Primary CV: {cv['title']}")
        print(f"   Viewer URL: {manager.generate_viewer_url(cv['id'])}")
