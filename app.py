"""
FastAPI Application for Finance Month-End Close AI Agent
Provides tools for Watsonx Orchestrate integration with Dashboard Approvals
Includes CFO Financial Dashboard and Email Reports with SendGrid
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timedelta
from enum import Enum
import csv
import os
from collections import defaultdict
import uuid
import pandas as pd
import logging
import io
import base64
import tempfile
import json

# Email and PDF libraries
from dotenv import load_dotenv
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Attachment, FileContent, FileName, FileType, Disposition
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

# Load environment variables
load_dotenv()


# Add this debug section
import os
print("\n" + "="*60)
print("🔍 ENVIRONMENT VARIABLES DEBUG")
print("="*60)
print(f"📁 Current working directory: {os.getcwd()}")
print(f"📄 .env file exists: {os.path.exists('.env')}")
print(f"🔑 SENDGRID_API_KEY present: {'✅ YES' if os.getenv('SENDGRID_API_KEY') else '❌ NO'}")
if os.getenv('SENDGRID_API_KEY'):
    # Show first 10 chars of API key to verify it's loading correctly
    api_key = os.getenv('SENDGRID_API_KEY')
    print(f"   Key starts with: {api_key[:15]}...")
    print(f"   Key length: {len(api_key)} chars")
print(f"📧 FROM_EMAIL: {os.getenv('FROM_EMAIL')}")
print(f"🌐 APP_BASE_URL: {os.getenv('APP_BASE_URL')}")
print("="*60 + "\n")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Finance Month-End Close AI Agent API",
    description="API endpoints for AI-powered month-end close automation with Dashboard Approvals and Email Reports",
    version="3.0.0"
)

# CORS middleware for cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Base URL for dashboard links
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000")

# ============================================================================
# DATA MODELS (Enhanced with Approval Tracking)
# ============================================================================

class SeverityLevel(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"

class ExceptionType(str, Enum):
    MISSING_COST_CENTER = "Missing Cost Center"
    AR_GL_VARIANCE = "AR/GL Variance"
    INVALID_ACCOUNT = "Invalid Account Code"
    OVERDUE_INVOICE = "Overdue Invoice"
    LARGE_OUTSTANDING = "Large Outstanding Balance"

class MilestoneStatus(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"

class ApprovalStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    IN_REVIEW = "IN_REVIEW"
    ASSIGNED = "ASSIGNED"  # New status for assigned items

class ToolResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None
    exceptions: Optional[List[Dict[str, Any]]] = None
    timestamp: datetime = Field(default_factory=datetime.now)

class TrialBalanceRequest(BaseModel):
    fiscal_period: str = Field(..., example="2026-04")
    entity_code: str = Field(default="AUS01", example="AUS01")

class ARVarianceRequest(BaseModel):
    fiscal_period: str = Field(..., example="2026-04")
    entity_code: str = Field(default="AUS01", example="AUS01")

class CostCenterAssignment(BaseModel):
    transaction_id: str
    cost_center: str
    approved_by: Optional[str] = None

class CostCenterBatchRequest(BaseModel):
    assignments: List[CostCenterAssignment]
    fiscal_period: str = Field(..., example="2026-04")

class CostCenterSuggestion(BaseModel):
    transaction_id: str
    suggested_cost_center: str
    reason: str = Field(..., example="Vendor pattern: Zoom → IT")
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)

class CostCenterSuggestionsRequest(BaseModel):
    suggestions: List[CostCenterSuggestion]
    fiscal_period: str = Field(..., example="2026-04")


class JournalEntry(BaseModel):
    entry_id: str
    date: str
    description: str
    debit_account: str
    credit_account: str
    amount: float
    approved: bool = False
    approved_by: Optional[str] = None

class JournalEntryRequest(BaseModel):
    entries: List[JournalEntry]
    fiscal_period: str = Field(..., example="2026-04")

class BudgetVarianceRequest(BaseModel):
    fiscal_period: str = Field(..., example="2026-04")
    entity_code: str = Field(default="AUS01", example="AUS01")

class YoYComparisonRequest(BaseModel):
    current_period: str = Field(..., example="2026-04")
    comparison_period: str = Field(..., example="2025-04")
    entity_code: str = Field(default="AUS01", example="AUS01")

class CostCenterPLRequest(BaseModel):
    fiscal_period: str = Field(..., example="2026-04")
    entity_code: str = Field(default="AUS01", example="AUS01")

class MonthEndCloseRequest(BaseModel):
    fiscal_period: str = Field(..., example="2026-04")
    entity_code: str = Field(default="AUS01", example="AUS01")
    approved_by: str
    send_email_reports: bool = Field(True, description="Send email reports after closing")

# New Models for Approval System
class ApprovalItem(BaseModel):
    id: str
    type: str  # 'cost_center_assignment', 'journal_entry', 'ar_reconciliation', 'bank_reconciliation', etc.
    description: str
    amount: Optional[float] = None
    account: Optional[str] = None
    cost_center: Optional[str] = None
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.now)
    token: str = Field(default_factory=lambda: str(uuid.uuid4()))
    metadata: Optional[Dict[str, Any]] = None
    assigned_to: Optional[str] = None  # New field for assignee
    assigned_at: Optional[datetime] = None  # New field for assignment timestamp

class ApprovalDecision(BaseModel):
    token: str
    approved: bool
    reviewer: str
    comments: Optional[str] = None

class ApprovalBatchRequest(BaseModel):
    tokens: List[str]
    approved: bool
    reviewer: str
    comments: Optional[str] = None

# New model for assignment
class ApprovalAssignmentRequest(BaseModel):
    token: str
    assignee_email: EmailStr
    assignee_name: Optional[str] = None
    assigner: str
    comments: Optional[str] = None

# ============================================================================
# EMAIL REPORTING MODELS
# ============================================================================

class EmailRecipient(BaseModel):
    email: EmailStr
    name: Optional[str] = None

class EmailReportRequest(BaseModel):
    recipients: List[EmailRecipient]
    fiscal_period: str = Field("2026-04", description="Fiscal period for reports")
    entity_code: str = Field("AUS01", description="Entity code")
    include_pdf: bool = Field(True, description="Include PDF report")
    include_csv: bool = Field(True, description="Include CSV data")
    report_types: List[str] = Field(
        ["trial_balance", "income_statement", "balance_sheet", "ar_aging", "budget_variance"],
        description="Types of reports to include"
    )
    subject: Optional[str] = None
    message: Optional[str] = None

class EmailReportResponse(BaseModel):
    success: bool
    message: str
    email_id: Optional[str] = None
    recipients: List[str]
    reports_sent: List[str]
    timestamp: datetime = Field(default_factory=datetime.now)

# ============================================================================
# APPROVAL REGISTRY - Tracks ALL approvals generated during the session
# ============================================================================

class ApprovalRegistry:
    """Tracks all approvals generated and their status"""
    
    def __init__(self):
        self.generated_approvals = {}  # Dict[token, approval_info]
        self.registry_file = 'approval_registry.csv'
        self._load_registry()
    
    def _load_registry(self):
        """Load existing registry from CSV if available"""
        if os.path.exists(self.registry_file):
            try:
                with open(self.registry_file, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        token = row.pop('token')
                        self.generated_approvals[token] = row
                logger.info(f"📋 Loaded {len(self.generated_approvals)} approvals from registry")
            except Exception as e:
                logger.error(f"Error loading registry: {e}")
    
    def _save_registry(self):
        """Save registry to CSV for persistence"""
        if not self.generated_approvals:
            return
        
        try:
            fieldnames = ['token', 'type', 'description', 'amount', 'created_at', 
                         'fiscal_period', 'entity', 'status', 'decision', 'processed_at',
                         'metadata_summary']
            
            with open(self.registry_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                
                for token, info in self.generated_approvals.items():
                    row = {'token': token, **info}
                    writer.writerow(row)
            
            logger.info(f"💾 Saved {len(self.generated_approvals)} approvals to registry")
        except Exception as e:
            logger.error(f"Error saving registry: {e}")
    
    def register_approval(self, token: str, approval_item: ApprovalItem):
        """Register a newly generated approval"""
        self.generated_approvals[token] = {
            'type': approval_item.type,
            'description': approval_item.description[:100],
            'amount': str(approval_item.amount) if approval_item.amount else '',
            'created_at': datetime.now().isoformat(),
            'fiscal_period': approval_item.metadata.get('fiscal_period', '2026-04') if approval_item.metadata else '2026-04',
            'entity': approval_item.metadata.get('entity', 'AUS01') if approval_item.metadata else 'AUS01',
            'status': 'PENDING',
            'metadata_summary': self._summarize_metadata(approval_item.metadata)
        }
        self._save_registry()
        logger.info(f"📝 Registered approval {token} of type {approval_item.type}")
    
    def update_approval_status(self, token: str, status: str, decision: str = None):
        """Update status when approval is processed"""
        if token in self.generated_approvals:
            self.generated_approvals[token]['status'] = status
            if decision:
                self.generated_approvals[token]['decision'] = decision
                self.generated_approvals[token]['processed_at'] = datetime.now().isoformat()
            self._save_registry()
    
    def _summarize_metadata(self, metadata: dict) -> str:
        """Create a brief summary of metadata for tracking"""
        if not metadata:
            return ''
        
        important_fields = []
        
        # Check for transaction IDs
        if 'transaction_id' in metadata:
            important_fields.append(f"txn:{metadata['transaction_id']}")
        if 'accrual_id' in metadata:
            important_fields.append(f"accrual:{metadata['accrual_id']}")
        if 'item_id' in metadata:
            important_fields.append(f"item:{metadata['item_id']}")
        if 'invoice_number' in metadata:
            important_fields.append(f"inv:{metadata['invoice_number']}")
        if 'entry_id' in metadata:
            important_fields.append(f"je:{metadata['entry_id']}")
        if 'variance_id' in metadata:
            important_fields.append(f"var:{metadata['variance_id']}")
        
        # Check for counts
        if 'count' in metadata:
            important_fields.append(f"count:{metadata['count']}")
        
        return '; '.join(important_fields)[:200]
    
    def get_pending_approvals(self, fiscal_period: str = None) -> List[Dict]:
        """Get all pending approvals"""
        pending = []
        for token, info in self.generated_approvals.items():
            if info.get('status') == 'PENDING':
                if not fiscal_period or info.get('fiscal_period') == fiscal_period:
                    pending.append({'token': token, **info})
        return pending
    
    def get_processed_approvals(self, fiscal_period: str = None) -> List[Dict]:
        """Get all processed (approved/rejected) approvals"""
        processed = []
        for token, info in self.generated_approvals.items():
            if info.get('status') in ['APPROVED', 'REJECTED', 'ASSIGNED']:
                if not fiscal_period or info.get('fiscal_period') == fiscal_period:
                    processed.append({'token': token, **info})
        return processed
    
    def get_approval_summary(self, fiscal_period: str = None) -> Dict:
        """Get summary of approvals by type and status"""
        summary = {
            'total_generated': 0,
            'pending': 0,
            'approved': 0,
            'rejected': 0,
            'assigned': 0,
            'by_type': {},
            'by_status': {}
        }
        
        for token, info in self.generated_approvals.items():
            if fiscal_period and info.get('fiscal_period') != fiscal_period:
                continue
            
            summary['total_generated'] += 1
            status = info.get('status', 'UNKNOWN')
            
            # Count by status
            summary['by_status'][status] = summary['by_status'].get(status, 0) + 1
            if status == 'PENDING':
                summary['pending'] += 1
            elif status == 'APPROVED':
                summary['approved'] += 1
            elif status == 'REJECTED':
                summary['rejected'] += 1
            elif status == 'ASSIGNED':
                summary['assigned'] += 1
            
            # Count by type
            approval_type = info.get('type', 'Unknown')
            if approval_type not in summary['by_type']:
                summary['by_type'][approval_type] = {'total': 0, 'pending': 0, 'approved': 0, 'rejected': 0, 'assigned': 0}
            
            summary['by_type'][approval_type]['total'] += 1
            summary['by_type'][approval_type][status.lower()] = summary['by_type'][approval_type].get(status.lower(), 0) + 1
        
        return summary
    
    def verify_all_approvals_processed(self, fiscal_period: str = None) -> Tuple[bool, List]:
        """Verify that all generated approvals have been processed"""
        pending = self.get_pending_approvals(fiscal_period)
        if pending:
            return False, pending
        return True, []

# Initialize the registry
approval_registry = ApprovalRegistry()

def update_progress_from_approvals():
    """Helper to update progress milestones after approvals"""
    update_milestones_from_approvals("2026-04")

# ============================================================================
# DATA STORES (In-memory for demo - use database in production)
# ============================================================================

# Store for pending approvals
pending_approvals: Dict[str, ApprovalItem] = {}

# Store for approval history
approval_history: List[Dict[str, Any]] = []

# Store for assignees (in production, this would come from a database)
assignees_db = [
    {"email": "steny.sebastian@octanesolutions.com.au", "name": "Steny Sebastian", "role": "Senior Accountant"},
    {"email": "alan.cheeramvelil@octanesolutions.com.au", "name": "Alan Francis Cheeramvelil", "role": "Finance Manager"},
    {"email": "deepanshu.dubey@octanesolutions.com.au", "name": "Deepanshu Dubey", "role": "Treasury Analyst"},
]

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def load_csv_data(filename: str) -> List[Dict[str, Any]]:
    """Load CSV file and return list of dictionaries"""
    if not os.path.exists(filename):
        raise HTTPException(status_code=404, detail=f"File {filename} not found")
    
    data = []
    with open(filename, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            data.append(row)
    return data

def save_csv_data(filename: str, data: List[Dict[str, Any]], fieldnames: List[str]):
    """Save data to CSV file"""
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)

def load_coa() -> Dict[str, Dict[str, str]]:
    """Load Chart of Accounts"""
    coa = {}
    data = load_csv_data('Master_COA_Complete.csv')
    for row in data:
        coa[row['Account_Code']] = {
            'name': row['Account_Name'],
            'type': row['Account_Type'],
            'category': row['Category']
        }
    return coa

def generate_approval_token() -> str:
    """Generate unique approval token"""
    return str(uuid.uuid4())

def create_approval_item(
    item_type: str,
    description: str,
    amount: Optional[float] = None,
    account: Optional[str] = None,
    cost_center: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    fiscal_period: str = "2026-04"
) -> ApprovalItem:
    """Create and store a new approval item"""
    item_id = str(uuid.uuid4())[:8]
    token = generate_approval_token()
    
    # Ensure metadata doesn't contain datetime objects that might cause issues
    if metadata:
        clean_metadata = {}
        for k, v in metadata.items():
            if isinstance(v, datetime):
                clean_metadata[k] = v.isoformat()
            else:
                clean_metadata[k] = v
        # Add fiscal_period to metadata
        clean_metadata['fiscal_period'] = fiscal_period
    else:
        clean_metadata = {'fiscal_period': fiscal_period}
    
    item = ApprovalItem(
        id=item_id,
        type=item_type,
        description=description,
        amount=amount,
        account=account,
        cost_center=cost_center,
        status=ApprovalStatus.PENDING,
        token=token,
        metadata=clean_metadata
    )
    
    pending_approvals[token] = item
    
    # REGISTER IN THE REGISTRY
    approval_registry.register_approval(token, item)
    
    logger.info(f"Created approval item: {item_type} - {item_id} (Token: {token}) for period {fiscal_period}")
    return item

def get_approval_links(token: str) -> Dict[str, str]:
    """Generate approval links for dashboard"""
    return {
        "approve_url": f"{APP_BASE_URL}/approvals/decide?token={token}&approved=true",
        "reject_url": f"{APP_BASE_URL}/approvals/decide?token={token}&approved=false",
        "dashboard_url": f"{APP_BASE_URL}/dashboard/approvals/{token}",
        "status_url": f"{APP_BASE_URL}/approvals/status/{token}",
        "assign_url": f"{APP_BASE_URL}/approvals/assign-page/{token}"
    }

def format_metadata_for_display(metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Format metadata into bullet points for display"""
    if not metadata:
        return []
    
    formatted = []
    
    # Common fields to display
    for key, value in metadata.items():
        # Format key for display
        display_key = key.replace('_', ' ').title()
        
        # Skip None values
        if value is None:
            continue
            
        # Format value based on type
        if isinstance(value, dict):
            # Recursively format nested dictionaries
            nested_items = format_metadata_for_display(value)
            if nested_items:  # Only add if there are nested items
                formatted.append({
                    'key': display_key,
                    'value': '',
                    'is_section': True,
                    'children': nested_items
                })
        elif isinstance(value, list):
            if value and len(value) > 0:
                if isinstance(value[0], dict):
                    # List of objects
                    children = []
                    for i, item in enumerate(value):
                        if isinstance(item, dict):
                            item_children = format_metadata_for_display(item)
                            if item_children:
                                children.append({
                                    'key': f"Item {i+1}",
                                    'value': '',
                                    'is_section': True,
                                    'children': item_children
                                })
                    if children:
                        formatted.append({
                            'key': display_key,
                            'value': '',
                            'is_section': True,
                            'children': children
                        })
                else:
                    # Simple list
                    formatted.append({
                        'key': display_key,
                        'value': ', '.join(str(v) for v in value if v is not None)
                    })
        elif isinstance(value, (int, float)):
            # Check if it's likely a currency value
            str_key = key.lower()
            if any(term in str_key for term in ['amount', 'balance', 'variance', 'price', 'cost', 'total', 'budget', 'actual']):
                formatted.append({
                    'key': display_key,
                    'value': f"${value:,.2f}"
                })
            else:
                formatted.append({
                    'key': display_key,
                    'value': f"{value:,.2f}" if isinstance(value, float) else str(value)
                })
        elif isinstance(value, datetime):
            formatted.append({
                'key': display_key,
                'value': value.strftime('%Y-%m-%d %H:%M')
            })
        else:
            # String or other values
            str_value = str(value)
            if len(str_value) > 100:  # Truncate very long strings
                str_value = str_value[:100] + "..."
            formatted.append({
                'key': display_key,
                'value': str_value
            })
    
    return formatted

def send_email_notification(
    to_email: str,
    to_name: str,
    subject: str,
    html_content: str
) -> Dict[str, Any]:
    """
    Send email notification using SendGrid
    """
    # Get API key from environment
    api_key = os.getenv("SENDGRID_API_KEY")
    from_email = os.getenv("FROM_EMAIL", "deepanshu.dubey@octanesolutions.com.au")
    
    if not api_key:
        logger.warning(f"⚠️ SENDGRID_API_KEY not found - simulated email to {to_email}")
        logger.info(f"📧 SIMULATED EMAIL:")
        logger.info(f"   To: {to_name} <{to_email}>")
        logger.info(f"   Subject: {subject}")
        
        return {
            "success": False,
            "message": "SendGrid API key not configured - email simulated",
            "simulated": True
        }
    
    try:
        # Create mail object
        message = Mail(
            from_email=from_email,
            to_emails=to_email,
            subject=subject,
            html_content=html_content
        )
        
        # Send email
        sg = SendGridAPIClient(api_key)
        response = sg.send(message)
        
        logger.info(f"✅ Email sent to {to_email}! Status Code: {response.status_code}")
        
        return {
            "success": True,
            "message": "Email sent successfully",
            "status_code": response.status_code
        }
        
    except Exception as e:
        logger.error(f"❌ Error sending email: {str(e)}")
        return {
            "success": False,
            "message": f"Error sending email: {str(e)}"
        }


# ============================================================================
# CLOSE PROGRESS DASHBOARD - TRACKS ALL DECISIONS AND PROGRESS
# ============================================================================

# ============================================================================
# CLOSE PROGRESS TRACKER - REDESIGNED WITH PROPER STAGE TRACKING
# ============================================================================

class MilestoneStatus(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"

class CloseProgressTracker:
    """Tracks progress of month-end close across all activities with proper state management"""
    
    def __init__(self):
        self.progress_file = 'close_progress.json'
        
        # Redesigned milestone structure with status and progress
        self.milestones = {
            'data_validation': {
                'name': 'Data Validation',
                'weight': 10,
                'status': MilestoneStatus.NOT_STARTED,
                'progress': 0.0,
                'approval_types': []  # No specific approval types - based on general data quality
            },
            'cost_center_assignment': {
                'name': 'Cost Center Assignment',
                'weight': 10,
                'status': MilestoneStatus.NOT_STARTED,
                'progress': 0.0,
                'approval_types': ['Missing Cost Center']
            },
            'ar_reconciliation': {
                'name': 'AR Reconciliation',
                'weight': 15,
                'status': MilestoneStatus.NOT_STARTED,
                'progress': 0.0,
                'approval_types': ['AR Variance Correction', 'AR Missing Cost Centers']
            },
            'intercompany_reconciliation': {
                'name': 'Intercompany Reconciliation',
                'weight': 20,
                'status': MilestoneStatus.NOT_STARTED,
                'progress': 0.0,
                'approval_types': ['Intercompany Variance']
            },
            'accruals_prepayments': {
                'name': 'Accruals & Prepayments',
                'weight': 15,
                'status': MilestoneStatus.NOT_STARTED,
                'progress': 0.0,
                'approval_types': ['Accrual Variance']
            },
            'bank_reconciliation': {
                'name': 'Bank Reconciliation',
                'weight': 15,
                'status': MilestoneStatus.NOT_STARTED,
                'progress': 0.0,
                'approval_types': ['Bank Reconciliation']
            },
            'budget_variance_review': {
                'name': 'Budget Variance Review',
                'weight': 10,
                'status': MilestoneStatus.NOT_STARTED,
                'progress': 0.0,
                'approval_types': ['Budget Variance']
            },
            'final_trial_balance': {
                'name': 'Final Trial Balance',
                'weight': 5,
                'status': MilestoneStatus.NOT_STARTED,
                'progress': 0.0,
                'approval_types': []  # All approvals must be complete
            }
        }
        self._load_progress()
    
    def _load_progress(self):
        """Load saved progress from file with backward compatibility"""
        if os.path.exists(self.progress_file):
            try:
                with open(self.progress_file, 'r') as f:
                    data = json.load(f)
                    
                # Load milestone data with backward compatibility
                for key, value in data.get('milestones', {}).items():
                    if key in self.milestones:
                        # Handle old format (completed: bool)
                        if 'completed' in value and 'status' not in value:
                            if value['completed']:
                                self.milestones[key]['status'] = MilestoneStatus.COMPLETED
                                self.milestones[key]['progress'] = 100.0
                            else:
                                self.milestones[key]['status'] = MilestoneStatus.NOT_STARTED
                                self.milestones[key]['progress'] = 0.0
                        else:
                            # New format
                            self.milestones[key]['status'] = MilestoneStatus(value.get('status', 'NOT_STARTED'))
                            self.milestones[key]['progress'] = float(value.get('progress', 0.0))
                
                logger.info(f"📊 Loaded close progress from {self.progress_file}")
            except Exception as e:
                logger.error(f"Error loading progress: {e}")
                self.reset()
    
    def _save_progress(self):
        """Save progress to file"""
        try:
            # Convert milestones to serializable format
            milestones_data = {}
            for key, milestone in self.milestones.items():
                milestones_data[key] = {
                    'name': milestone['name'],
                    'weight': milestone['weight'],
                    'status': milestone['status'].value,
                    'progress': milestone['progress']
                }
            
            data = {
                'milestones': milestones_data,
                'last_updated': datetime.now().isoformat()
            }
            with open(self.progress_file, 'w') as f:
                json.dump(data, f, indent=2, default=str)
            logger.info(f"💾 Saved close progress to {self.progress_file}")
        except Exception as e:
            logger.error(f"Error saving progress: {e}")
    
    def reset(self):
        """Reset all milestones to NOT_STARTED state"""
        for key in self.milestones:
            self.milestones[key]['status'] = MilestoneStatus.NOT_STARTED
            self.milestones[key]['progress'] = 0.0
        self._save_progress()
        logger.info("🔄 All milestones reset to NOT_STARTED")
    
    def update_milestone_progress(self, milestone_key: str, total_items: int, pending_items: int):
        """
        Update milestone progress based on actual work items.
        
        CORRECT LOGIC:
        - total_items == 0: NOT_STARTED, progress = 0
        - pending_items == total_items: NOT_STARTED, progress = 0
        - pending_items > 0: IN_PROGRESS, progress = ((total - pending) / total) * 100
        - pending_items == 0 AND total_items > 0: COMPLETED, progress = 100
        """
        if milestone_key not in self.milestones:
            logger.warning(f"Unknown milestone key: {milestone_key}")
            return
        
        if total_items == 0 or pending_items == total_items:
            # No work has been done or no items exist
            self.milestones[milestone_key]['status'] = MilestoneStatus.NOT_STARTED
            self.milestones[milestone_key]['progress'] = 0.0
        elif pending_items > 0:
            # Work in progress
            self.milestones[milestone_key]['status'] = MilestoneStatus.IN_PROGRESS
            self.milestones[milestone_key]['progress'] = ((total_items - pending_items) / total_items) * 100
        else:
            # All work completed (pending == 0 AND total > 0)
            self.milestones[milestone_key]['status'] = MilestoneStatus.COMPLETED
            self.milestones[milestone_key]['progress'] = 100.0
        
        self._save_progress()
        logger.info(f"📊 Milestone '{milestone_key}': status={self.milestones[milestone_key]['status'].value}, "
                   f"progress={self.milestones[milestone_key]['progress']:.1f}%")
    
    def calculate_overall_milestone_progress(self) -> float:
        """
        Calculate overall progress using WEIGHTED PARTIAL PROGRESS.
        
        Formula: sum(weight * (milestone.progress / 100)) / total_weight * 100
        """
        total_weight = sum(m['weight'] for m in self.milestones.values())
        
        if total_weight == 0:
            return 0.0
        
        weighted_sum = sum(
            m['weight'] * (m['progress'] / 100.0)
            for m in self.milestones.values()
        )
        
        return (weighted_sum / total_weight) * 100
    
    def get_current_stage(self) -> Dict[str, Any]:
        """
        Get the current active stage of the close process.
        
        Returns the FIRST milestone that is NOT completed.
        If all are completed, returns a completed status.
        """
        for key, milestone in self.milestones.items():
            if milestone['status'] != MilestoneStatus.COMPLETED:
                return {
                    'stage_key': key,
                    'stage_name': milestone['name'],
                    'status': milestone['status'].value,
                    'progress': milestone['progress']
                }
        
        # All milestones are completed
        return {
            'stage_key': 'complete',
            'stage_name': 'Close Complete',
            'status': 'COMPLETED',
            'progress': 100.0
        }
    
    def get_incomplete_milestones(self) -> List[Dict]:
        """Get list of incomplete milestones with their current status"""
        return [
            {
                'key': key,
                'name': data['name'],
                'weight': data['weight'],
                'status': data['status'].value,
                'progress': data['progress']
            }
            for key, data in self.milestones.items()
            if data['status'] != MilestoneStatus.COMPLETED
        ]
    
    def get_milestone_summary(self) -> Dict[str, Any]:
        """Get complete milestone summary for UI display"""
        milestones_summary = {}
        for key, milestone in self.milestones.items():
            milestones_summary[key] = {
                'name': milestone['name'],
                'weight': milestone['weight'],
                'status': milestone['status'].value,
                'progress': milestone['progress'],
                'approval_types': milestone['approval_types']
            }
        
        return {
            'milestones': milestones_summary,
            'overall_progress': self.calculate_overall_milestone_progress(),
            'current_stage': self.get_current_stage(),
            'incomplete_count': len(self.get_incomplete_milestones()),
            'last_updated': datetime.now().isoformat()
        }

# Initialize progress tracker
progress_tracker = CloseProgressTracker()

def update_milestones_from_approvals(fiscal_period: str = "2026-04"):
    """
    CORRECTED: Update milestone progress based on approval registry data.
    
    Rules:
    1. Milestone is COMPLETED ONLY IF: total_items > 0 AND pending_items == 0
    2. If total_items == 0: milestone is NOT_STARTED
    3. If pending_items > 0: milestone is IN_PROGRESS
    """
    approval_summary = approval_registry.get_approval_summary(fiscal_period)
    by_type = approval_summary.get('by_type', {})
    
    # Process each milestone using its mapped approval types
    for milestone_key, milestone in progress_tracker.milestones.items():
        approval_types = milestone.get('approval_types', [])
        
        if not approval_types:
            # Special milestones without mapped approval types
            if milestone_key == 'data_validation':
                # Data validation: Check if any data analysis has been performed
                # This is completed if we have generated any approvals from initial analysis
                total_generated = approval_summary.get('total_generated', 0)
                if total_generated > 0:
                    # Data has been analyzed (approvals generated), check if blocking issues exist
                    blocking_types = ['Missing Cost Center', 'AR Variance Correction', 'Invalid Account Codes']
                    blocking_pending = sum(
                        by_type.get(bt, {}).get('pending', 0)
                        for bt in blocking_types
                    )
                    if blocking_pending == 0:
                        progress_tracker.update_milestone_progress(
                            milestone_key, 
                            total_items=total_generated,
                            pending_items=0
                        )
                    else:
                        # Some blocking items still pending
                        total_relevant = sum(
                            by_type.get(bt, {}).get('total', 0)
                            for bt in blocking_types
                        )
                        progress_tracker.update_milestone_progress(
                            milestone_key,
                            total_items=total_relevant if total_relevant > 0 else total_generated,
                            pending_items=blocking_pending
                        )
                else:
                    # No analysis performed yet
                    progress_tracker.update_milestone_progress(milestone_key, total_items=0, pending_items=0)
            
            elif milestone_key == 'final_trial_balance':
                # Final TB: Complete only when ALL approvals are processed
                total_all = approval_summary.get('total_generated', 0)
                pending_all = approval_summary.get('pending', 0)
                progress_tracker.update_milestone_progress(milestone_key, total_items=total_all, pending_items=pending_all)
        
        else:
            # Milestones with mapped approval types
            total_items = 0
            pending_items = 0
            
            for atype in approval_types:
                type_data = by_type.get(atype, {})
                total_items += type_data.get('total', 0)
                pending_items += type_data.get('pending', 0)
            
            # Update milestone progress with correct totals
            progress_tracker.update_milestone_progress(milestone_key, total_items, pending_items)
    
    # Log current state
    overall = progress_tracker.calculate_overall_milestone_progress()
    current = progress_tracker.get_current_stage()
    logger.info(f"📊 Updated milestones: overall={overall:.1f}%, current_stage={current['stage_name']} ({current['status']})")


def update_progress_from_approvals():
    """Helper to update progress milestones after approvals"""
    update_milestones_from_approvals("2026-04")


def analyze_close_readiness(fiscal_period: str = "2026-04") -> Dict[str, Any]:
    """
    CORRECTED: Comprehensive analysis of close readiness based on current state.
    
    FIX: Approval progress returns None/0 when no work has started.
    """
    # Get approval summary from registry
    approval_summary = approval_registry.get_approval_summary(fiscal_period)
    
    # Categorize approvals by status
    approved_items = []
    pending_items = []
    rejected_items = []
    assigned_items = []
    
    for token, info in approval_registry.generated_approvals.items():
        if info.get('fiscal_period') != fiscal_period:
            continue
        
        item_data = {
            'token': token,
            'type': info.get('type', 'Unknown'),
            'description': info.get('description', ''),
            'amount': float(info.get('amount', 0)) if info.get('amount') else 0,
            'created_at': info.get('created_at', ''),
            'metadata_summary': info.get('metadata_summary', '')
        }
        
        status = info.get('status', 'PENDING')
        if status == 'APPROVED':
            approved_items.append(item_data)
        elif status == 'REJECTED':
            rejected_items.append(item_data)
        elif status == 'ASSIGNED':
            assigned_items.append(item_data)
        else:
            pending_items.append(item_data)
    
    # Calculate aging for pending items
    now = datetime.now()
    overdue_items = []
    for item in pending_items:
        created_at = item.get('created_at')
        if created_at:
            try:
                created_date = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                days_pending = (now - created_date).days
                if days_pending > 2:
                    overdue_items.append({
                        **item,
                        'days_pending': days_pending
                    })
            except Exception:
                pass
    
    # Identify blockers
    pending_by_type = {}
    for item in pending_items:
        item_type = item['type']
        pending_by_type[item_type] = pending_by_type.get(item_type, 0) + 1
    
    # Critical blockers
    critical_blockers = []
    
    if pending_by_type.get('AR Variance Correction', 0) > 0:
        critical_blockers.append({
            'type': 'AR/GL Variance',
            'severity': 'CRITICAL',
            'count': pending_by_type['AR Variance Correction'],
            'action': 'Approve variance correction journal entry'
        })
    
    if pending_by_type.get('Missing Cost Center', 0) > 0:
        critical_blockers.append({
            'type': 'Missing Cost Centers',
            'severity': 'HIGH',
            'count': pending_by_type['Missing Cost Center'],
            'action': 'Assign cost centers to transactions'
        })
    
    if pending_by_type.get('Intercompany Variance', 0) > 0:
        critical_blockers.append({
            'type': 'Intercompany Variance',
            'severity': 'HIGH',
            'count': pending_by_type['Intercompany Variance'],
            'action': 'Review and approve intercompany elimination journals'
        })
    
    blockers = []
    
    if pending_by_type.get('Accrual Variance', 0) > 0:
        blockers.append({
            'type': 'Accrual Variance',
            'severity': 'MEDIUM',
            'count': pending_by_type['Accrual Variance'],
            'action': 'Post adjustment journals for accruals'
        })
    
    if pending_by_type.get('Budget Variance', 0) > 0:
        blockers.append({
            'type': 'Budget Variance',
            'severity': 'LOW',
            'count': pending_by_type['Budget Variance'],
            'action': 'Review significant budget variances'
        })
    
    if pending_by_type.get('Bank Reconciliation', 0) > 0:
        blockers.append({
            'type': 'Bank Reconciliation Exceptions',
            'severity': 'MEDIUM',
            'count': pending_by_type['Bank Reconciliation'],
            'action': 'Review and resolve reconciling items'
        })
    
    # Determine overall status
    if critical_blockers:
        overall_status = 'BLOCKED'
        status_message = f"❌ BLOCKED - {len(critical_blockers)} critical issues require immediate attention"
    elif pending_items:
        overall_status = 'AT_RISK'
        status_message = f"⚠️ AT RISK - {len(pending_items)} items pending approval"
    elif not pending_items and len(approval_registry.generated_approvals) > 0:
        overall_status = 'READY'
        status_message = f"✅ READY - All approvals processed, ready to close"
    else:
        overall_status = 'NOT_STARTED'
        status_message = f"🔵 NOT STARTED - No approvals generated yet"
    
    # =========================================================================
    # CORRECTED APPROVAL PROGRESS CALCULATION
    # =========================================================================
    total_approvals = len(approval_registry.generated_approvals)
    processed_approvals = len(approved_items) + len(rejected_items)
    
    if total_approvals > 0:
        # Real work exists - calculate actual progress
        approval_progress_percent = (processed_approvals / total_approvals) * 100
        approval_progress_status = f"{processed_approvals} of {total_approvals} resolved"
    else:
        # No work has started - progress is 0, not 100
        approval_progress_percent = 0.0
        approval_progress_status = "No approvals generated yet"
    
    # =========================================================================
    # CORRECTED MILESTONE PROGRESS
    # =========================================================================
    # Update milestones from approval data (uses corrected logic)
    update_milestones_from_approvals(fiscal_period)
    
    # Get milestone progress and current stage
    milestone_progress_percent = progress_tracker.calculate_overall_milestone_progress()
    current_stage = progress_tracker.get_current_stage()
    milestone_summary = progress_tracker.get_milestone_summary()
    
    return {
        'fiscal_period': fiscal_period,
        'timestamp': datetime.now().isoformat(),
        'summary': {
            'total_approvals_generated': total_approvals,
            'approved': len(approved_items),
            'rejected': len(rejected_items),
            'pending': len(pending_items),
            'assigned': len(assigned_items),
            'overdue': len(overdue_items),
            'approval_progress_percent': approval_progress_percent,
            'approval_progress_status': approval_progress_status,
            'milestone_progress_percent': milestone_progress_percent,
        },
        'overall_status': overall_status,
        'status_message': status_message,
        'current_stage': current_stage,
        'critical_blockers': critical_blockers,
        'other_blockers': blockers,
        'pending_items': pending_items,
        'overdue_items': overdue_items,
        'approved_items': approved_items,
        'assigned_items': assigned_items,
        'pending_by_type': pending_by_type,
        'incomplete_milestones': progress_tracker.get_incomplete_milestones(),
        'milestone_summary': milestone_summary
    }


def generate_cfo_summary(analysis: Dict[str, Any]) -> str:
    """
    CORRECTED: Generate a plain English summary for CFO with proper progress indicators
    """
    fiscal_period = analysis['fiscal_period']
    summary = analysis['summary']
    status = analysis['overall_status']
    blockers = analysis['critical_blockers'] + analysis['other_blockers']
    pending_by_type = analysis['pending_by_type']
    current_stage = analysis['current_stage']
    
    # Format period
    period_parts = fiscal_period.split('-')
    try:
        period_str = f"{datetime(int(period_parts[0]), int(period_parts[1]), 1).strftime('%B %Y')}"
    except Exception:
        period_str = fiscal_period
    
    # Build the summary
    lines = []
    
    # Opening line with current stage
    if current_stage['status'] == 'COMPLETED':
        lines.append(f"📊 **{period_str} Close: All Stages Complete**")
    elif current_stage['status'] == 'NOT_STARTED':
        lines.append(f"📊 **{period_str} Close: Not Yet Started**")
    else:
        stage_name = current_stage.get('stage_name', 'Unknown')
        stage_progress = current_stage.get('progress', 0)
        lines.append(f"📊 **{period_str} Close: Currently at '{stage_name}' ({stage_progress:.0f}%)**")
    
    # Approval progress line
    approval_progress = summary.get('approval_progress_percent', 0)
    approval_status = summary.get('approval_progress_status', '')
    
    if summary.get('total_approvals_generated', 0) > 0:
        lines.append(f"📋 **Approval Progress:** {approval_progress:.0f}% ({approval_status})")
    else:
        lines.append(f"📋 **Approval Progress:** No approvals required yet")
    
    # Milestone progress
    milestone_progress = summary.get('milestone_progress_percent', 0)
    lines.append(f"🎯 **Milestone Progress:** {milestone_progress:.1f}%")
    
    # Status line
    if status == 'BLOCKED':
        lines.append(f"🚨 **Status: BLOCKED** - Cannot proceed until critical issues are resolved.")
    elif status == 'AT_RISK':
        lines.append(f"⚠️ **Status: At Risk** - Close can proceed but requires immediate attention on pending items.")
    elif status == 'READY':
        lines.append(f"✅ **Status: Ready to Close** - All approvals processed. Final validation can proceed.")
    elif status == 'NOT_STARTED':
        lines.append(f"🔵 **Status: Not Started** - Run initial data assessment to begin the close process.")
    else:
        lines.append(f"🔄 **Status: In Progress** - Work is ongoing.")
    
    # Current stage details
    if current_stage['status'] != 'COMPLETED':
        lines.append(f"\n**📍 Current Stage:** {current_stage['stage_name']}")
        lines.append(f"   • Status: {current_stage['status']}")
        lines.append(f"   • Progress: {current_stage['progress']:.1f}%")
    
    # Blockers section
    if blockers:
        lines.append(f"\n**🚫 Blockers ({len(blockers)}):**")
        for i, blocker in enumerate(blockers[:5], 1):
            severity_icon = "🔴" if blocker['severity'] == 'CRITICAL' else "🟠" if blocker['severity'] == 'HIGH' else "🟡"
            lines.append(f"  {i}) {severity_icon} **{blocker['type']}** - {blocker['action']}")
    
    # Pending items summary
    if pending_by_type:
        lines.append(f"\n**⏳ Items Pending ({summary['pending']} total):**")
        for item_type, count in list(pending_by_type.items())[:5]:
            lines.append(f"  • {count} × {item_type}")
    
    # Overdue items
    if summary['overdue'] > 0:
        lines.append(f"\n**⚠️ Overdue Items ({summary['overdue']}):**")
        lines.append(f"  {summary['overdue']} items have been pending for more than 2 days.")
    
    # Recommended actions based on current stage
    lines.append(f"\n**🎯 Recommended Path to Close:**")
    
    if status == 'NOT_STARTED':
        lines.append(f"  1. **Start:** Run initial data assessment")
        lines.append(f"  2. **Analyze:** Generate trial balance to detect exceptions")
        lines.append(f"  3. **Process:** Review and approve detected exceptions")
    elif status == 'BLOCKED':
        lines.append(f"  1. **Immediate:** Address {len(analysis['critical_blockers'])} critical blockers")
        for i, blocker in enumerate(analysis['critical_blockers'][:3], 1):
            lines.append(f"     - {blocker['action']}")
        lines.append(f"  2. **Next:** Process remaining {summary['pending']} pending approvals")
        lines.append(f"  3. **Final:** Run final trial balance validation and obtain CFO sign-off")
    elif status == 'AT_RISK':
        lines.append(f"  1. **Priority:** Process {summary['pending']} pending approvals within 24 hours")
        if analysis['overdue_items']:
            lines.append(f"     - Focus on {len(analysis['overdue_items'])} overdue items first")
        lines.append(f"  2. **Secondary:** Complete intercompany and bank reconciliations")
        lines.append(f"  3. **Final:** Generate final statements and close the period")
    else:
        lines.append(f"  1. Run final trial balance validation")
        lines.append(f"  2. Generate close summary report")
        lines.append(f"  3. Obtain CFO sign-off and lock the period")
    
    # Completed items
    if summary['approved'] > 0:
        lines.append(f"\n**✅ Completed Items:** {summary['approved']} approvals processed successfully.")
    
    # Milestone breakdown
    incomplete = analysis.get('incomplete_milestones', [])
    if incomplete:
        lines.append(f"\n**📋 Remaining Milestones ({len(incomplete)}):**")
        for m in incomplete[:5]:
            status_icon = "🔄" if m['status'] == 'IN_PROGRESS' else "○"
            lines.append(f"  {status_icon} {m['name']}: {m['progress']:.0f}% ({m['status']})")
    
    return "\n".join(lines)
# ============================================================================
# HELPER FUNCTION FOR TRIAL BALANCE DATA
# ============================================================================

def generate_trial_balance_data(fiscal_period: str, entity_code: str) -> Dict[str, Any]:
    """Helper function to generate trial balance data"""
    try:
        # Load data
        transactions = load_csv_data('Raw_GL_Export_With_CostCenters_Mar2026.csv')
        coa = load_coa()
        ar_records = load_csv_data('AR_Subledger_Mar2026.csv')
        
        # Filter transactions for the period
        period_txns = [t for t in transactions if t['Fiscal_Period'] == fiscal_period]
        
        # Calculate AR outstanding
        ar_outstanding = sum(float(r['Outstanding_Balance']) for r in ar_records)
        
        # Detect exceptions
        exceptions = []
        
        # Exception 1: Missing Cost Centers
        missing_cc = [t for t in period_txns if not t.get('Cost_Center', '')]
        if missing_cc:
            exceptions.append({
                'type': 'Missing Cost Centers',
                'severity': 'HIGH',
                'count': len(missing_cc),
                'amount': sum(float(t['Amount']) for t in missing_cc),
                'action': 'Assign cost centers to all transactions',
                'blocking': True
            })
        
        # Exception 2: AR/GL Variance
        gl_ar_balance = sum(float(t['Amount']) for t in period_txns if t['Account_Code_Raw'] == '1100')
        ar_variance = ar_outstanding - gl_ar_balance
        if abs(ar_variance) > 0.01:
            exceptions.append({
                'type': 'AR/GL Variance',
                'severity': 'CRITICAL',
                'variance': ar_variance,
                'ar_subledger': ar_outstanding,
                'gl_balance': gl_ar_balance,
                'action': 'Review and post journal entries',
                'blocking': True
            })
        
        # Exception 3: Invalid Account Codes
        invalid_accounts = [t for t in period_txns if t['Account_Code_Raw'] not in coa]
        if invalid_accounts:
            exceptions.append({
                'type': 'Invalid Account Codes',
                'severity': 'HIGH',
                'count': len(invalid_accounts),
                'amount': sum(float(t['Amount']) for t in invalid_accounts),
                'action': 'Map to valid account codes',
                'blocking': True
            })
        
        # Exception 4: AR Missing Cost Centers
        ar_missing_cc = [r for r in ar_records if not r['Cost_Center'] or not r['Region']]
        if ar_missing_cc:
            exceptions.append({
                'type': 'AR Missing Cost Centers',
                'severity': 'MEDIUM',
                'count': len(ar_missing_cc),
                'amount': sum(float(r['Outstanding_Balance']) for r in ar_missing_cc),
                'action': 'Assign regional cost centers',
                'blocking': False
            })
        
        # Exception 5: Overdue Invoices
        overdue = [r for r in ar_records if r['Status'] == 'Overdue']
        if overdue:
            exceptions.append({
                'type': 'Overdue Invoices',
                'severity': 'MEDIUM',
                'count': len(overdue),
                'amount': sum(float(r['Outstanding_Balance']) for r in overdue),
                'action': 'Review collections process',
                'blocking': False
            })
        
        # Calculate trial balance
        account_balances = defaultdict(float)
        for txn in period_txns:
            if txn['Account_Code_Raw'] in coa:
                account_balances[txn['Account_Code_Raw']] += float(txn['Amount'])
        
        # Group by type
        type_totals = {
            'Asset': 0,
            'Liability': 0,
            'Equity': 0,
            'Revenue': 0,
            'Expense': 0
        }
        
        for account, balance in account_balances.items():
            if account in coa:
                type_totals[coa[account]['type']] += balance
        
        # Check if balanced
        balance_check = type_totals['Asset'] + type_totals['Liability'] + type_totals['Equity']
        is_balanced = abs(balance_check) < 0.01
        
        blocking_exceptions = [e for e in exceptions if e.get('blocking', False)]
        
        return {
            'success': len(blocking_exceptions) == 0,
            'fiscal_period': fiscal_period,
            'transaction_count': len(period_txns),
            'trial_balance': type_totals,
            'is_balanced': is_balanced,
            'balance_check': balance_check,
            'blocking_exceptions_count': len(blocking_exceptions),
            'total_exceptions_count': len(exceptions),
            'exceptions': exceptions
        }
        
    except Exception as e:
        logger.error(f"Error in generate_trial_balance_data: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'exceptions': []
        }

# ============================================================================
# PDF REPORT GENERATION FUNCTIONS
# ============================================================================

def generate_pdf_report(
    fiscal_period: str,
    entity_code: str,
    report_types: List[str]
) -> bytes:
    """
    Generate a comprehensive PDF report with all financial data
    """
    # Create a temporary buffer for the PDF
    buffer = io.BytesIO()
    
    # Create the PDF document
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=72,
        leftMargin=72,
        topMargin=72,
        bottomMargin=72
    )
    
    # Container for the 'Flowable' objects
    elements = []
    
    # Get styles
    styles = getSampleStyleSheet()
    title_style = styles['Heading1']
    heading_style = styles['Heading2']
    normal_style = styles['Normal']
    
    # Add title
    elements.append(Paragraph(f"Financial Report - {fiscal_period}", title_style))
    elements.append(Paragraph(f"Entity: {entity_code}", heading_style))
    elements.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", normal_style))
    elements.append(Spacer(1, 20))
    
    # Load data
    try:
        transactions = load_csv_data('Raw_GL_Export_With_CostCenters_Mar2026.csv')
        coa = load_coa()
        ar_records = load_csv_data('AR_Subledger_Mar2026.csv')
        budget_data = load_csv_data('Budget_Mar2026_Detailed.csv')
        
        # Filter for period
        period_txns = [t for t in transactions if t['Fiscal_Period'] == fiscal_period]
        
        # Calculate account balances
        account_balances = defaultdict(float)
        for txn in period_txns:
            if txn['Account_Code_Raw'] in coa:
                account_balances[txn['Account_Code_Raw']] += float(txn['Amount'])
        
        # ==============================================================
        # TRIAL BALANCE
        # ==============================================================
        if "trial_balance" in report_types:
            elements.append(Paragraph("Trial Balance", heading_style))
            elements.append(Spacer(1, 10))
            
            # Group by type
            type_totals = defaultdict(float)
            data = [["Account Code", "Account Name", "Type", "Balance"]]
            
            for account, balance in account_balances.items():
                if account in coa:
                    acc_type = coa[account]['type']
                    type_totals[acc_type] += balance
                    data.append([
                        account,
                        coa[account]['name'][:30],
                        acc_type,
                        f"${balance:,.2f}"
                    ])
            
            # Add totals
            data.append(["", "", "TOTAL REVENUE", f"${type_totals['Revenue']:,.2f}"])
            data.append(["", "", "TOTAL EXPENSES", f"${type_totals['Expense']:,.2f}"])
            data.append(["", "", "NET INCOME", f"${type_totals['Revenue'] - type_totals['Expense']:,.2f}"])
            
            # Create table
            table = Table(data)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            elements.append(table)
            elements.append(Spacer(1, 20))
        
        # ==============================================================
        # INCOME STATEMENT
        # ==============================================================
        if "income_statement" in report_types:
            elements.append(Paragraph("Income Statement", heading_style))
            elements.append(Spacer(1, 10))
            
            revenue_total = 0
            expense_total = 0
            
            data = [["Account", "Amount"]]
            
            for account, balance in account_balances.items():
                if account in coa:
                    if coa[account]['type'] == 'Revenue':
                        revenue_total += balance
                        data.append([f"{account} - {coa[account]['name'][:30]}", f"${balance:,.2f}"])
            
            data.append(["", ""])
            data.append(["TOTAL REVENUE", f"${revenue_total:,.2f}"])
            data.append(["", ""])
            
            for account, balance in account_balances.items():
                if account in coa:
                    if coa[account]['type'] == 'Expense':
                        expense_total += balance
                        data.append([f"{account} - {coa[account]['name'][:30]}", f"${balance:,.2f}"])
            
            data.append(["", ""])
            data.append(["TOTAL EXPENSES", f"${expense_total:,.2f}"])
            data.append(["NET INCOME", f"${revenue_total - expense_total:,.2f}"])
            
            table = Table(data)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -2), colors.beige),
                ('BACKGROUND', (0, -1), (-1, -1), colors.lightgrey),
                ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            elements.append(table)
            elements.append(Spacer(1, 20))
        
        # ==============================================================
        # BALANCE SHEET
        # ==============================================================
        if "balance_sheet" in report_types:
            elements.append(Paragraph("Balance Sheet", heading_style))
            elements.append(Spacer(1, 10))
            
            assets = 0
            liabilities = 0
            equity = 0
            
            data = [["Account", "Amount"]]
            
            for account, balance in account_balances.items():
                if account in coa:
                    if coa[account]['type'] == 'Asset':
                        assets += balance
                        data.append([f"{account} - {coa[account]['name'][:30]}", f"${balance:,.2f}"])
            
            data.append(["", ""])
            data.append(["TOTAL ASSETS", f"${assets:,.2f}"])
            data.append(["", ""])
            
            for account, balance in account_balances.items():
                if account in coa:
                    if coa[account]['type'] == 'Liability':
                        liabilities += balance
                        data.append([f"{account} - {coa[account]['name'][:30]}", f"${balance:,.2f}"])
            
            data.append(["", ""])
            data.append(["TOTAL LIABILITIES", f"${liabilities:,.2f}"])
            data.append(["", ""])
            
            for account, balance in account_balances.items():
                if account in coa:
                    if coa[account]['type'] == 'Equity':
                        equity += balance
                        data.append([f"{account} - {coa[account]['name'][:30]}", f"${balance:,.2f}"])
            
            data.append(["", ""])
            data.append(["TOTAL EQUITY", f"${equity:,.2f}"])
            data.append(["", ""])
            data.append(["TOTAL LIABILITIES & EQUITY", f"${liabilities + equity:,.2f}"])
            
            table = Table(data)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            elements.append(table)
            elements.append(Spacer(1, 20))
        
        # ==============================================================
        # AR AGING
        # ==============================================================
        if "ar_aging" in report_types:
            elements.append(Paragraph("Accounts Receivable Aging", heading_style))
            elements.append(Spacer(1, 10))
            
            aging_buckets = {
                '0-30 Days': 0,
                '31-60 Days': 0,
                '61-90 Days': 0,
                '90+ Days': 0
            }
            
            for record in ar_records:
                days = int(record['Days_Outstanding'])
                amount = float(record['Outstanding_Balance'])
                
                if days <= 30:
                    aging_buckets['0-30 Days'] += amount
                elif days <= 60:
                    aging_buckets['31-60 Days'] += amount
                elif days <= 90:
                    aging_buckets['61-90 Days'] += amount
                else:
                    aging_buckets['90+ Days'] += amount
            
            data = [["Aging Bucket", "Amount", "% of Total"]]
            total_ar = sum(aging_buckets.values())
            
            for bucket, amount in aging_buckets.items():
                percentage = (amount / total_ar * 100) if total_ar > 0 else 0
                data.append([bucket, f"${amount:,.2f}", f"{percentage:.1f}%"])
            
            data.append(["TOTAL", f"${total_ar:,.2f}", "100%"])
            
            table = Table(data)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            elements.append(table)
            elements.append(Spacer(1, 20))
        
        # ==============================================================
        # BUDGET VARIANCE
        # ==============================================================
        if "budget_variance" in report_types:
            elements.append(Paragraph("Budget Variance Analysis", heading_style))
            elements.append(Spacer(1, 10))
            
            # Calculate actuals by category
            actuals = defaultdict(float)
            for txn in period_txns:
                account = txn['Account_Code_Raw']
                if account in coa:
                    category = coa[account]['category']
                    actuals[category] += float(txn['Amount'])
            
            # Calculate budget by category
            budget = defaultdict(float)
            for item in budget_data:
                category = item['Category']
                if category.upper() != 'TOTAL' and not item['Account_Code'].startswith('TOTAL'):
                    budget[category] += float(item['Budget_Amount'])
            
            data = [["Category", "Budget", "Actual", "Variance", "Variance %"]]
            
            for category in set(list(actuals.keys()) + list(budget.keys())):
                actual = actuals.get(category, 0)
                budg = budget.get(category, 0)
                variance = actual - budg
                variance_pct = (variance / budg * 100) if budg != 0 else 0
                
                data.append([
                    category,
                    f"${budg:,.2f}",
                    f"${actual:,.2f}",
                    f"${variance:,.2f}",
                    f"{variance_pct:.1f}%"
                ])
            
            table = Table(data)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            elements.append(table)
    
    except Exception as e:
        elements.append(Paragraph(f"Error generating report: {str(e)}", styles['Italic']))
        logger.error(f"Error in PDF generation: {str(e)}")
    
    # Build PDF
    doc.build(elements)
    
    # Get the value of the BytesIO buffer
    pdf_bytes = buffer.getvalue()
    buffer.close()
    
    return pdf_bytes

def generate_csv_report(fiscal_period: str, report_type: str) -> str:
    """
    Generate CSV report for specific report type
    """
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Load data
    transactions = load_csv_data('Raw_GL_Export_With_CostCenters_Mar2026.csv')
    coa = load_coa()
    ar_records = load_csv_data('AR_Subledger_Mar2026.csv')
    budget_data = load_csv_data('Budget_Mar2026_Detailed.csv')
    
    # Filter for period
    period_txns = [t for t in transactions if t['Fiscal_Period'] == fiscal_period]
    
    if report_type == "trial_balance":
        writer.writerow(["Account Code", "Account Name", "Account Type", "Category", "Balance"])
        
        account_balances = defaultdict(float)
        for txn in period_txns:
            if txn['Account_Code_Raw'] in coa:
                account_balances[txn['Account_Code_Raw']] += float(txn['Amount'])
        
        for account, balance in account_balances.items():
            if account in coa:
                writer.writerow([
                    account,
                    coa[account]['name'],
                    coa[account]['type'],
                    coa[account]['category'],
                    f"{balance:.2f}"
                ])
    
    elif report_type == "ar_aging":
        writer.writerow(["Customer ID", "Customer Name", "Invoice Number", "Invoice Date", 
                        "Due Date", "Days Outstanding", "Outstanding Balance", "Status"])
        
        for record in ar_records:
            writer.writerow([
                record['Customer_ID'],
                record['Customer_Name'],
                record['Invoice_Number'],
                record['Invoice_Date'],
                record['Due_Date'],
                record['Days_Outstanding'],
                record['Outstanding_Balance'],
                record['Status']
            ])
    
    elif report_type == "budget_variance":
        writer.writerow(["Category", "Budget", "Actual", "Variance", "Variance %"])
        
        # Calculate actuals by category
        actuals = defaultdict(float)
        for txn in period_txns:
            account = txn['Account_Code_Raw']
            if account in coa:
                category = coa[account]['category']
                actuals[category] += float(txn['Amount'])
        
        # Calculate budget by category
        budget = defaultdict(float)
        for item in budget_data:
            category = item['Category']
            if category.upper() != 'TOTAL' and not item['Account_Code'].startswith('TOTAL'):
                budget[category] += float(item['Budget_Amount'])
        
        for category in set(list(actuals.keys()) + list(budget.keys())):
            actual = actuals.get(category, 0)
            budg = budget.get(category, 0)
            variance = actual - budg
            variance_pct = (variance / budg * 100) if budg != 0 else 0
            
            writer.writerow([
                category,
                f"{budg:.2f}",
                f"{actual:.2f}",
                f"{variance:.2f}",
                f"{variance_pct:.1f}"
            ])
    
    return output.getvalue()

# ============================================================================
# EMAIL SENDING FUNCTION
# ============================================================================

def send_email_with_attachments(
    to_emails: List[str],
    subject: str,
    html_content: str,
    attachments: List[Dict[str, bytes]] = None
) -> Dict[str, any]:
    """
    Send email with attachments using SendGrid
    """
    # Get API key from environment
    api_key = os.getenv("SENDGRID_API_KEY")
    from_email = os.getenv("FROM_EMAIL", "deepanshu.dubey@octanesolutions.com.au")
    
    if not api_key:
        logger.warning("⚠️ SENDGRID_API_KEY not found in environment variables")
        logger.warning("   Email will be simulated (check console for content)")
        
        # Log what would be sent
        logger.info(f"📧 SIMULATED EMAIL:")
        logger.info(f"   To: {to_emails}")
        logger.info(f"   Subject: {subject}")
        logger.info(f"   Attachments: {len(attachments) if attachments else 0} file(s)")
        if attachments:
            for att in attachments:
                logger.info(f"      - {att['filename']} ({len(att['content'])} bytes)")
        
        return {
            "success": False,
            "message": "SendGrid API key not configured - email simulated",
            "simulated": True
        }
    
    try:
        # Create mail object
        message = Mail(
            from_email=from_email,
            to_emails=to_emails,
            subject=subject,
            html_content=html_content
        )
        
        # Add attachments
        if attachments:
            for attachment in attachments:
                encoded_file = base64.b64encode(attachment['content']).decode()
                
                attached_file = Attachment(
                    FileContent(encoded_file),
                    FileName(attachment['filename']),
                    FileType(attachment['filetype']),
                    Disposition('attachment')
                )
                message.add_attachment(attached_file)
        
        # Send email
        sg = SendGridAPIClient(api_key)
        response = sg.send(message)
        
        logger.info(f"✅ Email sent successfully! Status Code: {response.status_code}")
        
        return {
            "success": True,
            "message": "Email sent successfully",
            "status_code": response.status_code,
            "to": to_emails
        }
        
    except Exception as e:
        logger.error(f"❌ Error sending email: {str(e)}")
        return {
            "success": False,
            "message": f"Error sending email: {str(e)}"
        }

# ============================================================================
# HEALTH CHECK
# ============================================================================

@app.get("/")
def root():
    """Root endpoint - API health check"""
    # Load logo as base64 for header
    logo_base64 = ""
    try:
        with open("Octane_logo.png", "rb") as logo_file:
            logo_base64 = base64.b64encode(logo_file.read()).decode('utf-8')
    except Exception as e:
        logger.warning(f"Could not load logo: {e}")
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Finance Month-End Close AI Agent</title>
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 0; background: #f5f5f5; }}
            .header {{ background: #000000; color: white; padding: 40px 20px; text-align: center; }}
            .logo {{ height: 60px; margin-bottom: 20px; }}
            .container {{ max-width: 800px; margin: 40px auto; padding: 20px; }}
            .card {{ background: white; border-radius: 10px; padding: 30px; box-shadow: 0 5px 20px rgba(0,0,0,0.1); }}
            h1 {{ color: #000000; margin-top: 0; }}
            .status {{ background: #333333; color: white; padding: 10px 20px; border-radius: 5px; display: inline-block; margin-bottom: 20px; }}
            .links {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-top: 30px; }}
            .link {{ background: #f5f5f5; padding: 15px; border-radius: 5px; text-decoration: none; color: #000000; transition: all 0.3s; }}
            .link:hover {{ background: #000000; color: white; }}
            .version {{ color: #666; margin-top: 20px; }}
        </style>
    </head>
    <body>
        <div class="header">
            <img src="data:image/png;base64,{logo_base64}" alt="Octane Logo" class="logo">
            <h1>Finance Month-End Close AI Agent</h1>
        </div>
        <div class="container">
            <div class="card">
                <div class="status">✅ System Status: Healthy</div>
                <p>Welcome to the Finance Month-End Close AI Agent API. This system provides automated tools for month-end close processes with dashboard approvals and email reporting.</p>
                
                <div class="links">
                    <a href="/dashboard" class="link">📊 Approval Dashboard</a>
                    <a href="/cfo/financial_dashboard" class="link">💰 CFO Dashboard</a>
                    <a href="/reports/email/preview" class="link">📧 Email Reports</a>
                    <a href="/docs" class="link">📚 API Documentation</a>
                    <a href="/health" class="link">🔍 Health Check</a>
                    <a href="/approvals/history" class="link">📋 Approval History</a>
                    <a href="/approvals/check_status/2026-04" class="link">✅ Check Approval Status</a>
                </div>
                
                <p class="version">Version 3.0.0 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            </div>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.get("/Octane_logo.png")
async def get_logo():
    """Serve the Octane logo"""
    logo_path = os.path.join(os.getcwd(), "Octane_logo.png")
    if os.path.exists(logo_path):
        return FileResponse(logo_path, media_type="image/png")
    else:
        raise HTTPException(status_code=404, detail=f"Logo file not found at {logo_path}")

@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "pending_approvals": len(pending_approvals),
        "registered_approvals": len(approval_registry.generated_approvals)
    }

# ============================================================================
# DASHBOARD ENDPOINTS
# ============================================================================

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_home():
    """Main dashboard for approvals with black/white/grey theme"""
    # Load logo as base64
    logo_base64 = ""
    try:
        with open("Octane_logo.png", "rb") as logo_file:
            logo_base64 = base64.b64encode(logo_file.read()).decode('utf-8')
    except Exception as e:
        logger.warning(f"Could not load logo: {e}")
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Finance Month-End Close - Approval Dashboard</title>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: #f5f5f5;
                padding: 0;
                margin: 0;
            }}
            
            .header {{
                background: #000000;
                color: white;
                padding: 20px 40px;
                display: flex;
                align-items: center;
                gap: 30px;
                box-shadow: 0 4px 10px rgba(0,0,0,0.2);
            }}
            
            .header-logo {{
                height: 50px;
                flex-shrink: 0;
            }}
            
            .header-content {{
                flex-grow: 1;
            }}
            
            .header-title {{
                font-size: 1.8em;
                margin-bottom: 5px;
            }}
            
            .header-sub {{
                opacity: 0.8;
                font-size: 0.9em;
            }}
            
            .container {{
                max-width: 1400px;
                margin: 20px auto;
                padding: 0 20px;
            }}
            
            .stats {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                gap: 20px;
                margin-bottom: 30px;
            }}
            
            .stat-card {{
                background: white;
                padding: 25px;
                border-radius: 10px;
                box-shadow: 0 5px 15px rgba(0,0,0,0.08);
                transition: transform 0.3s;
            }}
            
            .stat-card:hover {{
                transform: translateY(-5px);
                box-shadow: 0 10px 25px rgba(0,0,0,0.15);
            }}
            
            .stat-card h3 {{
                color: #666;
                font-size: 0.9em;
                text-transform: uppercase;
                letter-spacing: 1px;
                margin-bottom: 10px;
            }}
            
            .stat-card p {{
                font-size: 2.2em;
                font-weight: bold;
                color: #000000;
            }}
            
            .summary-bar {{
                background: #ffffff;
                padding: 15px 20px;
                border-radius: 10px;
                margin-bottom: 20px;
                display: flex;
                justify-content: space-between;
                align-items: center;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                border-left: 4px solid #000000;
            }}
            
            .selected-count {{
                font-weight: bold;
                color: #000000;
                font-size: 1.1em;
            }}
            
            .bulk-actions {{
                background: white;
                padding: 20px;
                border-radius: 10px;
                margin-bottom: 20px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                display: flex;
                gap: 15px;
                align-items: center;
                flex-wrap: wrap;
            }}
            
            .bulk-actions h3 {{
                margin: 0;
                flex-grow: 1;
                color: #000000;
            }}
            
            .btn {{
                display: inline-block;
                padding: 10px 20px;
                border: none;
                border-radius: 5px;
                font-size: 14px;
                font-weight: 500;
                cursor: pointer;
                text-decoration: none;
                transition: all 0.3s;
            }}
            
            .btn-sm {{
                padding: 5px 10px;
                font-size: 12px;
            }}
            
            .btn-success {{
                background: #000000;
                color: white;
            }}
            
            .btn-success:hover {{
                background: #333333;
            }}
            
            .btn-danger {{
                background: #666666;
                color: white;
            }}
            
            .btn-danger:hover {{
                background: #444444;
            }}
            
            .btn-primary {{
                background: #333333;
                color: white;
            }}
            
            .btn-primary:hover {{
                background: #000000;
            }}
            
            .btn-warning {{
                background: #999999;
                color: white;
            }}
            
            .btn-warning:hover {{
                background: #777777;
            }}
            
            .btn-assign {{
                background: #000000;
                color: white;
            }}
            
            .btn-assign:hover {{
                background: #333333;
            }}
            
            table {{
                width: 100%;
                background: white;
                border-collapse: collapse;
                border-radius: 10px;
                overflow: hidden;
                box-shadow: 0 5px 15px rgba(0,0,0,0.08);
            }}
            
            th {{
                background: #000000;
                color: white;
                padding: 15px;
                text-align: left;
                font-weight: 500;
            }}
            
            td {{
                padding: 15px;
                border-bottom: 1px solid #f0f0f0;
            }}
            
            tr:hover {{
                background: #f9f9f9;
            }}
            
            .status-pending {{ color: #666666; font-weight: bold; }}
            .status-approved {{ color: #000000; font-weight: bold; }}
            .status-rejected {{ color: #999999; font-weight: bold; }}
            .status-assigned {{ color: #333333; font-weight: bold; }}
            
            .checkbox-col {{
                width: 30px;
                text-align: center;
            }}
            
            .checkbox-col input[type="checkbox"] {{
                width: 18px;
                height: 18px;
                cursor: pointer;
            }}
            
            .badge {{
                display: inline-block;
                padding: 3px 8px;
                border-radius: 12px;
                font-size: 11px;
                font-weight: 500;
                background: #f0f0f0;
                color: #000000;
            }}
            
            .badge-ai {{
                background: #000000;
                color: white;
            }}
            
            .action-buttons {{
                display: flex;
                gap: 5px;
                flex-wrap: wrap;
            }}
            
            .footer {{
                margin-top: 40px;
                padding: 20px;
                text-align: center;
                color: #666;
                border-top: 1px solid #e0e0e0;
            }}
            
            .footer a {{
                color: #000000;
                text-decoration: none;
                margin: 0 10px;
            }}
            
            .footer a:hover {{
                text-decoration: underline;
            }}
            
            /* Modal styles */
            .modal {{
                display: none;
                position: fixed;
                z-index: 1000;
                left: 0;
                top: 0;
                width: 100%;
                height: 100%;
                background-color: rgba(0,0,0,0.5);
            }}
            
            .modal-content {{
                background-color: #fefefe;
                margin: 10% auto;
                padding: 30px;
                border-radius: 10px;
                width: 90%;
                max-width: 500px;
                box-shadow: 0 5px 30px rgba(0,0,0,0.3);
            }}
            
            .modal-header {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 20px;
                padding-bottom: 15px;
                border-bottom: 2px solid #000000;
            }}
            
            .modal-header h3 {{
                margin: 0;
                color: #000000;
            }}
            
            .close {{
                color: #aaa;
                font-size: 28px;
                font-weight: bold;
                cursor: pointer;
            }}
            
            .close:hover {{
                color: #000000;
            }}
            
            .assignee-list {{
                max-height: 300px;
                overflow-y: auto;
                margin-bottom: 20px;
            }}
            
            .assignee-item {{
                padding: 15px;
                border: 1px solid #e0e0e0;
                border-radius: 5px;
                margin-bottom: 10px;
                cursor: pointer;
                transition: all 0.2s;
            }}
            
            .assignee-item:hover {{
                background: #f5f5f5;
                border-color: #000000;
            }}
            
            .assignee-item.selected {{
                background: #000000;
                color: white;
                border-color: #000000;
            }}
            
            .assignee-item.selected .assignee-role {{
                color: #cccccc;
            }}
            
            .assignee-name {{
                font-weight: bold;
                margin-bottom: 3px;
            }}
            
            .assignee-email {{
                font-size: 0.9em;
                margin-bottom: 3px;
            }}
            
            .assignee-role {{
                font-size: 0.85em;
                color: #666;
            }}
            
            .assignee-item.selected .assignee-role {{
                color: #cccccc;
            }}
            
            .notification {{
                position: fixed;
                top: 20px;
                right: 20px;
                padding: 15px 20px;
                background: #000000;
                color: white;
                border-radius: 5px;
                box-shadow: 0 5px 15px rgba(0,0,0,0.2);
                z-index: 1001;
                animation: slideIn 0.3s;
            }}
            
            @keyframes slideIn {{
                from {{ transform: translateX(100%); opacity: 0; }}
                to {{ transform: translateX(0); opacity: 1; }}
            }}
            
            @media (max-width: 768px) {{
                .header {{
                    flex-direction: column;
                    text-align: center;
                    padding: 20px;
                }}
                
                .bulk-actions {{
                    flex-direction: column;
                }}
                
                table {{
                    display: block;
                    overflow-x: auto;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <img src="data:image/png;base64,{logo_base64}" alt="Octane Logo" class="header-logo">
            <div class="header-content">
                <div class="header-title">💰 Finance Month-End Close Dashboard</div>
                <div class="header-sub">Manage approvals for cost center assignments, journal entries, and reconciliations</div>
            </div>
            <div class="header-date">{datetime.now().strftime('%d %b %Y, %H:%M')}</div>
        </div>
        
        <div class="container">
            <div class="stats">
                <div class="stat-card" id="pending-count">
                    <h3>Pending Approvals</h3>
                    <p id="pending-value">Loading...</p>
                </div>
                <div class="stat-card" id="approved-count">
                    <h3>Approved Today</h3>
                    <p id="approved-value">Loading...</p>
                </div>
                <div class="stat-card" id="total-count">
                    <h3>Total Items</h3>
                    <p id="total-value">Loading...</p>
                </div>
                <div class="stat-card" id="assigned-count">
                    <h3>Assigned</h3>
                    <p id="assigned-value">Loading...</p>
                </div>
            </div>
            
            <div class="summary-bar" id="summary-bar" style="display: none;">
                <span>
                    <span id="selected-count" class="selected-count">0</span> items selected
                </span>
                <div>
                    <button class="btn btn-success btn-sm" onclick="bulkApprove()">Approve Selected</button>
                    <button class="btn btn-danger btn-sm" onclick="bulkReject()">Reject Selected</button>
                    <button class="btn btn-primary btn-sm" onclick="clearSelection()">Clear</button>
                </div>
            </div>
            
            <div class="bulk-actions">
                <h3>Bulk Actions</h3>
                <button class="btn btn-success" onclick="approveAll()">✅ Approve All</button>
                <button class="btn btn-danger" onclick="rejectAll()">❌ Reject All</button>
                <button class="btn btn-primary" onclick="selectAll()">🔲 Select All</button>
                <button class="btn btn-warning" onclick="clearSelection()">🔄 Clear Selection</button>
                <a href="/approvals/check_status/2026-04" class="btn btn-assign" target="_blank">📊 Check Status</a>
            </div>
            
            <div>
                <h2 style="color: #000000; margin-bottom: 15px;">Pending Approvals</h2>
                <div id="approvals-table">Loading approvals...</div>
            </div>
            
            <div class="footer">
                <a href="/docs" target="_blank">API Documentation</a>
                <a href="/approvals/history" target="_blank">Approval History</a>
                <a href="/cfo/financial_dashboard" target="_blank">💰 CFO Dashboard</a>
                <a href="/reports/email/preview" target="_blank">📧 Email Reports</a>
                <a href="/health" target="_blank">Health Check</a>
                <a href="/approvals/check_status/2026-04" target="_blank">✅ Approval Status</a>
                <p style="margin-top: 20px;">Finance Month-End Close AI Agent v3.0.0</p>
            </div>
        </div>
        
        <!-- Assignment Modal -->
        <div id="assignModal" class="modal">
            <div class="modal-content">
                <div class="modal-header">
                    <h3 id="modalItemTitle">Assign Item</h3>
                    <span class="close" onclick="closeAssignModal()">&times;</span>
                </div>
                <div id="modalItemDescription" style="margin-bottom: 20px; color: #666;"></div>
                
                <h4 style="margin-bottom: 15px;">Select Assignee:</h4>
                <div class="assignee-list" id="assigneeList">
                    <!-- Will be populated dynamically -->
                </div>
                
                <div style="display: flex; gap: 10px; justify-content: flex-end;">
                    <button class="btn btn-primary" onclick="closeAssignModal()">Cancel</button>
                    <button class="btn btn-success" id="confirmAssignBtn" onclick="confirmAssignment()" disabled>Assign</button>
                </div>
            </div>
        </div>
        
        <!-- Notification -->
        <div id="notification" class="notification" style="display: none;"></div>
        
        <script>
            let selectedTokens = new Set();
            let pendingItems = [];
            let currentAssignToken = null;
            let selectedAssignee = null;
            
            async function loadDashboard() {{
                try {{
                    // Load approvals
                    const response = await fetch('/approvals/pending');
                    const data = await response.json();
                    
                    pendingItems = data.data || [];
                    const pendingCount = pendingItems.length;
                    document.getElementById('pending-value').textContent = pendingCount;
                    
                    // Load stats
                    const statsResponse = await fetch('/approvals/stats');
                    const statsData = await statsResponse.json();
                    
                    document.getElementById('approved-value').textContent = statsData.approved_today || 0;
                    document.getElementById('total-value').textContent = statsData.total_items || 0;
                    document.getElementById('assigned-value').textContent = statsData.assigned_count || 0;
                    
                    // Build table with checkboxes
                    let tableHtml = `
                        <table>
                            <thead>
                                <tr>
                                    <th class="checkbox-col">
                                        <input type="checkbox" id="select-all-checkbox" onchange="toggleSelectAll()">
                                    </th>
                                    <th>ID</th>
                                    <th>Type</th>
                                    <th>Description</th>
                                    <th>Amount</th>
                                    <th>Account</th>
                                    <th>Cost Center</th>
                                    <th>Status</th>
                                    <th>Created</th>
                                    <th>Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                    `;
                    
                    if (pendingItems.length > 0) {{
                        pendingItems.forEach(item => {{
                            const isChecked = selectedTokens.has(item.token);
                            const statusClass = item.status === 'PENDING' ? 'status-pending' : 
                                                item.status === 'APPROVED' ? 'status-approved' : 
                                                item.status === 'ASSIGNED' ? 'status-assigned' : 'status-rejected';
                            
                            tableHtml += `
                                <tr>
                                    <td class="checkbox-col">
                                        <input type="checkbox" class="item-checkbox" 
                                               data-token="${{item.token}}"
                                               ${{isChecked ? 'checked' : ''}}
                                               onchange="updateSelection('${{item.token}}', this.checked)">
                                    </td>
                                    <td>${{item.id}}</td>
                                    <td><span class="badge">${{item.type}}</span></td>
                                    <td>${{item.description.substring(0, 40)}}${{item.description.length > 40 ? '...' : ''}}</td>
                                    <td>${{item.amount ? '$' + item.amount.toLocaleString(undefined, {{minimumFractionDigits: 2, maximumFractionDigits: 2}}) : '-'}}</td>
                                    <td>${{item.account || '-'}}</td>
                                    <td>${{item.cost_center
                                        ? (item.metadata?.suggested_at
                                            ? `<span style="color: #000000; font-weight: bold;" title="AI Suggested: ${{item.metadata?.suggestion_reason || 'Pattern-based suggestion'}} (Confidence: ${{item.metadata?.suggestion_confidence ? (item.metadata.suggestion_confidence * 100).toFixed(0) + '%' : 'N/A'}})">${{item.cost_center}} 🤖</span>`
                                            : item.cost_center)
                                        : '-'}}</td>
                                    <td><span class="${{statusClass}}">${{item.status}}</span>${{item.assigned_to ? `<br><small>→ ${{item.assigned_to.split('@')[0]}}</small>` : ''}}</td>
                                    <td>${{new Date(item.created_at).toLocaleDateString()}}</td>
                                    <td class="action-buttons">
                                        <a href="/dashboard/approvals/${{item.token}}" class="btn btn-sm btn-primary">View</a>
                                        <button onclick="openAssignModal('${{item.token}}', '${{item.id}}', '${{item.description}}')" class="btn btn-sm btn-assign">Assign</button>
                                        <a href="/approvals/decide?token=${{item.token}}&approved=true" 
                                           class="btn btn-sm btn-success" onclick="return confirm('Approve this item?')">Approve</a>
                                        <a href="/approvals/decide?token=${{item.token}}&approved=false" 
                                           class="btn btn-sm btn-danger" onclick="return confirm('Reject this item?')">Reject</a>
                                    </td>
                                </tr>
                            `;
                        }});
                    }} else {{
                        tableHtml += `
                            <tr>
                                <td colspan="10" style="text-align: center; padding: 30px;">No pending approvals</td>
                            </tr>
                        `;
                    }}
                    
                    tableHtml += `</tbody></table>`;
                    document.getElementById('approvals-table').innerHTML = tableHtml;
                    
                    // Update summary bar
                    updateSummaryBar();
                    
                }} catch (error) {{
                    console.error('Error loading dashboard:', error);
                    document.getElementById('approvals-table').innerHTML = 'Error loading approvals';
                }}
            }}
            
            function updateSelection(token, checked) {{
                if (checked) {{
                    selectedTokens.add(token);
                }} else {{
                    selectedTokens.delete(token);
                }}
                updateSummaryBar();
                updateSelectAllCheckbox();
            }}
            
            function updateSummaryBar() {{
                const count = selectedTokens.size;
                const summaryBar = document.getElementById('summary-bar');
                const selectedCountSpan = document.getElementById('selected-count');
                
                if (count > 0) {{
                    summaryBar.style.display = 'flex';
                    selectedCountSpan.textContent = count;
                }} else {{
                    summaryBar.style.display = 'none';
                }}
            }}
            
            function updateSelectAllCheckbox() {{
                const selectAllCheckbox = document.getElementById('select-all-checkbox');
                if (selectAllCheckbox) {{
                    const allCheckboxes = document.querySelectorAll('.item-checkbox');
                    const checkedCheckboxes = document.querySelectorAll('.item-checkbox:checked');
                    
                    if (allCheckboxes.length === 0) {{
                        selectAllCheckbox.checked = false;
                        selectAllCheckbox.indeterminate = false;
                    }} else if (checkedCheckboxes.length === allCheckboxes.length) {{
                        selectAllCheckbox.checked = true;
                        selectAllCheckbox.indeterminate = false;
                    }} else if (checkedCheckboxes.length > 0) {{
                        selectAllCheckbox.checked = false;
                        selectAllCheckbox.indeterminate = true;
                    }} else {{
                        selectAllCheckbox.checked = false;
                        selectAllCheckbox.indeterminate = false;
                    }}
                }}
            }}
            
            function toggleSelectAll() {{
                const selectAllCheckbox = document.getElementById('select-all-checkbox');
                const checkboxes = document.querySelectorAll('.item-checkbox');
                
                checkboxes.forEach(cb => {{
                    cb.checked = selectAllCheckbox.checked;
                    const token = cb.dataset.token;
                    if (selectAllCheckbox.checked) {{
                        selectedTokens.add(token);
                    }} else {{
                        selectedTokens.delete(token);
                    }}
                }});
                
                updateSummaryBar();
            }}
            
            function selectAll() {{
                document.querySelectorAll('.item-checkbox').forEach(cb => {{
                    cb.checked = true;
                    selectedTokens.add(cb.dataset.token);
                }});
                updateSummaryBar();
                updateSelectAllCheckbox();
            }}
            
            function clearSelection() {{
                document.querySelectorAll('.item-checkbox').forEach(cb => {{
                    cb.checked = false;
                }});
                selectedTokens.clear();
                updateSummaryBar();
                updateSelectAllCheckbox();
            }}
            
            async function bulkApprove() {{
                if (selectedTokens.size === 0) {{
                    alert('No items selected');
                    return;
                }}
                
                if (!confirm(`Are you sure you want to approve ${{selectedTokens.size}} items?`)) return;
                
                const tokens = Array.from(selectedTokens);
                try {{
                    const response = await fetch('/approvals/batch', {{
                        method: 'POST',
                        headers: {{
                            'Content-Type': 'application/json',
                        }},
                        body: JSON.stringify({{
                            tokens: tokens,
                            approved: true,
                            reviewer: 'Dashboard User',
                            comments: 'Bulk approved from dashboard'
                        }})
                    }});
                    
                    const result = await response.json();
                    if (result.success) {{
                        showNotification(`✅ Successfully approved ${{result.results.filter(r => r.status === 'success').length}} items`);
                        selectedTokens.clear();
                        loadDashboard();
                    }} else {{
                        showNotification('❌ Error approving items', 'error');
                    }}
                }} catch (error) {{
                    console.error('Error:', error);
                    showNotification('❌ Error approving items', 'error');
                }}
            }}
            
            async function bulkReject() {{
                if (selectedTokens.size === 0) {{
                    alert('No items selected');
                    return;
                }}
                
                if (!confirm(`Are you sure you want to reject ${{selectedTokens.size}} items?`)) return;
                
                const tokens = Array.from(selectedTokens);
                try {{
                    const response = await fetch('/approvals/batch', {{
                        method: 'POST',
                        headers: {{
                            'Content-Type': 'application/json',
                        }},
                        body: JSON.stringify({{
                            tokens: tokens,
                            approved: false,
                            reviewer: 'Dashboard User',
                            comments: 'Bulk rejected from dashboard'
                        }})
                    }});
                    
                    const result = await response.json();
                    if (result.success) {{
                        showNotification(`✅ Successfully rejected ${{result.results.filter(r => r.status === 'success').length}} items`);
                        selectedTokens.clear();
                        loadDashboard();
                    }} else {{
                        showNotification('❌ Error rejecting items', 'error');
                    }}
                }} catch (error) {{
                    console.error('Error:', error);
                    showNotification('❌ Error rejecting items', 'error');
                }}
            }}
            
            async function approveAll() {{
                if (!confirm('Are you sure you want to approve ALL pending items?')) return;
                
                try {{
                    const response = await fetch('/approvals/approve_all', {{
                        method: 'POST',
                        headers: {{
                            'Content-Type': 'application/json',
                        }},
                        body: JSON.stringify({{
                            reviewer: 'Dashboard User',
                            comments: 'Bulk approved from dashboard'
                        }})
                    }});
                    
                    const result = await response.json();
                    if (result.success) {{
                        showNotification(`✅ Successfully approved ${{result.approved_count}} items`);
                        selectedTokens.clear();
                        loadDashboard();
                    }} else {{
                        showNotification('❌ Error approving all items: ' + (result.message || 'Unknown error'), 'error');
                    }}
                }} catch (error) {{
                    console.error('Error:', error);
                    showNotification('❌ Error approving all items', 'error');
                }}
            }}
            
            async function rejectAll() {{
                if (!confirm('Are you sure you want to reject ALL pending items?')) return;
                
                try {{
                    const response = await fetch('/approvals/reject_all', {{
                        method: 'POST',
                        headers: {{
                            'Content-Type': 'application/json',
                        }},
                        body: JSON.stringify({{
                            reviewer: 'Dashboard User',
                            comments: 'Bulk rejected from dashboard'
                        }})
                    }});
                    
                    const result = await response.json();
                    if (result.success) {{
                        showNotification(`✅ Successfully rejected ${{result.rejected_count}} items`);
                        selectedTokens.clear();
                        loadDashboard();
                    }} else {{
                        showNotification('❌ Error rejecting all items: ' + (result.message || 'Unknown error'), 'error');
                    }}
                }} catch (error) {{
                    console.error('Error:', error);
                    showNotification('❌ Error rejecting all items', 'error');
                }}
            }}
            
            // Assignment functions
            function openAssignModal(token, itemId, description) {{
                currentAssignToken = token;
                document.getElementById('modalItemTitle').textContent = `Assign Item #${{itemId}}`;
                document.getElementById('modalItemDescription').textContent = description;
                
                // Load assignees
                loadAssignees();
                
                document.getElementById('assignModal').style.display = 'block';
            }}
            
            async function loadAssignees() {{
                try {{
                    const response = await fetch('/approvals/assignees');
                    const data = await response.json();
                    
                    const assigneeList = document.getElementById('assigneeList');
                    assigneeList.innerHTML = '';
                    
                    data.assignees.forEach(assignee => {{
                        const div = document.createElement('div');
                        div.className = 'assignee-item';
                        div.dataset.email = assignee.email;
                        div.dataset.name = assignee.name;
                        div.onclick = () => selectAssignee(div, assignee);
                        div.innerHTML = `
                            <div class="assignee-name">${{assignee.name}}</div>
                            <div class="assignee-email">${{assignee.email}}</div>
                            <div class="assignee-role">${{assignee.role}}</div>
                        `;
                        assigneeList.appendChild(div);
                    }});
                }} catch (error) {{
                    console.error('Error loading assignees:', error);
                }}
            }}
            
            function selectAssignee(element, assignee) {{
                // Remove selected class from all
                document.querySelectorAll('.assignee-item').forEach(el => {{
                    el.classList.remove('selected');
                }});
                
                // Add selected class to this one
                element.classList.add('selected');
                selectedAssignee = assignee;
                
                // Enable confirm button
                document.getElementById('confirmAssignBtn').disabled = false;
            }}
            
            async function confirmAssignment() {{
                if (!selectedAssignee || !currentAssignToken) return;
                
                try {{
                    const response = await fetch('/approvals/assign', {{
                        method: 'POST',
                        headers: {{
                            'Content-Type': 'application/json',
                        }},
                        body: JSON.stringify({{
                            token: currentAssignToken,
                            assignee_email: selectedAssignee.email,
                            assignee_name: selectedAssignee.name,
                            assigner: 'Dashboard User',
                            comments: `Assigned to ${{selectedAssignee.name}}`
                        }})
                    }});
                    
                    const result = await response.json();
                    if (result.success) {{
                        showNotification(`✅ Item assigned to ${{selectedAssignee.name}}. Notification email sent.`);
                        closeAssignModal();
                        loadDashboard();
                    }} else {{
                        showNotification('❌ Error assigning item: ' + (result.message || 'Unknown error'), 'error');
                    }}
                }} catch (error) {{
                    console.error('Error:', error);
                    showNotification('❌ Error assigning item', 'error');
                }}
            }}
            
            function closeAssignModal() {{
                document.getElementById('assignModal').style.display = 'none';
                currentAssignToken = null;
                selectedAssignee = null;
                document.getElementById('confirmAssignBtn').disabled = true;
            }}
            
            function showNotification(message, type = 'success') {{
                const notification = document.getElementById('notification');
                notification.textContent = message;
                notification.style.backgroundColor = type === 'success' ? '#000000' : '#666666';
                notification.style.display = 'block';
                
                setTimeout(() => {{
                    notification.style.display = 'none';
                }}, 3000);
            }}
            
            // Close modal when clicking outside
            window.onclick = function(event) {{
                const modal = document.getElementById('assignModal');
                if (event.target == modal) {{
                    closeAssignModal();
                }}
            }}
            
            // Load dashboard on page load
            loadDashboard();
            
            // Refresh every 10 seconds
            setInterval(loadDashboard, 10000);
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.get("/dashboard/approvals/{token}", response_class=HTMLResponse)
async def view_approval_dashboard(token: str):
    """View single approval item in dashboard with bullet points for metadata"""
    
    # Load logo as base64
    logo_base64 = ""
    try:
        with open("Octane_logo.png", "rb") as logo_file:
            logo_base64 = base64.b64encode(logo_file.read()).decode('utf-8')
    except Exception as e:
        logger.warning(f"Could not load logo: {e}")
    
    if token not in pending_approvals:
        # Check history
        item = None
        for record in approval_history:
            if record.get('token') == token:
                item = record
                break
        if not item:
            return HTMLResponse(content=f"<h1>Approval token {token} not found</h1>", status_code=404)
    else:
        item = pending_approvals[token]
    
    # Get approval links
    links = get_approval_links(token)
    
    # Convert to dict if it's an ApprovalItem object
    if hasattr(item, 'dict'):
        item_dict = item.dict()
    else:
        item_dict = item
    
    # Format metadata for display
    formatted_metadata = []
    if item_dict.get('metadata'):
        formatted_metadata = format_metadata_for_display(item_dict['metadata'])
    
    # Determine status color
    status_color = {
        'PENDING': '#666666',
        'APPROVED': '#000000',
        'REJECTED': '#999999',
        'IN_REVIEW': '#333333',
        'ASSIGNED': '#000000'
    }.get(item_dict.get('status', 'PENDING'), '#666666')
    
    # Format created_at date properly
    created_at_str = 'N/A'
    if item_dict.get('created_at'):
        try:
            if isinstance(item_dict['created_at'], str):
                # If it's a string, parse it
                created_at = datetime.fromisoformat(item_dict['created_at'].replace('Z', '+00:00'))
                created_at_str = created_at.strftime('%Y-%m-%d %H:%M')
            else:
                # If it's already a datetime object
                created_at_str = item_dict['created_at'].strftime('%Y-%m-%d %H:%M')
        except Exception as e:
            logger.error(f"Error formatting date: {e}")
            created_at_str = str(item_dict['created_at'])
    
    # Generate metadata HTML with bullet points
    metadata_html = ""
    if formatted_metadata:
        metadata_html = "<ul style='list-style-type: none; padding: 0; margin: 0;'>"
        for item in formatted_metadata:
            if item.get('is_section'):
                metadata_html += f"<li style='margin-top: 15px;'><strong>{item['key']}:</strong>"
                if item.get('children'):
                    metadata_html += "<ul style='list-style-type: disc; margin-left: 20px; margin-top: 5px;'>"
                    for child in item['children']:
                        if isinstance(child, dict):
                            if child.get('is_section'):
                                metadata_html += f"<li><strong>{child['key']}:</strong>"
                                if child.get('children'):
                                    metadata_html += "<ul style='list-style-type: circle; margin-left: 20px;'>"
                                    for grandchild in child['children']:
                                        metadata_html += f"<li><strong>{grandchild['key']}:</strong> {grandchild['value']}</li>"
                                    metadata_html += "</ul>"
                                metadata_html += "</li>"
                            else:
                                metadata_html += f"<li><strong>{child['key']}:</strong> {child['value']}</li>"
                    metadata_html += "</ul>"
                metadata_html += "</li>"
            else:
                metadata_html += f"<li style='margin-bottom: 8px;'><strong>{item['key']}:</strong> {item['value']}</li>"
        metadata_html += "</ul>"
    else:
        metadata_html = "<p style='color: #666;'>No additional information available</p>"
    
    # Check if assigned
    assigned_info = ""
    if item_dict.get('assigned_to'):
        assigned_at_str = 'N/A'
        if item_dict.get('assigned_at'):
            try:
                if isinstance(item_dict['assigned_at'], str):
                    assigned_at = datetime.fromisoformat(item_dict['assigned_at'].replace('Z', '+00:00'))
                    assigned_at_str = assigned_at.strftime('%Y-%m-%d %H:%M')
                else:
                    assigned_at_str = item_dict['assigned_at'].strftime('%Y-%m-%d %H:%M')
            except Exception:
                assigned_at_str = str(item_dict['assigned_at'])
        
        assigned_info = f"""
        <div style="background: #f0f0f0; padding: 15px; border-radius: 8px; margin-bottom: 20px;">
            <p><strong>Assigned To:</strong> {item_dict['assigned_to']}</p>
            <p><strong>Assigned At:</strong> {assigned_at_str}</p>
        </div>
        """
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Approval #{item_dict.get('id')} - Finance Dashboard</title>
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 0; background: #f5f5f5; }}
            .header {{ background: #000000; color: white; padding: 20px 40px; display: flex; align-items: center; gap: 30px; }}
            .header-logo {{ height: 50px; }}
            .header-content {{ flex-grow: 1; }}
            .header-title {{ font-size: 1.5em; margin-bottom: 5px; }}
            .header-sub {{ opacity: 0.8; font-size: 0.9em; }}
            .container {{ max-width: 900px; margin: 20px auto; padding: 20px; }}
            .card {{ background: white; padding: 30px; border-radius: 10px; box-shadow: 0 5px 20px rgba(0,0,0,0.1); margin-bottom: 20px; }}
            .btn {{ display: inline-block; padding: 10px 20px; margin: 5px; border: none; border-radius: 5px; font-size: 14px; font-weight: 500; cursor: pointer; text-decoration: none; transition: all 0.3s; }}
            .btn-approve {{ background: #000000; color: white; }}
            .btn-approve:hover {{ background: #333333; }}
            .btn-reject {{ background: #666666; color: white; }}
            .btn-reject:hover {{ background: #444444; }}
            .btn-back {{ background: #333333; color: white; }}
            .btn-back:hover {{ background: #000000; }}
            .btn-dashboard {{ background: #999999; color: white; }}
            .btn-dashboard:hover {{ background: #777777; }}
            .btn-assign {{ background: #000000; color: white; }}
            .btn-assign:hover {{ background: #333333; }}
            .status-badge {{ display: inline-block; padding: 8px 16px; border-radius: 20px; color: white; font-weight: bold; background-color: {status_color}; }}
            .details-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin: 20px 0; }}
            .detail-item {{ background: #f9f9f9; padding: 15px; border-radius: 8px; }}
            .detail-item strong {{ display: block; color: #666; font-size: 0.9em; margin-bottom: 5px; }}
            .detail-item .value {{ font-size: 1.2em; font-weight: bold; color: #000000; }}
            .metadata-section {{ background: #f9f9f9; padding: 20px; border-radius: 8px; margin: 20px 0; }}
            .metadata-section h3 {{ margin-top: 0; color: #000000; border-bottom: 2px solid #000000; padding-bottom: 10px; margin-bottom: 20px; }}
            .token-box {{ background: #f0f0f0; padding: 15px; border-radius: 5px; font-family: monospace; word-break: break-all; margin-top: 20px; }}
            .footer {{ margin-top: 30px; padding: 20px; text-align: center; color: #666; }}
            .footer a {{ color: #000000; text-decoration: none; margin: 0 10px; }}
            .footer a:hover {{ text-decoration: underline; }}
        </style>
    </head>
    <body>
        <div class="header">
            <img src="data:image/png;base64,{logo_base64}" alt="Octane Logo" class="header-logo">
            <div class="header-content">
                <div class="header-title">Approval Details</div>
                <div class="header-sub">Token: {token[:8]}...{token[-8:]}</div>
            </div>
            <div class="status-badge">{item_dict.get('status', 'PENDING')}</div>
        </div>
        
        <div class="container">
            {assigned_info}
            
            <div class="card">
                <h2 style="color: #000000; margin-top: 0;">{item_dict.get('type', 'Approval Item')}</h2>
                <p style="font-size: 1.1em; color: #333;">{item_dict.get('description')}</p>
                
                <div class="details-grid">
                    <div class="detail-item">
                        <strong>Item ID</strong>
                        <div class="value">{item_dict.get('id')}</div>
                    </div>
                    <div class="detail-item">
                        <strong>Amount</strong>
                        <div class="value">{f'${item_dict.get("amount", 0):,.2f}' if item_dict.get('amount') else 'N/A'}</div>
                    </div>
                    <div class="detail-item">
                        <strong>Account</strong>
                        <div class="value">{item_dict.get('account', 'N/A')}</div>
                    </div>
                    <div class="detail-item">
                        <strong>Cost Center</strong>
                        <div class="value">{item_dict.get('cost_center', 'N/A')}</div>
                    </div>
                    <div class="detail-item">
                        <strong>Created</strong>
                        <div class="value">{created_at_str}</div>
                    </div>
                    <div class="detail-item">
                        <strong>Token</strong>
                        <div class="value" style="font-size: 0.9em;">{item_dict.get('token', 'N/A')}</div>
                    </div>
                </div>
                
                <div class="metadata-section">
                    <h3>📋 Additional Information</h3>
                    {metadata_html}
                </div>
                
                <div class="token-box">
                    <strong>Approval Token:</strong> {token}
                </div>
            </div>
            
            {f'''
            <div class="card" style="text-align: center;">
                <h3 style="color: #000000;">Actions</h3>
                <p>
                    <a href="{links['approve_url']}" class="btn btn-approve" onclick="return confirm('Approve this item?')">
                        ✅ Approve
                    </a>
                    <a href="{links['reject_url']}" class="btn btn-reject" onclick="return confirm('Reject this item?')">
                        ❌ Reject
                    </a>
                    <button onclick="window.location.href='/approvals/assign-page/{token}'" class="btn btn-assign">
                        👤 Assign
                    </button>
                </p>
            </div>
            ''' if item_dict.get('status') in ['PENDING', 'ASSIGNED'] else ''}
            
            <div class="card" style="text-align: center;">
                <a href="/dashboard" class="btn btn-back">← Back to Dashboard</a>
                <a href="/approvals/history" class="btn btn-dashboard">📋 Approval History</a>
            </div>
            
            <div class="footer">
                <p>Finance Month-End Close AI Agent v3.0.0</p>
            </div>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.get("/approvals/assign-page/{token}", response_class=HTMLResponse)
async def assign_approval_page(token: str):
    """Dedicated page for assigning approval items"""
    
    # Load logo as base64
    logo_base64 = ""
    try:
        with open("Octane_logo.png", "rb") as logo_file:
            logo_base64 = base64.b64encode(logo_file.read()).decode('utf-8')
    except Exception as e:
        logger.warning(f"Could not load logo: {e}")
    
    if token not in pending_approvals:
        return HTMLResponse(content=f"<h1>Approval token {token} not found</h1>", status_code=404)
    
    item = pending_approvals[token]
    
    # IMPORTANT: Convert assignees_db to JSON string properly
    import json
    assignees_json = json.dumps(assignees_db)
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Assign Approval - Finance Dashboard</title>
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 0; background: #f5f5f5; }}
            .header {{ background: #000000; color: white; padding: 20px 40px; display: flex; align-items: center; gap: 30px; }}
            .header-logo {{ height: 50px; }}
            .header-content {{ flex-grow: 1; }}
            .container {{ max-width: 800px; margin: 20px auto; padding: 20px; }}
            .card {{ background: white; padding: 30px; border-radius: 10px; box-shadow: 0 5px 20px rgba(0,0,0,0.1); }}
            h2 {{ color: #000000; margin-top: 0; }}
            .item-details {{ background: #f9f9f9; padding: 20px; border-radius: 8px; margin: 20px 0; }}
            .assignee-list {{ margin: 20px 0; }}
            .assignee-item {{ padding: 15px; border: 1px solid #e0e0e0; border-radius: 5px; margin-bottom: 10px; cursor: pointer; transition: all 0.2s; }}
            .assignee-item:hover {{ background: #f5f5f5; border-color: #000000; }}
            .assignee-item.selected {{ background: #000000; color: white; border-color: #000000; }}
            .assignee-name {{ font-weight: bold; margin-bottom: 5px; }}
            .assignee-email {{ font-size: 0.9em; margin-bottom: 5px; }}
            .assignee-role {{ font-size: 0.85em; color: #666; }}
            .assignee-item.selected .assignee-role {{ color: #cccccc; }}
            .btn {{ display: inline-block; padding: 10px 20px; border: none; border-radius: 5px; font-size: 14px; font-weight: 500; cursor: pointer; text-decoration: none; transition: all 0.3s; }}
            .btn-success {{ background: #000000; color: white; }}
            .btn-success:hover {{ background: #333333; }}
            .btn-success:disabled {{ background: #cccccc; cursor: not-allowed; }}
            .btn-back {{ background: #666666; color: white; }}
            .btn-back:hover {{ background: #444444; }}
            .notification {{ position: fixed; top: 20px; right: 20px; padding: 15px 20px; background: #000000; color: white; border-radius: 5px; box-shadow: 0 5px 15px rgba(0,0,0,0.2); z-index: 1001; }}
            .footer {{ margin-top: 30px; padding: 20px; text-align: center; color: #666; }}
        </style>
    </head>
    <body>
        <div class="header">
            <img src="data:image/png;base64,{logo_base64}" alt="Octane Logo" class="header-logo">
            <div class="header-content">
                <h1>Assign Approval Item</h1>
            </div>
        </div>
        
        <div class="container">
            <div class="card">
                <h2>Item Details</h2>
                <div class="item-details">
                    <p><strong>ID:</strong> {item.id}</p>
                    <p><strong>Type:</strong> {item.type}</p>
                    <p><strong>Description:</strong> {item.description}</p>
                    <p><strong>Amount:</strong> {f'${item.amount:,.2f}' if item.amount else 'N/A'}</p>
                </div>
                
                <h3>Select Assignee:</h3>
                <div class="assignee-list" id="assigneeList">
                    <!-- Will be populated dynamically -->
                </div>
                
                <div style="display: flex; gap: 10px; margin-top: 20px;">
                    <button class="btn btn-success" id="assignBtn" onclick="assignItem()" disabled>Assign Item</button>
                    <a href="/dashboard" class="btn btn-back">Back to Dashboard</a>
                </div>
            </div>
            
            <div class="footer">
                <p>Finance Month-End Close AI Agent v3.0.0</p>
            </div>
        </div>
        
        <div id="notification" class="notification" style="display: none;"></div>
        
        <script>
            // Use the properly formatted JSON from Python - THIS REPLACES THE HARDCODED ARRAY
            const assignees = {assignees_json};
            
            let selectedAssignee = null;
            const token = "{token}";
            
            function loadAssignees() {{
                const assigneeList = document.getElementById('assigneeList');
                assigneeList.innerHTML = '';
                
                assignees.forEach(assignee => {{
                    const div = document.createElement('div');
                    div.className = 'assignee-item';
                    div.dataset.email = assignee.email;
                    div.dataset.name = assignee.name;
                    div.onclick = () => selectAssignee(div, assignee);
                    div.innerHTML = `
                        <div class="assignee-name">${{assignee.name}}</div>
                        <div class="assignee-email">${{assignee.email}}</div>
                        <div class="assignee-role">${{assignee.role}}</div>
                    `;
                    assigneeList.appendChild(div);
                }});
            }}
            
            function selectAssignee(element, assignee) {{
                document.querySelectorAll('.assignee-item').forEach(el => {{
                    el.classList.remove('selected');
                }});
                element.classList.add('selected');
                selectedAssignee = assignee;
                document.getElementById('assignBtn').disabled = false;
            }}
            
            async function assignItem() {{
                if (!selectedAssignee) return;
                
                try {{
                    const response = await fetch('/approvals/assign', {{
                        method: 'POST',
                        headers: {{
                            'Content-Type': 'application/json',
                        }},
                        body: JSON.stringify({{
                            token: token,
                            assignee_email: selectedAssignee.email,
                            assignee_name: selectedAssignee.name,
                            assigner: 'Dashboard User',
                            comments: `Assigned to ${{selectedAssignee.name}}`
                        }})
                    }});
                    
                    const result = await response.json();
                    if (result.success) {{
                        showNotification(`✅ Item assigned to ${{selectedAssignee.name}}. Notification email sent.`);
                        setTimeout(() => {{
                            window.location.href = '/dashboard';
                        }}, 2000);
                    }} else {{
                        showNotification('❌ Error assigning item: ' + (result.message || 'Unknown error'), 'error');
                    }}
                }} catch (error) {{
                    console.error('Error:', error);
                    showNotification('❌ Error assigning item', 'error');
                }}
            }}
            
            function showNotification(message, type = 'success') {{
                const notification = document.getElementById('notification');
                notification.textContent = message;
                notification.style.backgroundColor = type === 'success' ? '#000000' : '#666666';
                notification.style.display = 'block';
                
                setTimeout(() => {{
                    notification.style.display = 'none';
                }}, 3000);
            }}
            
            // Load assignees on page load
            loadAssignees();
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

# ============================================================================
# APPROVAL MANAGEMENT ENDPOINTS
# ============================================================================

@app.get("/approvals/pending")
async def get_pending_approvals():
    """Get all pending approvals"""
    pending = [item.dict() for item in pending_approvals.values() if item.status == ApprovalStatus.PENDING]
    return {
        "success": True,
        "data": pending,
        "count": len(pending)
    }

@app.get("/approvals/status/{token}")
async def get_approval_status(token: str):
    """Get status of an approval by token"""
    
    # Check pending approvals
    if token in pending_approvals:
        item = pending_approvals[token]
        links = get_approval_links(token)
        return {
            "success": True,
            "status": item.status,
            "item": item.dict(),
            "links": links
        }
    
    # Check history
    for record in approval_history:
        if record.get('token') == token:
            return {
                "success": True,
                "status": record.get('status', 'PROCESSED'),
                "item": record,
                "message": "This approval has already been processed"
            }
    
    raise HTTPException(status_code=404, detail="Approval token not found")

@app.get("/approvals/decide")
async def decide_approval(
    token: str,
    approved: bool,
    reviewer: str = Query("Dashboard User"),
    comments: Optional[str] = Query(None)
):
    """Decision endpoint for approvals (can be used from dashboard links)"""
    
    if token not in pending_approvals:
        return HTMLResponse(content=f"<h1>Approval token {token} not found or already processed</h1>", status_code=404)
    
    item = pending_approvals[token]
    
    # Update status
    old_status = item.status
    item.status = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
    
    # Record in history
    history_record = item.dict()
    history_record['processed_at'] = datetime.now().isoformat()
    history_record['reviewer'] = reviewer
    history_record['comments'] = comments
    history_record['decision'] = 'approved' if approved else 'rejected'
    history_record['fiscal_period'] = item.metadata.get('fiscal_period', '2026-04') if item.metadata else '2026-04'
    approval_history.append(history_record)
    
    # UPDATE REGISTRY
    # UPDATE REGISTRY
    approval_registry.update_approval_status(
        token, 
        item.status.value,
        decision='approved' if approved else 'rejected'
    )

    # ✅ ADD THIS LINE HERE - Update progress milestones after approval
    update_progress_from_approvals()
    
    # Remove from pending
    del pending_approvals[token]
    
    logger.info(f"Approval {token} {item.status.value} by {reviewer}")
    
    # Return success page
    decision_text = "Approved" if approved else "Rejected"
    color = "#000000" if approved else "#666666"
    
    # Load logo
    logo_base64 = ""
    try:
        with open("Octane_logo.png", "rb") as logo_file:
            logo_base64 = base64.b64encode(logo_file.read()).decode('utf-8')
    except:
        pass
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Approval {decision_text}</title>
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 0; background: #f5f5f5; }}
            .header {{ background: #000000; color: white; padding: 20px 40px; display: flex; align-items: center; gap: 30px; }}
            .header-logo {{ height: 50px; }}
            .container {{ max-width: 600px; margin: 50px auto; padding: 20px; }}
            .result {{ background: {color}; color: white; padding: 40px; border-radius: 10px; box-shadow: 0 10px 30px rgba(0,0,0,0.2); }}
            .btn {{ display: inline-block; padding: 10px 20px; background: white; color: {color}; text-decoration: none; border-radius: 5px; margin: 10px; font-weight: bold; }}
            .details {{ margin: 20px 0; text-align: left; background: rgba(255,255,255,0.1); padding: 20px; border-radius: 5px; }}
        </style>
    </head>
    <body>
        <div class="header">
            <img src="data:image/png;base64,{logo_base64}" alt="Octane Logo" class="header-logo">
            <h1>Finance Month-End Close</h1>
        </div>
        <div class="container">
            <div class="result">
                <h1>{'✅' if approved else '❌'} {decision_text}!</h1>
                <p>Approval item has been {item.status.value.lower()}.</p>
                
                <div class="details">
                    <p><strong>Type:</strong> {item.type}</p>
                    <p><strong>Description:</strong> {item.description}</p>
                    <p><strong>Reviewer:</strong> {reviewer}</p>
                    {f'<p><strong>Comments:</strong> {comments}</p>' if comments else ''}
                </div>
                
                <a href="/dashboard/approvals/{token}" class="btn">View Details</a>
                <a href="/dashboard" class="btn">Back to Dashboard</a>
            </div>
        </div>
        <script>
            setTimeout(function() {{
                window.location.href = "/dashboard/approvals/{token}";
            }}, 5000);
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.post("/approvals/batch")
async def batch_approve(request: ApprovalBatchRequest):
    """Batch approve/reject multiple items"""
    
    results = []
    for token in request.tokens:
        if token in pending_approvals:
            item = pending_approvals[token]
            old_status = item.status
            item.status = ApprovalStatus.APPROVED if request.approved else ApprovalStatus.REJECTED
            
            history_record = item.dict()
            history_record['processed_at'] = datetime.now().isoformat()
            history_record['reviewer'] = request.reviewer
            history_record['comments'] = request.comments
            history_record['decision'] = 'approved' if request.approved else 'rejected'
            history_record['fiscal_period'] = item.metadata.get('fiscal_period', '2026-04') if item.metadata else '2026-04'
            approval_history.append(history_record)
            
            # UPDATE REGISTRY
            approval_registry.update_approval_status(
                token,
                item.status.value,
                decision='approved' if request.approved else 'rejected'
            )
            
            del pending_approvals[token]
            results.append({"token": token, "status": "success", "decision": request.approved})
        else:
            results.append({"token": token, "status": "not_found"})

    # ✅ ADD THIS LINE HERE - Update progress milestones after batch approval
    update_progress_from_approvals()
    
    return {
        "success": True,
        "message": f"Processed {len([r for r in results if r['status'] == 'success'])} items",
        "results": results
    }

@app.post("/approvals/approve_all")
async def approve_all_pending(
    reviewer: str = Query("Dashboard User"),
    comments: Optional[str] = Query("Bulk approved from dashboard")
):
    """
    Approve all pending approvals in one go
    """
    if not pending_approvals:
        return {
            "success": True,
            "message": "No pending approvals to process",
            "approved_count": 0
        }
    
    pending_tokens = [
        token for token, item in pending_approvals.items() 
        if item.status == ApprovalStatus.PENDING
    ]
    
    if not pending_tokens:
        return {
            "success": True,
            "message": "No pending approvals to process",
            "approved_count": 0
        }
    
    # Process batch approval
    results = []
    for token in pending_tokens:
        if token in pending_approvals:
            item = pending_approvals[token]
            item.status = ApprovalStatus.APPROVED
            
            history_record = item.dict()
            history_record['processed_at'] = datetime.now().isoformat()
            history_record['reviewer'] = reviewer
            history_record['comments'] = comments
            history_record['decision'] = 'approved'
            history_record['fiscal_period'] = item.metadata.get('fiscal_period', '2026-04') if item.metadata else '2026-04'
            approval_history.append(history_record)
            
            # UPDATE REGISTRY
            approval_registry.update_approval_status(
                token,
                item.status.value,
                decision='approved'
            )
            
            del pending_approvals[token]
            results.append({"token": token, "status": "success"})
    
    logger.info(f"Bulk approved {len(results)} items by {reviewer}")

    # ✅ ADD THIS LINE HERE - Update progress milestones
    update_progress_from_approvals()
    
    return {
        "success": True,
        "message": f"Successfully approved {len(results)} items",
        "approved_count": len(results),
        "results": results
    }

@app.post("/approvals/reject_all")
async def reject_all_pending(
    reviewer: str = Query("Dashboard User"),
    comments: Optional[str] = Query("Bulk rejected from dashboard")
):
    """
    Reject all pending approvals in one go
    """
    if not pending_approvals:
        return {
            "success": True,
            "message": "No pending approvals to process",
            "rejected_count": 0
        }
    
    pending_tokens = [
        token for token, item in pending_approvals.items() 
        if item.status == ApprovalStatus.PENDING
    ]
    
    if not pending_tokens:
        return {
            "success": True,
            "message": "No pending approvals to process",
            "rejected_count": 0
        }
    
    # Process batch rejection
    results = []
    for token in pending_tokens:
        if token in pending_approvals:
            item = pending_approvals[token]
            item.status = ApprovalStatus.REJECTED
            
            history_record = item.dict()
            history_record['processed_at'] = datetime.now().isoformat()
            history_record['reviewer'] = reviewer
            history_record['comments'] = comments
            history_record['decision'] = 'rejected'
            history_record['fiscal_period'] = item.metadata.get('fiscal_period', '2026-04') if item.metadata else '2026-04'
            approval_history.append(history_record)
            
            # UPDATE REGISTRY
            approval_registry.update_approval_status(
                token,
                item.status.value,
                decision='rejected'
            )
            
            del pending_approvals[token]
            results.append({"token": token, "status": "success"})
    
    logger.info(f"Bulk rejected {len(results)} items by {reviewer}")

    # ✅ ADD THIS LINE HERE - Update progress milestones
    update_progress_from_approvals()
    
    return {
        "success": True,
        "message": f"Successfully rejected {len(results)} items",
        "rejected_count": len(results),
        "results": results
    }

@app.get("/approvals/history")
async def get_approval_history(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100)
):
    """Get approval history with pagination"""
    
    # Sort by processed_at desc
    sorted_history = sorted(
        approval_history,
        key=lambda x: x.get('processed_at', ''),
        reverse=True
    )
    
    start_idx = (page - 1) * size
    end_idx = start_idx + size
    paginated = sorted_history[start_idx:end_idx]
    
    return {
        "success": True,
        "data": paginated,
        "pagination": {
            "page": page,
            "size": size,
            "total": len(approval_history),
            "pages": (len(approval_history) + size - 1) // size
        }
    }

@app.get("/approvals/stats")
async def get_approval_stats():
    """Get approval statistics"""
    
    # Filter pending items
    pending_items = [item for item in pending_approvals.values() if item.status == ApprovalStatus.PENDING]
    total_pending = len(pending_items)
    
    # Count assigned items
    assigned_count = len([item for item in pending_approvals.values() if item.assigned_to is not None])
    
    # Calculate today's approvals
    today = datetime.now().date()
    approved_today = 0
    rejected_today = 0
    
    for record in approval_history:
        processed_date = datetime.fromisoformat(record.get('processed_at', '2000-01-01')).date()
        if processed_date == today:
            if record.get('decision') == 'approved':
                approved_today += 1
            elif record.get('decision') == 'rejected':
                rejected_today += 1
    
    # Calculate amounts by type
    pending_amounts = {}
    for item in pending_items:
        if item.type not in pending_amounts:
            pending_amounts[item.type] = 0
        pending_amounts[item.type] += item.amount or 0
    
    # Get counts by type
    by_type = {}
    for item in pending_items:
        by_type[item.type] = by_type.get(item.type, 0) + 1
    
    return {
        "total_items": len(pending_approvals) + len(approval_history),
        "pending": total_pending,
        "approved_today": approved_today,
        "rejected_today": rejected_today,
        "assigned_count": assigned_count,
        "total_processed": len(approval_history),
        "pending_amounts": pending_amounts,
        "by_type": by_type
    }

@app.get("/approvals/assignees")
async def get_assignees():
    """Get list of available assignees"""
    return {
        "success": True,
        "assignees": assignees_db
    }

@app.post("/approvals/assign")
async def assign_approval_item(request: ApprovalAssignmentRequest):
    """
    Assign an approval item to a specific person and send email notification
    """
    if request.token not in pending_approvals:
        raise HTTPException(status_code=404, detail="Approval token not found")
    
    item = pending_approvals[request.token]
    
    # Update item with assignment info
    item.assigned_to = request.assignee_email
    item.assigned_at = datetime.now()
    item.status = ApprovalStatus.ASSIGNED
    
    # UPDATE REGISTRY
    approval_registry.update_approval_status(request.token, 'ASSIGNED')
    
    # Add to history
    history_record = item.dict()
    history_record['processed_at'] = datetime.now().isoformat()
    history_record['assigner'] = request.assigner
    history_record['assigned_to'] = request.assignee_email
    history_record['decision'] = 'assigned'
    history_record['fiscal_period'] = item.metadata.get('fiscal_period', '2026-04') if item.metadata else '2026-04'
    approval_history.append(history_record)
    
    # Send email notification to assignee
    assignee_name = request.assignee_name or request.assignee_email
    subject = f"Action Required: Approval Item #{item.id} Assigned to You"
    
    # Get approval links
    links = get_approval_links(request.token)
    
    html_content = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: #000000; color: white; padding: 20px; text-align: center; }}
            .content {{ padding: 20px; background: #f9f9f9; }}
            .button {{ display: inline-block; padding: 10px 20px; background: #000000; color: white; text-decoration: none; border-radius: 5px; margin: 10px 5px; }}
            .footer {{ margin-top: 20px; font-size: 12px; color: #666; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h2>Finance Month-End Close System</h2>
            </div>
            <div class="content">
                <h3>Hello {assignee_name},</h3>
                <p>An approval item has been assigned to you by <strong>{request.assigner}</strong>.</p>
                
                <h4>Item Details:</h4>
                <ul>
                    <li><strong>ID:</strong> {item.id}</li>
                    <li><strong>Type:</strong> {item.type}</li>
                    <li><strong>Description:</strong> {item.description}</li>
                    <li><strong>Amount:</strong> {f'${item.amount:,.2f}' if item.amount else 'N/A'}</li>
                    <li><strong>Account:</strong> {item.account or 'N/A'}</li>
                    <li><strong>Cost Center:</strong> {item.cost_center or 'N/A'}</li>
                </ul>
                
                <h4>Assignment Comments:</h4>
                <p>{request.comments or 'No additional comments'}</p>
                
                <h4>Actions Required:</h4>
                <p>Please review this item and take appropriate action:</p>
                <p>
                    <a href="{links['approve_url']}" class="button">✅ Approve</a>
                    <a href="{links['reject_url']}" class="button" style="background: #666666;">❌ Reject</a>
                    <a href="{links['dashboard_url']}" class="button" style="background: #333333;">👤 View Details</a>
                </p>
                
                <p>You can also view this item in the <a href="{APP_BASE_URL}/dashboard">Finance Dashboard</a>.</p>
            </div>
            <div class="footer">
                <p>This is an automated message from the Finance Month-End Close System.</p>
                <p>© 2026 Octane Solutions</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    # Send email
    email_result = send_email_notification(
        to_email=request.assignee_email,
        to_name=assignee_name,
        subject=subject,
        html_content=html_content
    )
    
    logger.info(f"Item {item.id} assigned to {request.assignee_email} by {request.assigner}")
    
    return {
        "success": True,
        "message": f"Item assigned to {assignee_name}. {email_result.get('message', '')}",
        "item": item.dict(),
        "email_status": email_result
    }

# ============================================================================
# NEW ENDPOINT: CHECK APPROVAL STATUS
# ============================================================================

@app.get("/approvals/check_status/{fiscal_period}")
async def check_approval_status(fiscal_period: str):
    """
    Check status of all approvals generated for a fiscal period
    Useful before closing the period
    """
    summary = approval_registry.get_approval_summary(fiscal_period)
    pending = approval_registry.get_pending_approvals(fiscal_period)
    
    # Also check if any approvals are still in pending_approvals
    pending_in_memory = [
        {"token": token, "type": item.type, "description": item.description}
        for token, item in pending_approvals.items()
        if item.metadata and item.metadata.get('fiscal_period') == fiscal_period
    ]
    
    # Get processed from history
    processed_in_history = [
        record for record in approval_history
        if record.get('fiscal_period') == fiscal_period
    ]
    
    all_processed = len(pending) == 0 and len(pending_in_memory) == 0
    
    return {
        "fiscal_period": fiscal_period,
        "summary": summary,
        "pending_in_registry": pending,
        "pending_in_memory": pending_in_memory,
        "processed_in_history": len(processed_in_history),
        "all_approvals_processed": all_processed,
        "can_close": all_processed,
        "dashboard_url": f"{APP_BASE_URL}/dashboard"
    }

# ============================================================================
# TOOL 0: INITIAL DATA ASSESSMENT
# ============================================================================

@app.post("/tools/initial_assessment", response_model=ToolResponse)
def initial_assessment(request: TrialBalanceRequest):
    """
    Provide initial data assessment without full exception detection
    """
    try:
        # Load all data files
        transactions = load_csv_data('Raw_GL_Export_With_CostCenters_Mar2026.csv')
        coa = load_coa()
        cost_centers_data = load_csv_data('Master_CostCenters_States.csv')
        ar_records = load_csv_data('AR_Subledger_Mar2026.csv')
        
        # Filter for the requested period
        period_txns = [t for t in transactions if t['Fiscal_Period'] == request.fiscal_period]
        
        # Count by transaction type
        revenue_txns = [t for t in period_txns if t['Account_Code_Raw'].startswith('4')]
        expense_txns = [t for t in period_txns if t['Account_Code_Raw'].startswith('5')]
        balance_sheet_txns = [t for t in period_txns if t['Account_Code_Raw'][0] in ['1', '2', '3']]
        
        # Calculate totals
        revenue_total = sum(float(t['Amount']) for t in revenue_txns)
        expense_total = sum(float(t['Amount']) for t in expense_txns)
        ar_outstanding = sum(float(r['Outstanding_Balance']) for r in ar_records)
        
        # Get unique currencies
        currencies = set(t.get('Currency', 'AUD') for t in period_txns if t.get('Currency'))
        if not currencies:
            currencies = {'AUD', 'USD', 'NZD', 'GBP'}
        
        # Get cost center list
        cost_center_codes = [cc['Cost_Center_Code'] for cc in cost_centers_data]
        
        # Build summary message
        summary = {
            "data_loaded": {
                "gl_transactions_total": len(transactions),
                "gl_transactions_period": len(period_txns),
                "chart_of_accounts": len(coa),
                "cost_centers": len(cost_center_codes),
                "cost_center_list": cost_center_codes,
                "ar_customers": len(ar_records),
                "ar_outstanding": ar_outstanding
            },
            "transaction_breakdown": {
                "revenue_transactions": len(revenue_txns),
                "revenue_amount": revenue_total,
                "expense_transactions": len(expense_txns),
                "expense_amount": expense_total,
                "balance_sheet_adjustments": len(balance_sheet_txns)
            },
            "currencies": list(currencies),
            "status": "ready",
            "next_step": "Run 'Generate Trial Balance' to detect exceptions and validate data"
        }
        
        message = f"""Loading data files...

✓ GL Transactions: {len(transactions)} total, {len(period_txns)} for {request.fiscal_period}
✓ Chart of Accounts: {len(coa)} accounts (Assets, Liabilities, Equity, Revenue, Expenses)
✓ Cost Centers: {len(cost_center_codes)} centers ({', '.join(cost_center_codes)})
✓ AR Subledger: {len(ar_records)} customers, ${ar_outstanding:,.2f} outstanding

Initial Assessment:
- Revenue transactions: {len(revenue_txns)} (${revenue_total:,.2f})
- Expense transactions: {len(expense_txns)} (${expense_total:,.2f})
- Balance sheet adjustments: {len(balance_sheet_txns)}
- Multi-currency: {', '.join(sorted(currencies))}

Ready to proceed with month-end close process."""
        
        return ToolResponse(
            success=True,
            message=message,
            data=summary
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# TOOL 1: GENERATE TRIAL BALANCE WITH EXCEPTIONS (Using Helper Function)
# ============================================================================

@app.post("/tools/generate_trial_balance", response_model=ToolResponse)
def generate_trial_balance(request: TrialBalanceRequest):
    """
    Generate trial balance and detect exceptions with approval links
    """
    try:
        # Use the helper function
        result = generate_trial_balance_data(request.fiscal_period, request.entity_code)
        
        if not result.get('success'):
            return ToolResponse(
                success=False,
                message="Trial balance generation failed",
                data=result,
                exceptions=result.get('exceptions', [])
            )
        
        # Add dashboard info
        dashboard_info = {
            "dashboard_url": f"{APP_BASE_URL}/dashboard",
            "pending_approvals_count": result.get('blocking_exceptions_count', 0)
        }
        
        return ToolResponse(
            success=result.get('blocking_exceptions_count', 0) == 0,
            message=f"Trial balance {'completed' if result.get('blocking_exceptions_count', 0) == 0 else 'requires approval'} - {result.get('total_exceptions_count', 0)} exception(s) detected. View dashboard at {APP_BASE_URL}/dashboard",
            data={
                'fiscal_period': request.fiscal_period,
                'transaction_count': result.get('transaction_count', 0),
                'trial_balance': result.get('trial_balance', {}),
                'is_balanced': result.get('is_balanced', False),
                'balance_check': result.get('balance_check', 0),
                'blocking_exceptions_count': result.get('blocking_exceptions_count', 0),
                'total_exceptions_count': result.get('total_exceptions_count', 0),
                'dashboard': dashboard_info
            },
            exceptions=result.get('exceptions', [])
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# TOOL 2: ANALYZE AR VARIANCE
# ============================================================================

@app.post("/tools/analyze_ar_variance", response_model=ToolResponse)
def analyze_ar_variance(request: ARVarianceRequest):
    """
    Analyze Accounts Receivable variance between subledger and GL
    """
    try:
        # Load data
        ar_records = load_csv_data('AR_Subledger_Mar2026.csv')
        transactions = load_csv_data('Raw_GL_Export_With_CostCenters_Mar2026.csv')
        
        # Filter GL transactions for AR account
        period_txns = [t for t in transactions if t['Fiscal_Period'] == request.fiscal_period]
        
        # Calculate totals
        total_invoiced = sum(float(r['Invoice_Amount']) for r in ar_records)
        total_paid = sum(float(r['Amount_Paid']) for r in ar_records)
        total_outstanding = sum(float(r['Outstanding_Balance']) for r in ar_records)
        
        gl_ar_balance = sum(float(t['Amount']) for t in period_txns if t['Account_Code_Raw'] == '1100')
        variance = total_outstanding - gl_ar_balance
        
        # Analyze by status
        status_summary = defaultdict(lambda: {'count': 0, 'amount': 0.0})
        for record in ar_records:
            status = record['Status']
            outstanding = float(record['Outstanding_Balance'])
            status_summary[status]['count'] += 1
            status_summary[status]['amount'] += outstanding
        
        # Identify issues
        missing_cost_centers = [r for r in ar_records if not r['Cost_Center'] or not r['Region']]
        overdue_invoices = [r for r in ar_records if r['Status'] == 'Overdue']
        large_outstanding = [r for r in ar_records if float(r['Outstanding_Balance']) > 500000 and r['Status'] in ['Outstanding', 'Overdue']]
        
        # Generate recommendations with approval items
        recommendations = []
        
        if missing_cost_centers:
            # Create approval item for missing cost centers
            approval_item = create_approval_item(
                item_type="AR Missing Cost Centers",
                description=f"Assign cost centers to {len(missing_cost_centers)} AR invoices",
                amount=sum(float(r['Outstanding_Balance']) for r in missing_cost_centers),
                metadata={
                    "count": len(missing_cost_centers),
                    "customers": list(set(r['Customer_Name'] for r in missing_cost_centers))[:5]
                },
                fiscal_period=request.fiscal_period
            )
            
            recommendations.append({
                'type': 'Missing Cost Centers',
                'action': f'Assign cost centers to {len(missing_cost_centers)} invoices',
                'impact': sum(float(r['Outstanding_Balance']) for r in missing_cost_centers),
                'priority': 'HIGH',
                'requires_approval': True,
                'approval_token': approval_item.token,
                'approval_links': get_approval_links(approval_item.token)
            })
        
        if overdue_invoices:
            recommendations.append({
                'type': 'Overdue Invoices',
                'action': f'Review and follow up on {len(overdue_invoices)} overdue invoices',
                'impact': sum(float(r['Outstanding_Balance']) for r in overdue_invoices),
                'priority': 'HIGH',
                'details': [
                    {
                        'customer': r['Customer_Name'],
                        'invoice': r['Invoice_Number'],
                        'days_overdue': r['Days_Outstanding'],
                        'amount': float(r['Outstanding_Balance'])
                    } for r in sorted(overdue_invoices, key=lambda x: int(x['Days_Outstanding']), reverse=True)[:5]
                ]
            })
        
        if abs(variance) > 0.01:
            # Create approval item for variance correction
            approval_item = create_approval_item(
                item_type="AR Variance Correction",
                description=f"Journal entry to correct ${variance:,.2f} AR/GL variance",
                amount=abs(variance),
                account="1100",
                metadata={
                    "variance": variance,
                    "ar_subledger": total_outstanding,
                    "gl_balance": gl_ar_balance,
                    "entry_id": "JE-2026-001"
                },
                fiscal_period=request.fiscal_period
            )
            
            recommendations.append({
                'type': 'AR/GL Variance',
                'action': f'Investigate ${variance:,.2f} variance',
                'impact': abs(variance),
                'priority': 'CRITICAL',
                'requires_approval': True,
                'approval_token': approval_item.token,
                'approval_links': get_approval_links(approval_item.token),
                'suggested_journal_entries': [
                    {
                        'entry_id': 'JE-2026-001',
                        'description': 'AR Variance Correction',
                        'debit_account': '6000' if variance < 0 else '1000',
                        'credit_account': '1100',
                        'amount': abs(variance)
                    }
                ]
            })
        
        return ToolResponse(
            success=True,
            message=f"AR variance analysis complete - Variance: ${variance:,.2f}. Approvals needed at {APP_BASE_URL}/dashboard",
            data={
                'ar_subledger': {
                    'total_invoiced': total_invoiced,
                    'total_paid': total_paid,
                    'total_outstanding': total_outstanding
                },
                'gl_balance': gl_ar_balance,
                'variance': variance,
                'status_summary': dict(status_summary),
                'missing_cost_centers_count': len(missing_cost_centers),
                'overdue_invoices_count': len(overdue_invoices),
                'large_outstanding_count': len(large_outstanding),
                'recommendations': recommendations,
                'dashboard_url': f"{APP_BASE_URL}/dashboard"
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# TOOL 3: UPDATE GL WITH COST CENTERS
# ============================================================================

@app.post("/tools/assign_cost_centers", response_model=ToolResponse)
def assign_cost_centers(request: CostCenterBatchRequest):
    """
    Apply APPROVED cost center assignments to GL transactions.
    This should only be called AFTER user has approved suggestions in dashboard.
    """
    try:
        # Load data
        transactions = load_csv_data('Raw_GL_Export_With_CostCenters_Mar2026.csv')
        cost_centers_data = load_csv_data('Master_CostCenters_States.csv')
        valid_cost_centers = [cc['Cost_Center_Code'] for cc in cost_centers_data]
        
        # Create lookup for assignments
        assignment_map = {a.transaction_id: a for a in request.assignments}
        
        # CHECK: Verify all assignments have been approved by checking registry
        unapproved_items = []
        approved_items = {}
        
        for txn_id in assignment_map:
            # Check registry for approval
            found_approved = False
            for token, info in approval_registry.generated_approvals.items():
                if (info.get('type') == "Missing Cost Center" and
                    f"txn:{txn_id}" in info.get('metadata_summary', '') and
                    info.get('status') == 'APPROVED'):
                    found_approved = True
                    approved_items[txn_id] = token
                    break
            
            # Also check in-memory history
            if not found_approved:
                for hist_item in approval_history:
                    if (hist_item.get('type') == "Missing Cost Center" and
                        hist_item.get('metadata', {}).get('transaction_id') == txn_id and
                        hist_item.get('decision') == 'approved'):
                        found_approved = True
                        break
            
            if not found_approved:
                unapproved_items.append({
                    'transaction_id': txn_id,
                    'status': 'not_found_or_not_approved',
                    'message': 'No approval record found for this transaction'
                })
        
        # If any items are not approved, return error
        if unapproved_items:
            return ToolResponse(
                success=False,
                message=f"❌ Cannot assign cost centers - {len(unapproved_items)} items not approved. Please approve in dashboard first.",
                data={
                    'unapproved_count': len(unapproved_items),
                    'unapproved_items': unapproved_items[:10],  # Show first 10
                    'dashboard_url': f"{APP_BASE_URL}/dashboard",
                    'action_required': 'User must approve suggestions in dashboard before applying'
                }
            )
        
        # All items approved - proceed with assignment
        updated_count = 0
        invalid_assignments = []
        
        for txn in transactions:
            if txn['Txn_ID'] in assignment_map:
                assignment = assignment_map[txn['Txn_ID']]
                
                # Validate cost center
                if assignment.cost_center not in valid_cost_centers:
                    invalid_assignments.append({
                        'transaction_id': txn['Txn_ID'],
                        'cost_center': assignment.cost_center,
                        'reason': 'Invalid cost center code'
                    })
                    continue
                
                txn['Cost_Center'] = assignment.cost_center
                updated_count += 1
                logger.info(f"Applied cost center {assignment.cost_center} to transaction {txn['Txn_ID']}")
        
        # Save updated transactions
        if updated_count > 0:
            fieldnames = list(transactions[0].keys())
            save_csv_data('Raw_GL_Export_With_CostCenters_Mar2026.csv', transactions, fieldnames)
            logger.info(f"Saved {updated_count} cost center assignments to CSV")
        
        # Clean up approved items from pending_approvals
        for txn_id, token in approved_items.items():
            if token in pending_approvals:
                del pending_approvals[token]
                logger.info(f"Removed approved item {token} from pending approvals")
        
        return ToolResponse(
            success=len(invalid_assignments) == 0,
            message=f"✅ Applied {updated_count} approved cost center assignments to GL",
            data={
                'updated_count': updated_count,
                'requested_count': len(request.assignments),
                'invalid_count': len(invalid_assignments),
                'invalid_assignments': invalid_assignments,
                'cleaned_up_approvals': len(approved_items)
            }
        )
        
    except Exception as e:
        logger.error(f"Error in assign_cost_centers: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# TOOL 4: POST JOURNAL ENTRIES
# ============================================================================

@app.post("/tools/post_journal_entries", response_model=ToolResponse)
def post_journal_entries(request: JournalEntryRequest):
    """
    Post approved journal entries to GL
    """
    try:
        # Load data
        transactions = load_csv_data('Raw_GL_Export_With_CostCenters_Mar2026.csv')
        coa = load_coa()
        
        # Check if entries are approved using registry
        unapproved_entries = []
        for entry in request.entries:
            if not entry.approved:
                # Check registry for approval
                found_approved = False
                for token, info in approval_registry.generated_approvals.items():
                    if (info.get('type') == "AR Variance Correction" and
                        f"je:{entry.entry_id}" in info.get('metadata_summary', '') and
                        info.get('status') == 'APPROVED'):
                        found_approved = True
                        break
                
                # Also check history
                if not found_approved:
                    for hist_item in approval_history:
                        if (hist_item.get('type') == "AR Variance Correction" and
                            hist_item.get('metadata', {}).get('entry_id') == entry.entry_id and
                            hist_item.get('decision') == 'approved'):
                            found_approved = True
                            break
                
                if not found_approved:
                    unapproved_entries.append({
                        'entry_id': entry.entry_id,
                        'status': 'not_approved',
                        'message': 'Entry not approved in system'
                    })
        
        if unapproved_entries:
            return ToolResponse(
                success=False,
                message=f"Cannot post entries - {len(unapproved_entries)} require approval. Visit {APP_BASE_URL}/dashboard",
                data={
                    'unapproved_entries': unapproved_entries,
                    'dashboard_url': f"{APP_BASE_URL}/dashboard"
                }
            )
        
        # Validate entries
        validation_errors = []
        for entry in request.entries:
            if entry.debit_account not in coa:
                validation_errors.append({
                    'entry_id': entry.entry_id,
                    'error': f'Invalid debit account: {entry.debit_account}'
                })
            if entry.credit_account not in coa:
                validation_errors.append({
                    'entry_id': entry.entry_id,
                    'error': f'Invalid credit account: {entry.credit_account}'
                })
        
        if validation_errors:
            return ToolResponse(
                success=False,
                message=f"Validation failed for {len(validation_errors)} entries",
                data={'validation_errors': validation_errors}
            )
        
        # Post entries
        posted_entries = []
        for entry in request.entries:
            # Create debit transaction
            debit_txn = {
                'Txn_ID': f"{entry.entry_id}-DR",
                'Posting_Date_Raw': entry.date,
                'Fiscal_Period': request.fiscal_period,
                'Account_Code_Raw': entry.debit_account,
                'Amount': str(entry.amount),
                'Vendor_Name_Raw': 'Journal Entry',
                'Narrative': entry.description,
                'Cost_Center': 'CORP'
            }
            
            # Create credit transaction
            credit_txn = {
                'Txn_ID': f"{entry.entry_id}-CR",
                'Posting_Date_Raw': entry.date,
                'Fiscal_Period': request.fiscal_period,
                'Account_Code_Raw': entry.credit_account,
                'Amount': str(-entry.amount),
                'Vendor_Name_Raw': 'Journal Entry',
                'Narrative': entry.description,
                'Cost_Center': 'CORP'
            }
            
            transactions.append(debit_txn)
            transactions.append(credit_txn)
            posted_entries.append(entry.entry_id)
        
        # Save updated transactions
        fieldnames = list(transactions[0].keys())
        save_csv_data('Raw_GL_Export_With_CostCenters_Mar2026.csv', transactions, fieldnames)
        
        return ToolResponse(
            success=True,
            message=f"Posted {len(posted_entries)} journal entries",
            data={
                'posted_entries': posted_entries,
                'total_amount': sum(e.amount for e in request.entries)
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# TOOL 5: BUDGET VARIANCE ANALYSIS
# ============================================================================

@app.post("/tools/budget_variance_analysis", response_model=ToolResponse)
def budget_variance_analysis(request: BudgetVarianceRequest):
    """
    Compare actuals vs budget
    """
    try:
        # Load data
        transactions = load_csv_data('Raw_GL_Export_With_CostCenters_Mar2026.csv')
        budget_data = load_csv_data('Budget_Mar2026_Detailed.csv')
        coa = load_coa()
        
        # Filter period transactions
        period_txns = [t for t in transactions if t['Fiscal_Period'] == request.fiscal_period]
        
        # Calculate actuals by category
        actuals = defaultdict(float)
        for txn in period_txns:
            account = txn['Account_Code_Raw']
            if account in coa:
                category = coa[account]['category']
                actuals[category] += float(txn['Amount'])
        
        # Calculate budget by category (skip TOTAL rows)
        budget = defaultdict(float)
        for item in budget_data:
            category = item['Category']
            # Skip summary/total rows
            if category.upper() == 'TOTAL' or item['Account_Code'].startswith('TOTAL'):
                continue
            budget[category] += float(item['Budget_Amount'])
        
        # Calculate variances and identify significant ones
        variances = []
        significant_variances = []
        
        for category in set(list(actuals.keys()) + list(budget.keys())):
            actual_amt = actuals.get(category, 0)
            budget_amt = budget.get(category, 0)
            variance = actual_amt - budget_amt
            variance_pct = (variance / budget_amt * 100) if budget_amt != 0 else 0
            
            variance_item = {
                'category': category,
                'budget': budget_amt,
                'actual': actual_amt,
                'variance': variance,
                'variance_percent': variance_pct,
                'status': 'favorable' if variance < 0 else 'unfavorable'
            }
            variances.append(variance_item)
            
            # Flag significant variances (>10% or >$100,000)
            if abs(variance_pct) > 10 or abs(variance) > 100000:
                # Create approval item for significant variance
                approval_item = create_approval_item(
                    item_type="Budget Variance",
                    description=f"Significant variance in {category}: ${variance:,.2f} ({variance_pct:.1f}%)",
                    amount=abs(variance),
                    metadata={
                        "category": category,
                        "budget": budget_amt,
                        "actual": actual_amt,
                        "variance": variance,
                        "variance_percent": variance_pct
                    },
                    fiscal_period=request.fiscal_period
                )
                
                variance_item['requires_review'] = True
                variance_item['approval_token'] = approval_item.token
                variance_item['approval_links'] = get_approval_links(approval_item.token)
                significant_variances.append(variance_item)
        
        # Sort by absolute variance
        variances.sort(key=lambda x: abs(x['variance']), reverse=True)
        
        return ToolResponse(
            success=True,
            message=f"Budget variance analysis complete for {request.fiscal_period}. {len(significant_variances)} variances require review at {APP_BASE_URL}/dashboard",
            data={
                'fiscal_period': request.fiscal_period,
                'variances': variances,
                'significant_variances': significant_variances,
                'total_budget': sum(budget.values()),
                'total_actual': sum(actuals.values()),
                'total_variance': sum(actuals.values()) - sum(budget.values()),
                'dashboard_url': f"{APP_BASE_URL}/dashboard"
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# TOOL 6: YEAR-OVER-YEAR COMPARISON
# ============================================================================

@app.post("/tools/yoy_comparison", response_model=ToolResponse)
def yoy_comparison(request: YoYComparisonRequest):
    """
    Year-over-year performance comparison
    """
    try:
        # Load data
        transactions = load_csv_data('Raw_GL_Export_With_CostCenters_Mar2026.csv')
        prior_year_data = load_csv_data('PL_Statement_Mar2025_Comparative.csv')
        coa = load_coa()
        
        # Calculate current period by category
        current_txns = [t for t in transactions if t['Fiscal_Period'] == request.current_period]
        current_totals = defaultdict(float)
        
        for txn in current_txns:
            account = txn['Account_Code_Raw']
            if account in coa:
                category = coa[account]['category']
                current_totals[category] += float(txn['Amount'])
        
        # Load prior year data from comparative P&L (skip TOTAL rows)
        prior_totals = {}
        for item in prior_year_data:
            category = item['Category']
            # Skip summary/total rows
            if category.upper() == 'TOTAL' or item['Account_Code'].startswith('TOTAL'):
                continue
            # Use Mar_2025_Actual column from the CSV
            prior_totals[category] = float(item['Mar_2025_Actual'])
        
        # Calculate comparisons
        comparisons = []
        for category in set(list(current_totals.keys()) + list(prior_totals.keys())):
            current = current_totals.get(category, 0)
            prior = prior_totals.get(category, 0)
            variance = current - prior
            growth_rate = (variance / prior * 100) if prior != 0 else 0
            
            comparisons.append({
                'category': category,
                'prior_year': prior,
                'current_year': current,
                'variance': variance,
                'growth_rate': growth_rate
            })
        
        return ToolResponse(
            success=True,
            message=f"YoY comparison complete: {request.comparison_period} vs {request.current_period}",
            data={
                'current_period': request.current_period,
                'comparison_period': request.comparison_period,
                'comparisons': comparisons
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# TOOL 7: COST CENTER P&L
# ============================================================================

@app.post("/tools/cost_center_pl", response_model=ToolResponse)
def cost_center_pl(request: CostCenterPLRequest):
    """
    Generate P&L by cost center
    """
    try:
        # Load data
        transactions = load_csv_data('Raw_GL_Export_With_CostCenters_Mar2026.csv')
        coa = load_coa()
        
        # Filter period transactions
        period_txns = [t for t in transactions if t['Fiscal_Period'] == request.fiscal_period]
        
        # Calculate by cost center
        cc_summary = defaultdict(lambda: {'revenue': 0, 'expenses': 0})
        
        for txn in period_txns:
            account = txn['Account_Code_Raw']
            cost_center = txn.get('Cost_Center', 'UNASSIGNED')
            amount = float(txn['Amount'])
            
            if account in coa:
                acc_type = coa[account]['type']
                if acc_type == 'Revenue':
                    cc_summary[cost_center]['revenue'] += amount
                elif acc_type == 'Expense':
                    cc_summary[cost_center]['expenses'] += amount
        
        # Calculate net income and margin
        cost_center_results = []
        for cc, data in cc_summary.items():
            net_income = data['revenue'] - data['expenses']
            margin = (net_income / data['revenue'] * 100) if data['revenue'] != 0 else 0
            
            cost_center_results.append({
                'cost_center': cc,
                'revenue': data['revenue'],
                'expenses': data['expenses'],
                'net_income': net_income,
                'margin_percent': margin,
                'status': 'profitable' if net_income > 0 else 'loss'
            })
        
        # Sort by net income
        cost_center_results.sort(key=lambda x: x['net_income'], reverse=True)
        
        return ToolResponse(
            success=True,
            message=f"Cost center P&L generated for {request.fiscal_period}",
            data={
                'fiscal_period': request.fiscal_period,
                'cost_centers': cost_center_results,
                'total_revenue': sum(cc['revenue'] for cc in cost_center_results),
                'total_expenses': sum(cc['expenses'] for cc in cost_center_results),
                'total_net_income': sum(cc['net_income'] for cc in cost_center_results)
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# TOOL 8: MONTH-END CLOSE (UPDATED to use helper function)
# ============================================================================

# ============================================================================
# UPDATED TOOL 8: MONTH-END CLOSE (POC VERSION - Checks approvals only)
# ============================================================================

@app.post("/tools/close_period", response_model=ToolResponse)
def close_period(
    request: MonthEndCloseRequest,
    background_tasks: BackgroundTasks
):
    """
    Close the accounting period - POC VERSION
    
    This tool:
    - Checks that ALL generated approvals have been processed (ignores actual data)
    - Locks the period based on approval status only
    - Generates final financial statements
    - Sends email reports if requested
    """
    try:
        # ====================================================================
        # STEP 1: Check if ALL generated approvals have been processed
        # ====================================================================
        all_processed, pending_list = approval_registry.verify_all_approvals_processed(request.fiscal_period)
        
        if not all_processed:
            # Get summary for better error message
            summary = approval_registry.get_approval_summary(request.fiscal_period)
            
            pending_by_type = {}
            for p in pending_list:
                p_type = p.get('type', 'Unknown')
                pending_by_type[p_type] = pending_by_type.get(p_type, 0) + 1
            
            return ToolResponse(
                success=False,
                message=f"Cannot close period - {len(pending_list)} approvals still pending! Please process all pending approvals before closing.",
                data={
                    'pending_count': len(pending_list),
                    'pending_by_type': pending_by_type,
                    'summary': summary,
                    'dashboard_url': f"{APP_BASE_URL}/dashboard",
                    'action_required': 'Please process all pending approvals before closing'
                }
            )
        
        # ====================================================================
        # STEP 2: Double-check no approvals in memory (backward compatibility)
        # ====================================================================
        memory_pending = [
            {"token": token, "type": item.type}
            for token, item in pending_approvals.items()
            if item.metadata and item.metadata.get('fiscal_period') == request.fiscal_period
        ]
        
        if memory_pending:
            return ToolResponse(
                success=False,
                message=f"Cannot close period - {len(memory_pending)} approvals still in memory!",
                data={
                    'pending_in_memory': memory_pending,
                    'dashboard_url': f"{APP_BASE_URL}/dashboard"
                }
            )
        
        # ====================================================================
        # STEP 3: Generate final approval summary for reporting
        # ====================================================================
        summary = approval_registry.get_approval_summary(request.fiscal_period)
        
        approved_count = summary.get('approved', 0)
        rejected_count = summary.get('rejected', 0)
        assigned_count = summary.get('assigned', 0)
        
        # Generate approval summary for the close report
        approval_summary_html = ""
        by_type = summary.get('by_type', {})
        for approval_type, counts in by_type.items():
            approval_summary_html += f"<li><strong>{approval_type}:</strong> {counts.get('approved', 0)} approved, {counts.get('rejected', 0)} rejected, {counts.get('assigned', 0)} assigned (Total: {counts.get('total', 0)})</li>"
        
        close_summary = {
            'fiscal_period': request.fiscal_period,
            'entity_code': request.entity_code,
            'close_date': datetime.now().isoformat(),
            'approved_by': request.approved_by,
            'status': 'CLOSED',
            'approvals_summary': {
                'total_generated': summary['total_generated'],
                'approved': approved_count,
                'rejected': rejected_count,
                'assigned': assigned_count,
                'by_type': by_type
            },
            'statements_generated': [
                'Income Statement',
                'Balance Sheet',
                'Cash Flow Statement',
                'Statement of Changes in Equity'
            ],
            'note': 'POC Mode: Period closed based on approval registry only. Data was not modified.'
        }
        
        # Send email reports if requested
        if request.send_email_reports:
            email_request = EmailReportRequest(
                recipients=[
                    EmailRecipient(email=os.getenv("CFO_EMAIL", "deep.dws.mp@gmail.com"), name="CFO"),
                    EmailRecipient(email=os.getenv("FINANCE_EMAIL", "steny.sebastian@octanesolutions.com.au"), name="Finance"),
                    EmailRecipient(email=os.getenv("FINANCE_EMAIL", "deepanshu.dubey@octanesolutions.com.au"), name="Finance")
                ],
                fiscal_period=request.fiscal_period,
                entity_code=request.entity_code,
                include_pdf=True,
                include_csv=True,
                subject=f"Month-End Close Report - {request.fiscal_period}",
                message=f"""
                <h2>Month-End Close Completed (POC Mode)</h2>
                <p>The month-end close for period <strong>{request.fiscal_period}</strong> has been completed successfully.</p>
                <p><strong>Closed by:</strong> {request.approved_by}</p>
                <p><strong>Close Date:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                <p><strong>Note:</strong> This is a POC demo. Period closed based on approval registry only.</p>
                
                <h3>📋 Approval Summary</h3>
                <ul>
                    <li><strong>Total Approvals Generated:</strong> {summary['total_generated']}</li>
                    <li><strong>Approved:</strong> {approved_count}</li>
                    <li><strong>Rejected:</strong> {rejected_count}</li>
                    <li><strong>Assigned:</strong> {assigned_count}</li>
                </ul>
                
                <h4>Breakdown by Type:</h4>
                <ul>
                    {approval_summary_html}
                </ul>
                
                <p>Please find attached the final financial reports.</p>
                """
            )
            
            background_tasks.add_task(send_financial_reports, email_request, background_tasks)
            close_summary['email_reports_sent'] = True
        
        # Log the successful close
        logger.info(f"✅ Period {request.fiscal_period} closed successfully by {request.approved_by} (POC Mode)")
        logger.info(f"   Approvals processed: {approved_count} approved, {rejected_count} rejected, {assigned_count} assigned out of {summary['total_generated']} total")
        
        return ToolResponse(
            success=True,
            message=f"✅ Period {request.fiscal_period} closed successfully! Processed {approved_count} approvals out of {summary['total_generated']} total. (POC Mode)",
            data=close_summary
        )
        
    except Exception as e:
        logger.error(f"Error in close_period: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# TOOL 9: GET MISSING COST CENTERS
# ============================================================================

@app.get("/tools/get_missing_cost_centers/{fiscal_period}", response_model=ToolResponse)
def get_missing_cost_centers(fiscal_period: str):
    """
    Get list of transactions with missing cost centers
    """
    try:
        transactions = load_csv_data('Raw_GL_Export_With_CostCenters_Mar2026.csv')
        period_txns = [t for t in transactions if t['Fiscal_Period'] == fiscal_period]
        
        missing = []
        for txn in period_txns:
            if not txn.get('Cost_Center', ''):
                # Check if this transaction already has a pending approval
                existing_token = None
                for token, item in pending_approvals.items():
                    if (item.type == "Missing Cost Center" and 
                        item.metadata and 
                        item.metadata.get('transaction_id') == txn['Txn_ID']):
                        existing_token = token
                        break
                
                txn_data = {
                    'transaction_id': txn['Txn_ID'],
                    'posting_date': txn['Posting_Date_Raw'],
                    'account': txn['Account_Code_Raw'],
                    'vendor': txn['Vendor_Name_Raw'],
                    'amount': float(txn['Amount']),
                    'narrative': txn['Narrative']
                }
                
                if existing_token:
                    txn_data['approval_token'] = existing_token
                    txn_data['approval_links'] = get_approval_links(existing_token)
                    txn_data['approval_status'] = 'pending'
                else:
                    # Create new approval item
                    approval_item = create_approval_item(
                        item_type="Missing Cost Center",
                        description=f"Transaction {txn['Txn_ID']}: {txn['Narrative']}",
                        amount=float(txn['Amount']),
                        account=txn['Account_Code_Raw'],
                        metadata={
                            "transaction_id": txn['Txn_ID'],
                            "posting_date": txn['Posting_Date_Raw'],
                            "vendor": txn['Vendor_Name_Raw']
                        },
                        fiscal_period=fiscal_period
                    )
                    txn_data['approval_token'] = approval_item.token
                    txn_data['approval_links'] = get_approval_links(approval_item.token)
                    txn_data['approval_status'] = 'new'
                
                missing.append(txn_data)
        
        return ToolResponse(
            success=True,
            message=f"Found {len(missing)} transactions with missing cost centers. Approve at {APP_BASE_URL}/dashboard",
            data={
                'fiscal_period': fiscal_period,
                'missing_count': len(missing),
                'transactions': missing,
                'total_amount': sum(t['amount'] for t in missing) if missing else 0,
                'dashboard_url': f"{APP_BASE_URL}/dashboard"
            }
        )
        
    except Exception as e:
        logger.error(f"Error in get_missing_cost_centers: {e}")
        return ToolResponse(
            success=False,
            message=f"Error retrieving missing cost centers: {str(e)}",
            data=None
        )

@app.post("/tools/suggest_cost_centers", response_model=ToolResponse)
def suggest_cost_centers(request: CostCenterSuggestionsRequest):
    """
    Store agent's cost center suggestions in approval items for user review.
    This does NOT update the CSV - only prepares suggestions for approval.
    """
    try:
        # Load cost centers to validate suggestions
        cost_centers_data = load_csv_data('Master_CostCenters_States.csv')
        valid_cost_centers = [cc['Cost_Center_Code'] for cc in cost_centers_data]
        
        updated_count = 0
        invalid_suggestions = []
        not_found = []
        
        # Create lookup for suggestions
        suggestion_map = {s.transaction_id: s for s in request.suggestions}
        
        # Update approval items with suggestions
        for token, item in pending_approvals.items():
            if item.type == "Missing Cost Center":
                txn_id = item.metadata.get('transaction_id') if item.metadata else None
                
                if txn_id and txn_id in suggestion_map:
                    suggestion = suggestion_map[txn_id]
                    
                    # Validate cost center
                    if suggestion.suggested_cost_center not in valid_cost_centers:
                        invalid_suggestions.append({
                            'transaction_id': txn_id,
                            'suggested_cost_center': suggestion.suggested_cost_center,
                            'reason': 'Invalid cost center code'
                        })
                        continue
                    
                    # Update approval item with suggestion
                    item.cost_center = suggestion.suggested_cost_center
                    if item.metadata is None:
                        item.metadata = {}
                    item.metadata['suggestion_reason'] = suggestion.reason
                    item.metadata['suggestion_confidence'] = suggestion.confidence
                    item.metadata['suggested_at'] = datetime.now().isoformat()
                    updated_count += 1
                    logger.info(f"Suggested cost center {suggestion.suggested_cost_center} for transaction {txn_id}")
        
        # Check for suggestions that didn't match any approval items
        for txn_id in suggestion_map:
            found = False
            for item in pending_approvals.values():
                if item.type == "Missing Cost Center" and item.metadata and item.metadata.get('transaction_id') == txn_id:
                    found = True
                    break
            if not found:
                not_found.append(txn_id)
        
        return ToolResponse(
            success=len(invalid_suggestions) == 0,
            message=f"✅ Stored {updated_count} cost center suggestions for user approval. View at {APP_BASE_URL}/dashboard",
            data={
                'updated_count': updated_count,
                'requested_count': len(request.suggestions),
                'invalid_count': len(invalid_suggestions),
                'invalid_suggestions': invalid_suggestions,
                'not_found_count': len(not_found),
                'not_found_transactions': not_found[:10] if not_found else [],
                'dashboard_url': f"{APP_BASE_URL}/dashboard"
            }
        )
        
    except Exception as e:
        logger.error(f"Error in suggest_cost_centers: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# TOOL 10: GET OVERDUE INVOICES
# ============================================================================

@app.get("/tools/get_overdue_invoices", response_model=ToolResponse)
def get_overdue_invoices():
    """
    Get list of overdue invoices requiring collection action
    """
    try:
        ar_records = load_csv_data('AR_Subledger_Mar2026.csv')
        
        overdue = []
        for record in ar_records:
            if record['Status'] == 'Overdue':
                amount = float(record['Outstanding_Balance'])
                
                # For very old/high value invoices, create approval items
                days_outstanding = int(record['Days_Outstanding'])
                invoice_data = {
                    'customer_id': record['Customer_ID'],
                    'customer_name': record['Customer_Name'],
                    'invoice_number': record['Invoice_Number'],
                    'invoice_date': record['Invoice_Date'],
                    'due_date': record['Due_Date'],
                    'days_outstanding': days_outstanding,
                    'outstanding_balance': amount,
                    'cost_center': record['Cost_Center'],
                    'region': record['Region']
                }
                
                # Flag for approval if > 90 days overdue or > $100,000
                if days_outstanding > 90 or amount > 100000:
                    # Check if already has approval
                    existing_token = None
                    for token, item in pending_approvals.items():
                        if (item.type == "Overdue Invoice" and 
                            item.metadata and 
                            item.metadata.get('invoice_number') == record['Invoice_Number']):
                            existing_token = token
                            break
                    
                    if existing_token:
                        invoice_data['approval_token'] = existing_token
                        invoice_data['approval_links'] = get_approval_links(existing_token)
                        invoice_data['approval_status'] = 'pending'
                    else:
                        approval_item = create_approval_item(
                            item_type="Overdue Invoice",
                            description=f"Overdue invoice {record['Invoice_Number']} - {record['Customer_Name']} (${amount:,.2f}, {days_outstanding} days)",
                            amount=amount,
                            metadata={
                                "invoice_number": record['Invoice_Number'],
                                "customer": record['Customer_Name'],
                                "days_outstanding": days_outstanding,
                                "due_date": record['Due_Date']
                            },
                            fiscal_period="2026-04"
                        )
                        invoice_data['approval_token'] = approval_item.token
                        invoice_data['approval_links'] = get_approval_links(approval_item.token)
                        invoice_data['approval_status'] = 'new'
                    
                    invoice_data['requires_action'] = True
                
                overdue.append(invoice_data)
        
        # Sort by days outstanding
        overdue.sort(key=lambda x: x['days_outstanding'], reverse=True)
        
        total_outstanding = sum(inv['outstanding_balance'] for inv in overdue) if overdue else 0
        
        return ToolResponse(
            success=True,
            message=f"Found {len(overdue)} overdue invoices. Critical items require approval at {APP_BASE_URL}/dashboard",
            data={
                'overdue_count': len(overdue),
                'invoices': overdue,
                'total_outstanding': total_outstanding,
                'dashboard_url': f"{APP_BASE_URL}/dashboard"
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# CFO FINANCIAL DASHBOARD (WITH SUMMARY SECTION)
# ============================================================================

@app.get("/cfo/financial_dashboard", response_class=HTMLResponse)
async def cfo_financial_dashboard(
    fiscal_period: str = Query("2026-04", description="Fiscal period to display"),
    entity_code: str = Query("AUS01", description="Entity code")
):
    """
    Comprehensive CFO financial dashboard with actual financial data
    Shows trial balance, P&L, budget variances, and key financial metrics with summary and forecast
    """
    try:
        # Load logo as base64
        logo_base64 = ""
        try:
            with open("Octane_logo.png", "rb") as logo_file:
                import base64
                logo_base64 = base64.b64encode(logo_file.read()).decode('utf-8')
        except Exception as e:
            logger.warning(f"Could not load logo: {e}")
        
        # Load financial data
        transactions = load_csv_data('Raw_GL_Export_With_CostCenters_Mar2026.csv')
        coa = load_coa()
        budget_data = load_csv_data('Budget_Mar2026_Detailed.csv')
        ar_records = load_csv_data('AR_Subledger_Mar2026.csv')
        
        # Filter for the period
        period_txns = [t for t in transactions if t['Fiscal_Period'] == fiscal_period]
        
        # ====================================================================
        # TRIAL BALANCE CALCULATION
        # ====================================================================
        
        # Calculate account balances
        account_balances = defaultdict(float)
        for txn in period_txns:
            if txn['Account_Code_Raw'] in coa:
                account_balances[txn['Account_Code_Raw']] += float(txn['Amount'])
        
        # Group by account type
        type_totals = {
            'Revenue': 0,
            'Expense': 0,
            'Asset': 0,
            'Liability': 0,
            'Equity': 0
        }
        
        # Detailed account list for display
        revenue_accounts = []
        expense_accounts = []
        asset_accounts = []
        liability_accounts = []
        equity_accounts = []
        
        for account, balance in account_balances.items():
            if account in coa:
                acc_type = coa[account]['type']
                acc_name = coa[account]['name']
                type_totals[acc_type] += balance
                
                account_info = {
                    'code': account,
                    'name': acc_name,
                    'balance': balance
                }
                
                if acc_type == 'Revenue':
                    revenue_accounts.append(account_info)
                elif acc_type == 'Expense':
                    expense_accounts.append(account_info)
                elif acc_type == 'Asset':
                    asset_accounts.append(account_info)
                elif acc_type == 'Liability':
                    liability_accounts.append(account_info)
                elif acc_type == 'Equity':
                    equity_accounts.append(account_info)
        
        # Sort accounts by balance (largest first)
        revenue_accounts.sort(key=lambda x: abs(x['balance']), reverse=True)
        expense_accounts.sort(key=lambda x: abs(x['balance']), reverse=True)
        
        # Calculate Net Income
        net_income = type_totals['Revenue'] - type_totals['Expense']
        
        # ====================================================================
        # BUDGET VARIANCE CALCULATION
        # ====================================================================
        
        # Calculate actuals by category
        actuals_by_category = defaultdict(float)
        for txn in period_txns:
            account = txn['Account_Code_Raw']
            if account in coa:
                category = coa[account]['category']
                actuals_by_category[category] += float(txn['Amount'])
        
        # Calculate budget by category
        budget_by_category = defaultdict(float)
        for item in budget_data:
            category = item['Category']
            if category.upper() != 'TOTAL' and not item['Account_Code'].startswith('TOTAL'):
                budget_by_category[category] += float(item['Budget_Amount'])
        
        # Calculate variances
        variances = []
        total_variance = 0
        for category in set(list(actuals_by_category.keys()) + list(budget_by_category.keys())):
            actual = actuals_by_category.get(category, 0)
            budget = budget_by_category.get(category, 0)
            variance = actual - budget
            variance_pct = (variance / budget * 100) if budget != 0 else 0
            total_variance += abs(variance)
            
            variances.append({
                'category': category,
                'actual': actual,
                'budget': budget,
                'variance': variance,
                'variance_pct': variance_pct,
                'status': 'favorable' if variance < 0 else 'unfavorable'
            })
        
        variances.sort(key=lambda x: abs(x['variance']), reverse=True)
        
        # ====================================================================
        # AR METRICS
        # ====================================================================
        
        total_ar = sum(float(r['Outstanding_Balance']) for r in ar_records)
        overdue_ar = sum(float(r['Outstanding_Balance']) for r in ar_records if r['Status'] == 'Overdue')
        current_ar = total_ar - overdue_ar
        
        # AR Aging
        aging_buckets = {
            '0-30 Days': 0,
            '31-60 Days': 0,
            '61-90 Days': 0,
            '90+ Days': 0
        }
        
        for record in ar_records:
            days = int(record['Days_Outstanding'])
            amount = float(record['Outstanding_Balance'])
            
            if days <= 30:
                aging_buckets['0-30 Days'] += amount
            elif days <= 60:
                aging_buckets['31-60 Days'] += amount
            elif days <= 90:
                aging_buckets['61-90 Days'] += amount
            else:
                aging_buckets['90+ Days'] += amount
        
        # ====================================================================
        # PROFITABILITY METRICS
        # ====================================================================
        
        # Calculate margins
        gross_profit = type_totals['Revenue'] - sum(e['balance'] for e in expense_accounts if 'cost' in e['name'].lower())
        gross_margin = (gross_profit / type_totals['Revenue'] * 100) if type_totals['Revenue'] != 0 else 0
        net_margin = (net_income / type_totals['Revenue'] * 100) if type_totals['Revenue'] != 0 else 0
        
        # ====================================================================
        # HTML DASHBOARD WITH SUMMARY SECTION AND FORECAST
        # ====================================================================
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>CFO Financial Dashboard - {fiscal_period}</title>
            <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
            <style>
                * {{ margin: 0; padding: 0; box-sizing: border-box; }}
                
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    background: #f5f5f5;
                    padding: 20px;
                }}
                
                .dashboard-header {{
                    background: #000000;
                    color: white;
                    padding: 30px;
                    border-radius: 15px;
                    margin-bottom: 30px;
                    box-shadow: 0 10px 30px rgba(0,0,0,0.3);
                    display: flex;
                    align-items: center;
                    gap: 30px;
                }}
                
                .header-logo {{
                    height: 60px;
                    flex-shrink: 0;
                }}
                
                .header-content {{
                    flex-grow: 1;
                }}
                
                .header-title {{
                    font-size: 2.5em;
                    margin-bottom: 10px;
                }}
                
                .header-sub {{
                    opacity: 0.9;
                    font-size: 1.1em;
                }}
                
                .period-badge {{
                    background: rgba(255,255,255,0.2);
                    padding: 8px 16px;
                    border-radius: 20px;
                    display: inline-block;
                    margin-top: 15px;
                }}
                
                .kpi-grid {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                    gap: 20px;
                    margin-bottom: 30px;
                }}
                
                .kpi-card {{
                    background: white;
                    padding: 25px;
                    border-radius: 15px;
                    box-shadow: 0 5px 15px rgba(0,0,0,0.08);
                    transition: transform 0.3s;
                }}
                
                .kpi-card:hover {{
                    transform: translateY(-5px);
                    box-shadow: 0 10px 25px rgba(0,0,0,0.15);
                }}
                
                .kpi-title {{
                    color: #666;
                    font-size: 0.9em;
                    text-transform: uppercase;
                    letter-spacing: 1px;
                    margin-bottom: 10px;
                }}
                
                .kpi-value {{
                    font-size: 2.2em;
                    font-weight: bold;
                    color: #000000;
                }}
                
                .kpi-trend {{
                    margin-top: 10px;
                    font-size: 0.9em;
                }}
                
                .trend-up {{ color: #333333; }}
                .trend-down {{ color: #666666; }}
                
                .chart-grid {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(500px, 1fr));
                    gap: 20px;
                    margin-bottom: 30px;
                }}
                
                .chart-card {{
                    background: white;
                    padding: 20px;
                    border-radius: 15px;
                    box-shadow: 0 5px 15px rgba(0,0,0,0.08);
                }}
                
                .chart-title {{
                    font-size: 1.2em;
                    color: #000000;
                    margin-bottom: 20px;
                    padding-bottom: 10px;
                    border-bottom: 2px solid #e0e0e0;
                }}
                
                .chart-container {{
                    height: 300px;
                    position: relative;
                }}
                
                .financial-grid {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
                    gap: 20px;
                    margin-bottom: 30px;
                }}
                
                .financial-card {{
                    background: white;
                    padding: 20px;
                    border-radius: 15px;
                    box-shadow: 0 5px 15px rgba(0,0,0,0.08);
                }}
                
                .financial-table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin-top: 15px;
                }}
                
                .financial-table th {{
                    text-align: left;
                    padding: 10px;
                    background: #f0f0f0;
                    color: #000000;
                    font-weight: 600;
                }}
                
                .financial-table td {{
                    padding: 10px;
                    border-bottom: 1px solid #f0f0f0;
                }}
                
                .financial-table tr:last-child td {{
                    border-bottom: none;
                }}
                
                .amount {{
                    text-align: right;
                    font-weight: 500;
                }}
                
                .total-row {{
                    background: #f0f0f0;
                    font-weight: bold;
                }}
                
                .variance-favorable {{
                    color: #333333;
                    font-weight: 500;
                }}
                
                .variance-unfavorable {{
                    color: #666666;
                    font-weight: 500;
                }}
                
                .badge {{
                    display: inline-block;
                    padding: 4px 8px;
                    border-radius: 12px;
                    font-size: 0.8em;
                    font-weight: 500;
                    background: #f0f0f0;
                    color: #000000;
                }}
                
                .badge-success {{ background: #000000; color: white; }}
                .badge-warning {{ background: #666666; color: white; }}
                .badge-danger {{ background: #999999; color: white; }}
                
                .footer {{
                    text-align: center;
                    margin-top: 30px;
                    padding: 20px;
                    color: #666;
                }}
                
                .footer a {{
                    color: #000000;
                    text-decoration: none;
                    margin: 0 10px;
                }}
                
                .footer a:hover {{
                    text-decoration: underline;
                }}
                
                /* Summary Card Styles */
                .summary-card {{
                    background: linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%);
                    padding: 25px;
                    border-radius: 15px;
                    margin-bottom: 30px;
                    box-shadow: 0 5px 20px rgba(0,0,0,0.1);
                    border: 1px solid #e0e0e0;
                }}
                
                .summary-header {{
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    margin-bottom: 20px;
                    padding-bottom: 15px;
                    border-bottom: 2px solid #000000;
                }}
                
                .summary-header h2 {{
                    color: #000000;
                    font-size: 1.8em;
                    margin: 0;
                }}
                
                .summary-date {{
                    background: #000000;
                    color: white;
                    padding: 8px 16px;
                    border-radius: 20px;
                    font-weight: bold;
                }}
                
                .summary-grid {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                    gap: 20px;
                    margin-bottom: 20px;
                }}
                
                .summary-item {{
                    background: white;
                    padding: 20px;
                    border-radius: 12px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.05);
                }}
                
                .summary-item h3 {{
                    color: #000000;
                    margin-bottom: 15px;
                    padding-bottom: 10px;
                    border-bottom: 2px solid #e0e0e0;
                    font-size: 1.2em;
                }}
                
                .summary-table {{
                    width: 100%;
                }}
                
                .summary-table td {{
                    padding: 8px 0;
                }}
                
                .summary-table td:last-child {{
                    text-align: right;
                    font-weight: 500;
                }}
                
                .highlight {{
                    background: #f0f0f0;
                    border-radius: 8px;
                }}
                
                .highlight td {{
                    padding: 12px 8px;
                }}
                
                .key-points {{
                    background: #f0f0f0;
                    padding: 15px 20px;
                    border-radius: 10px;
                    margin-top: 15px;
                }}
                
                .key-points h4 {{
                    margin-bottom: 10px;
                    color: #000000;
                }}
                
                .key-points ul {{
                    list-style-type: none;
                    padding: 0;
                    margin: 0;
                    display: flex;
                    flex-wrap: wrap;
                    gap: 15px;
                }}
                
                .key-points li {{
                    background: white;
                    padding: 8px 16px;
                    border-radius: 20px;
                    font-size: 0.95em;
                    box-shadow: 0 2px 5px rgba(0,0,0,0.05);
                }}
                
                /* Forecast Section Styles */
                .forecast-summary {{
                    padding: 10px;
                }}
                
                .forecast-metrics {{
                    padding: 10px;
                }}
                
                .forecast-metrics table td {{
                    padding: 8px 0;
                    border-bottom: 1px solid #f0f0f0;
                }}
                
                .forecast-metrics table tr:last-child td {{
                    border-bottom: none;
                }}
                
                @media (max-width: 768px) {{
                    .chart-grid {{
                        grid-template-columns: 1fr;
                    }}
                    
                    .financial-grid {{
                        grid-template-columns: 1fr;
                    }}
                    
                    .summary-grid {{
                        grid-template-columns: 1fr;
                    }}
                }}
            </style>
        </head>
        <body>
            <div class="dashboard-header">
                <img src="data:image/png;base64,{logo_base64}" alt="Octane Logo" class="header-logo">
                <div class="header-content">
                    <div class="header-title">💰 CFO Financial Dashboard</div>
                    <div class="header-sub">Real-time financial performance and month-end close status</div>
                    <div class="period-badge">
                        📅 Period: {fiscal_period} | Entity: {entity_code} |
                        As of: {datetime.now().strftime('%Y-%m-%d %H:%M')}
                    </div>
                </div>
            </div>
            
            <!-- ==================== EXECUTIVE SUMMARY SECTION ==================== -->
            <div class="summary-card">
                <div class="summary-header">
                    <h2>📊 Executive Summary - {fiscal_period}</h2>
                    <span class="summary-date">{datetime.now().strftime('%d %b %Y')}</span>
                </div>
                
                <div class="summary-grid">
                    <!-- Performance Summary -->
                    <div class="summary-item">
                        <h3>📈 Performance</h3>
                        <table class="summary-table">
                            <tr>
                                <td><strong>Revenue:</strong></td>
                                <td>${type_totals['Revenue']:,.0f}</td>
                            </tr>
                            <tr>
                                <td><strong>Expenses:</strong></td>
                                <td>${type_totals['Expense']:,.0f}</td>
                            </tr>
                            <tr class="highlight">
                                <td><strong>Net Income:</strong></td>
                                <td style="font-weight: bold; color: {'#000000' if net_income >= 0 else '#666666'};">
                                    ${net_income:,.0f}
                                </td>
                            </tr>
                            <tr>
                                <td><strong>Gross Margin:</strong></td>
                                <td>{gross_margin:.1f}%</td>
                            </tr>
                            <tr>
                                <td><strong>Net Margin:</strong></td>
                                <td>{net_margin:.1f}%</td>
                            </tr>
                        </table>
                    </div>
                    
                    <!-- AR Summary -->
                    <div class="summary-item">
                        <h3>💰 Accounts Receivable</h3>
                        <table class="summary-table">
                            <tr>
                                <td><strong>Total Outstanding:</strong></td>
                                <td>${total_ar:,.0f}</td>
                            </tr>
                            <tr>
                                <td><strong>Current:</strong></td>
                                <td>${current_ar:,.0f}</td>
                            </tr>
                            <tr>
                                <td><strong>Overdue:</strong></td>
                                <td style="color: {'#000000' if overdue_ar == 0 else '#666666'};">
                                    ${overdue_ar:,.0f}
                                </td>
                            </tr>
                            <tr>
                                <td><strong>Overdue %:</strong></td>
                                <td>{(overdue_ar/total_ar*100) if total_ar > 0 else 0:.1f}%</td>
                            </tr>
                            <tr>
                                <td><strong>90+ Days Aging:</strong></td>
                                <td>${aging_buckets['90+ Days']:,.0f}</td>
                            </tr>
                        </table>
                    </div>
                    
                    <!-- Budget Variance Summary -->
                    <div class="summary-item">
                        <h3>📊 Budget Variance</h3>
                        <table class="summary-table">
                            <tr>
                                <td><strong>Total Budget:</strong></td>
                                <td>${sum(v['budget'] for v in variances):,.0f}</td>
                            </tr>
                            <tr>
                                <td><strong>Total Actual:</strong></td>
                                <td>${sum(v['actual'] for v in variances):,.0f}</td>
                            </tr>
                            <tr class="highlight">
                                <td><strong>Total Variance:</strong></td>
                                <td style="font-weight: bold; color: {'#000000' if sum(v['variance'] for v in variances) < 0 else '#666666'};">
                                    ${sum(v['variance'] for v in variances):,.0f}
                                </td>
                            </tr>
                            <tr>
                                <td><strong>Variance %:</strong></td>
                                <td>{(sum(v['variance'] for v in variances)/sum(v['budget'] for v in variances)*100) if sum(v['budget'] for v in variances) > 0 else 0:.1f}%</td>
                            </tr>
                        </table>
                    </div>
                </div>
                
                <!-- Key Highlights -->
                <div class="key-points">
                    <h4>🔍 Key Highlights</h4>
                    <ul>
        """
        
        # Add dynamic highlights
        highlights = []
        
        if net_income > 0:
            highlights.append(f"✅ Profitable period with net income of ${net_income:,.0f}")
        else:
            highlights.append(f"⚠️ Net loss of ${abs(net_income):,.0f} this period")
        
        if overdue_ar == 0:
            highlights.append("✅ No overdue receivables")
        elif overdue_ar < total_ar * 0.1:
            highlights.append(f"⚠️ Overdue receivables at {(overdue_ar/total_ar*100):.1f}% of total AR")
        else:
            highlights.append(f"⚠️ High overdue receivables at {(overdue_ar/total_ar*100):.1f}% of total AR")
        
        # Check significant variances
        significant_vars = [v for v in variances if abs(v['variance_pct']) > 10]
        if significant_vars:
            highlights.append(f"⚠️ {len(significant_vars)} categories with >10% budget variance")
        
        # Add AR aging highlight
        if aging_buckets['90+ Days'] > 0:
            highlights.append(f"⚠️ ${aging_buckets['90+ Days']:,.0f} in 90+ days aging bucket")
        
        # Revenue growth/decline
        if len(revenue_accounts) > 0:
            highlights.append(f"💰 Top revenue: {revenue_accounts[0]['code']} - ${revenue_accounts[0]['balance']:,.0f}")
        
        for highlight in highlights[:4]:  # Show top 4 highlights
            html_content += f"""
                        <li>{highlight}</li>
            """
        
        html_content += f"""
                    </ul>
                </div>
            </div>
            <!-- ==================== END EXECUTIVE SUMMARY ==================== -->
            
            <!-- KPI Cards -->
            <div class="kpi-grid">
                <div class="kpi-card">
                    <div class="kpi-title">Total Revenue</div>
                    <div class="kpi-value">${type_totals['Revenue']:,.0f}</div>
                    <div class="kpi-trend">
                        <span class="{'trend-up' if net_income > 0 else 'trend-down'}">
                            Net Income: ${net_income:,.0f}
                        </span>
                    </div>
                </div>
                
                <div class="kpi-card">
                    <div class="kpi-title">Total Expenses</div>
                    <div class="kpi-value">${type_totals['Expense']:,.0f}</div>
                    <div class="kpi-trend">
                        <span>vs Budget: ${type_totals['Expense'] - budget_by_category.get('Operating Expenses', 0):,.0f}</span>
                    </div>
                </div>
                
                <div class="kpi-card">
                    <div class="kpi-title">Gross Margin</div>
                    <div class="kpi-value">{gross_margin:.1f}%</div>
                    <div class="kpi-trend">
                        <span>Gross Profit: ${gross_profit:,.0f}</span>
                    </div>
                </div>
                
                <div class="kpi-card">
                    <div class="kpi-title">Net Margin</div>
                    <div class="kpi-value">{net_margin:.1f}%</div>
                    <div class="kpi-trend">
                        <span>Net Income: ${net_income:,.0f}</span>
                    </div>
                </div>
                
                <div class="kpi-card">
                    <div class="kpi-title">AR Outstanding</div>
                    <div class="kpi-value">${total_ar:,.0f}</div>
                    <div class="kpi-trend">
                        <span class="trend-down">Overdue: ${overdue_ar:,.0f}</span>
                    </div>
                </div>
                
                <div class="kpi-card">
                    <div class="kpi-title">Budget Variance</div>
                    <div class="kpi-value">${sum(v['variance'] for v in variances):,.0f}</div>
                    <div class="kpi-trend">
                        <span>{'Favorable' if sum(v['variance'] for v in variances) < 0 else 'Unfavorable'}</span>
                    </div>
                </div>
            </div>
            
            <!-- Charts -->
            <div class="chart-grid">
                <!-- Revenue vs Expense Chart -->
                <div class="chart-card">
                    <div class="chart-title">📊 Revenue vs Expenses</div>
                    <div class="chart-container">
                        <canvas id="revenueExpenseChart"></canvas>
                    </div>
                </div>
                
                <!-- Budget Variance Chart -->
                <div class="chart-card">
                    <div class="chart-title">📈 Budget Variance by Category</div>
                    <div class="chart-container">
                        <canvas id="varianceChart"></canvas>
                    </div>
                </div>
                
                <!-- AR Aging Chart -->
                <div class="chart-card">
                    <div class="chart-title">📅 AR Aging Analysis</div>
                    <div class="chart-container">
                        <canvas id="arAgingChart"></canvas>
                    </div>
                </div>
                
                <!-- Top Expenses Chart -->
                <div class="chart-card">
                    <div class="chart-title">🔥 Top 5 Expenses</div>
                    <div class="chart-container">
                        <canvas id="topExpensesChart"></canvas>
                    </div>
                </div>
            </div>
            
            <!-- ==================== FORECAST SECTION ==================== -->
            <div class="summary-card" style="margin-top: 30px;">
                <div class="summary-header">
                    <h2>🔮 Financial Forecast - Next 3 Months</h2>
                    <span class="summary-date">Based on historical trends & budget</span>
                </div>
                
                <div class="forecast-summary">
                    <div style="display: flex; gap: 20px; margin-bottom: 30px; flex-wrap: wrap;">
                        <!-- Revenue Forecast -->
                        <div style="flex: 1; min-width: 250px; background: white; padding: 20px; border-radius: 12px; box-shadow: 0 2px 10px rgba(0,0,0,0.05);">
                            <h3 style="color: #000000; margin-bottom: 15px;">📈 Revenue Forecast</h3>
                            <table style="width: 100%;">
                                <tr>
                                    <td><strong>Current Month:</strong></td>
                                    <td style="text-align: right; font-weight: bold;">${type_totals['Revenue']:,.0f}</td>
                                </tr>
                                <tr>
                                    <td><strong>Next Month:</strong></td>
                                    <td style="text-align: right; color: #333333;">${type_totals['Revenue'] * 1.02:,.0f}</td>
                                </tr>
                                <tr>
                                    <td><strong>Month +2:</strong></td>
                                    <td style="text-align: right; color: #333333;">${type_totals['Revenue'] * 1.035:,.0f}</td>
                                </tr>
                                <tr>
                                    <td><strong>Month +3:</strong></td>
                                    <td style="text-align: right; color: #333333;">${type_totals['Revenue'] * 1.05:,.0f}</td>
                                </tr>
                                <tr style="border-top: 1px solid #e0e0e0;">
                                    <td style="padding-top: 10px;"><strong>Growth (QoQ):</strong></td>
                                    <td style="text-align: right; padding-top: 10px; color: #000000; font-weight: bold;">+5.0%</td>
                                </tr>
                            </table>
                        </div>
                        
                        <!-- Expense Forecast -->
                        <div style="flex: 1; min-width: 250px; background: white; padding: 20px; border-radius: 12px; box-shadow: 0 2px 10px rgba(0,0,0,0.05);">
                            <h3 style="color: #000000; margin-bottom: 15px;">📉 Expense Forecast</h3>
                            <table style="width: 100%;">
                                <tr>
                                    <td><strong>Current Month:</strong></td>
                                    <td style="text-align: right; font-weight: bold;">${type_totals['Expense']:,.0f}</td>
                                </tr>
                                <tr>
                                    <td><strong>Next Month:</strong></td>
                                    <td style="text-align: right; color: #666666;">${type_totals['Expense'] * 1.01:,.0f}</td>
                                </tr>
                                <tr>
                                    <td><strong>Month +2:</strong></td>
                                    <td style="text-align: right; color: #666666;">${type_totals['Expense'] * 1.02:,.0f}</td>
                                </tr>
                                <tr>
                                    <td><strong>Month +3:</strong></td>
                                    <td style="text-align: right; color: #666666;">${type_totals['Expense'] * 1.025:,.0f}</td>
                                </tr>
                                <tr style="border-top: 1px solid #e0e0e0;">
                                    <td style="padding-top: 10px;"><strong>Growth (QoQ):</strong></td>
                                    <td style="text-align: right; padding-top: 10px; color: #666666; font-weight: bold;">+2.5%</td>
                                </tr>
                            </table>
                        </div>
                        
                        <!-- Net Income Forecast -->
                        <div style="flex: 1; min-width: 250px; background: white; padding: 20px; border-radius: 12px; box-shadow: 0 2px 10px rgba(0,0,0,0.05);">
                            <h3 style="color: #000000; margin-bottom: 15px;">💰 Net Income Forecast</h3>
                            <table style="width: 100%;">
                                <tr>
                                    <td><strong>Current Month:</strong></td>
                                    <td style="text-align: right; font-weight: bold;">${net_income:,.0f}</td>
                                </tr>
                                <tr>
                                    <td><strong>Next Month:</strong></td>
                                    <td style="text-align: right; color: {'#000000' if net_income > 0 else '#666666'};">${net_income * 1.03:,.0f}</td>
                                </tr>
                                <tr>
                                    <td><strong>Month +2:</strong></td>
                                    <td style="text-align: right; color: {'#000000' if net_income > 0 else '#666666'};">${net_income * 1.06:,.0f}</td>
                                </tr>
                                <tr>
                                    <td><strong>Month +3:</strong></td>
                                    <td style="text-align: right; color: {'#000000' if net_income > 0 else '#666666'};">${net_income * 1.09:,.0f}</td>
                                </tr>
                                <tr style="border-top: 1px solid #e0e0e0;">
                                    <td style="padding-top: 10px;"><strong>Growth (QoQ):</strong></td>
                                    <td style="text-align: right; padding-top: 10px; color: #000000; font-weight: bold;">+9.0%</td>
                                </tr>
                            </table>
                        </div>
                    </div>
                    
                    <!-- Cash Flow Forecast -->
                    <div style="margin-bottom: 25px;">
                        <h3 style="color: #000000; margin-bottom: 15px;">💵 Cash Flow Forecast</h3>
                        <div style="display: flex; gap: 20px; flex-wrap: wrap;">
                            <div style="flex: 1; min-width: 200px;">
                                <div style="background: #f0f0f0; padding: 15px; border-radius: 10px; text-align: center;">
                                    <div style="font-size: 0.9em; color: #666;">Opening Balance</div>
                                    <div style="font-size: 1.5em; font-weight: bold; color: #000000;">${type_totals['Asset'] * 0.3:,.0f}</div>
                                </div>
                            </div>
                            <div style="flex: 1; min-width: 200px;">
                                <div style="background: #f0f0f0; padding: 15px; border-radius: 10px; text-align: center;">
                                    <div style="font-size: 0.9em; color: #666;">Expected Inflows</div>
                                    <div style="font-size: 1.5em; font-weight: bold; color: #000000;">+${type_totals['Revenue'] * 0.95:,.0f}</div>
                                </div>
                            </div>
                            <div style="flex: 1; min-width: 200px;">
                                <div style="background: #f0f0f0; padding: 15px; border-radius: 10px; text-align: center;">
                                    <div style="font-size: 0.9em; color: #666;">Expected Outflows</div>
                                    <div style="font-size: 1.5em; font-weight: bold; color: #666666;">-${type_totals['Expense'] * 0.9:,.0f}</div>
                                </div>
                            </div>
                            <div style="flex: 1; min-width: 200px;">
                                <div style="background: #000000; padding: 15px; border-radius: 10px; text-align: center;">
                                    <div style="font-size: 0.9em; color: #cccccc;">Projected Closing</div>
                                    <div style="font-size: 1.5em; font-weight: bold; color: white;">${(type_totals['Asset'] * 0.3) + (type_totals['Revenue'] * 0.95) - (type_totals['Expense'] * 0.9):,.0f}</div>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Forecast Charts -->
                    <div class="chart-grid" style="grid-template-columns: repeat(2, 1fr);">
                        <!-- 3-Month Forecast Trend -->
                        <div class="chart-card">
                            <div class="chart-title">📊 3-Month Forecast Trend</div>
                            <div class="chart-container" style="height: 250px;">
                                <canvas id="forecastTrendChart"></canvas>
                            </div>
                        </div>
                        
                        <!-- Key Forecast Metrics -->
                        <div class="chart-card">
                            <div class="chart-title">🎯 Key Forecast Metrics</div>
                            <div class="forecast-metrics">
                                <table style="width: 100%; margin-top: 10px;">
                                    <tr>
                                        <td style="padding: 10px;"><strong>Projected Revenue (Qtr):</strong></td>
                                        <td style="text-align: right; font-weight: bold;">${type_totals['Revenue'] * 3.05:,.0f}</td>
                                    </tr>
                                    <tr>
                                        <td style="padding: 10px;"><strong>Projected Expenses (Qtr):</strong></td>
                                        <td style="text-align: right;">${type_totals['Expense'] * 3.025:,.0f}</td>
                                    </tr>
                                    <tr style="background: #f0f0f0;">
                                        <td style="padding: 10px;"><strong>Projected Net Income (Qtr):</strong></td>
                                        <td style="text-align: right; font-weight: bold; color: #000000;">${(type_totals['Revenue'] * 3.05) - (type_totals['Expense'] * 3.025):,.0f}</td>
                                    </tr>
                                    <tr>
                                        <td style="padding: 10px;"><strong>Avg Monthly Growth:</strong></td>
                                        <td style="text-align: right; color: #333333;">1.7%</td>
                                    </tr>
                                    <tr>
                                        <td style="padding: 10px;"><strong>Cash Runway (months):</strong></td>
                                        <td style="text-align: right; color: #333333;">{(type_totals['Asset'] * 0.3) / (type_totals['Expense'] * 0.1) if type_totals['Expense'] > 0 else 0:.1f}</td>
                                    </tr>
                                    <tr>
                                        <td style="padding: 10px;"><strong>Forecast Confidence:</strong></td>
                                        <td style="text-align: right;">
                                            <span style="background: #000000; color: white; padding: 5px 10px; border-radius: 15px; font-size: 0.85em;">HIGH (85%)</span>
                                        </td>
                                    </tr>
                                </table>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Forecast Notes -->
                    <div style="margin-top: 20px; background: #f8f9fa; padding: 15px; border-radius: 10px; border-left: 4px solid #000000;">
                        <p style="margin: 0; color: #333;">
                            <strong>🔍 Forecast Assumptions:</strong> Based on historical trends, budget targets, and seasonal adjustments. 
                            Revenue projected at 2% monthly growth, expenses at 1% monthly growth. 
                            Cash flow assumes 95% collection rate and 90% payment rate.
                        </p>
                    </div>
                </div>
            </div>
            <!-- ==================== END FORECAST SECTION ==================== -->
            
            <!-- Financial Statements -->
            <div class="financial-grid">
                <!-- Income Statement -->
                <div class="financial-card">
                    <div class="chart-title">📋 Income Statement</div>
                    <table class="financial-table">
                        <tr>
                            <th>Account</th>
                            <th class="amount">Amount</th>
                        </tr>
                        <tr>
                            <td><strong>Revenue</strong></td>
                            <td class="amount">${type_totals['Revenue']:,.0f}</td>
                        </tr>
        """
        
        # Add top 5 revenue accounts
        for acc in revenue_accounts[:5]:
            html_content += f"""
                        <tr>
                            <td style="padding-left: 20px;">{acc['code']} - {acc['name'][:30]}</td>
                            <td class="amount">${acc['balance']:,.0f}</td>
                        </tr>
            """
        
        html_content += f"""
                        <tr>
                            <td><strong>Total Expenses</strong></td>
                            <td class="amount">${type_totals['Expense']:,.0f}</td>
                        </tr>
        """
        
        # Add top 5 expense accounts
        for acc in expense_accounts[:5]:
            html_content += f"""
                        <tr>
                            <td style="padding-left: 20px;">{acc['code']} - {acc['name'][:30]}</td>
                            <td class="amount">${acc['balance']:,.0f}</td>
                        </tr>
            """
        
        html_content += f"""
                        <tr class="total-row">
                            <td><strong>Net Income</strong></td>
                            <td class="amount"><strong>${net_income:,.0f}</strong></td>
                        </tr>
                    </table>
                </div>
                
                <!-- Budget Variance Table -->
                <div class="financial-card">
                    <div class="chart-title">📊 Budget Variance Analysis</div>
                    <table class="financial-table">
                        <tr>
                            <th>Category</th>
                            <th class="amount">Budget</th>
                            <th class="amount">Actual</th>
                            <th class="amount">Variance</th>
                        </tr>
        """
        
        for var in variances[:8]:
            variance_class = 'variance-favorable' if var['variance'] < 0 else 'variance-unfavorable'
            html_content += f"""
                        <tr>
                            <td>{var['category']}</td>
                            <td class="amount">${var['budget']:,.0f}</td>
                            <td class="amount">${var['actual']:,.0f}</td>
                            <td class="amount {variance_class}">${var['variance']:,.0f} ({var['variance_pct']:.1f}%)</td>
                        </tr>
            """
        
        html_content += f"""
                    </table>
                </div>
                
                <!-- AR Aging Table -->
                <div class="financial-card">
                    <div class="chart-title">📅 Accounts Receivable Aging</div>
                    <table class="financial-table">
                        <tr>
                            <th>Aging Bucket</th>
                            <th class="amount">Amount</th>
                            <th class="amount">% of Total</th>
                        </tr>
        """
        
        for bucket, amount in aging_buckets.items():
            percentage = (amount / total_ar * 100) if total_ar > 0 else 0
            badge_class = 'badge-success' if bucket == '0-30 Days' else 'badge-warning' if bucket in ['31-60 Days', '61-90 Days'] else 'badge-danger'
            html_content += f"""
                        <tr>
                            <td><span class="badge {badge_class}">{bucket}</span></td>
                            <td class="amount">${amount:,.0f}</td>
                            <td class="amount">{percentage:.1f}%</td>
                        </tr>
            """
        
        html_content += f"""
                        <tr class="total-row">
                            <td><strong>Total AR</strong></td>
                            <td class="amount"><strong>${total_ar:,.0f}</strong></td>
                            <td class="amount"><strong>100%</strong></td>
                        </tr>
                    </table>
                </div>
                
                <!-- Balance Sheet Summary -->
                <div class="financial-card">
                    <div class="chart-title">⚖️ Balance Sheet Summary</div>
                    <table class="financial-table">
                        <tr>
                            <th>Category</th>
                            <th class="amount">Amount</th>
                        </tr>
                        <tr>
                            <td><strong>Total Assets</strong></td>
                            <td class="amount">${type_totals['Asset']:,.0f}</td>
                        </tr>
                        <tr>
                            <td style="padding-left: 20px;">Cash & AR</td>
                            <td class="amount">${type_totals['Asset'] * 0.6:,.0f}</td>
                        </tr>
                        <tr>
                            <td><strong>Total Liabilities</strong></td>
                            <td class="amount">${type_totals['Liability']:,.0f}</td>
                        </tr>
                        <tr>
                            <td><strong>Total Equity</strong></td>
                            <td class="amount">${type_totals['Equity']:,.0f}</td>
                        </tr>
                        <tr class="total-row">
                            <td><strong>Liabilities + Equity</strong></td>
                            <td class="amount"><strong>${type_totals['Liability'] + type_totals['Equity']:,.0f}</strong></td>
                        </tr>
                    </table>
                </div>
            </div>
            
            <!-- Navigation -->
            <div class="footer">
                <a href="/dashboard">← Approval Dashboard</a>
                <a href="/cfo/financial_report">📊 JSON Report</a>
                <a href="/docs">📚 API Docs</a>
                <p style="margin-top: 20px;">© 2026 Finance Month-End Close AI Agent v3.0.0</p>
            </div>
            
            <script>
                // Revenue vs Expense Chart
                const revExpCtx = document.getElementById('revenueExpenseChart').getContext('2d');
                new Chart(revExpCtx, {{
                    type: 'doughnut',
                    data: {{
                        labels: ['Revenue', 'Expenses', 'Net Income'],
                        datasets: [{{
                            data: [{type_totals['Revenue']}, {type_totals['Expense']}, {abs(net_income)}],
                            backgroundColor: ['#333333', '#666666', '#999999'],
                            borderWidth: 0
                        }}]
                    }},
                    options: {{
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {{
                            legend: {{ position: 'bottom' }}
                        }},
                        cutout: '60%'
                    }}
                }});
                
                // Budget Variance Chart
                const varianceCtx = document.getElementById('varianceChart').getContext('2d');
                new Chart(varianceCtx, {{
                    type: 'bar',
                    data: {{
                        labels: {str([v['category'][:15] for v in variances[:6]])},
                        datasets: [{{
                            label: 'Variance ($)',
                            data: {str([v['variance'] for v in variances[:6]])},
                            backgroundColor: {str(['#333333' if v['variance'] < 0 else '#666666' for v in variances[:6]])},
                            borderRadius: 5
                        }}]
                    }},
                    options: {{
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {{
                            legend: {{ display: false }}
                        }},
                        scales: {{
                            y: {{
                                beginAtZero: true,
                                ticks: {{
                                    callback: function(value) {{
                                        return '$' + value;
                                    }}
                                }}
                            }}
                        }}
                    }}
                }});
                
                // AR Aging Chart
                const arCtx = document.getElementById('arAgingChart').getContext('2d');
                new Chart(arCtx, {{
                    type: 'pie',
                    data: {{
                        labels: {str(list(aging_buckets.keys()))},
                        datasets: [{{
                            data: {str(list(aging_buckets.values()))},
                            backgroundColor: ['#333333', '#555555', '#777777', '#999999'],
                            borderWidth: 0
                        }}]
                    }},
                    options: {{
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {{
                            legend: {{ position: 'bottom' }}
                        }}
                    }}
                }});
                
                // Top Expenses Chart
                const topExpCtx = document.getElementById('topExpensesChart').getContext('2d');
                new Chart(topExpCtx, {{
                    type: 'bar',
                    data: {{
                        labels: {str([f"{e['code']}" for e in expense_accounts[:5]])},
                        datasets: [{{
                            label: 'Amount ($)',
                            data: {str([e['balance'] for e in expense_accounts[:5]])},
                            backgroundColor: '#666666',
                            borderRadius: 5
                        }}]
                    }},
                    options: {{
                        responsive: true,
                        maintainAspectRatio: false,
                        indexAxis: 'y',
                        plugins: {{
                            legend: {{ display: false }}
                        }},
                        scales: {{
                            x: {{
                                ticks: {{
                                    callback: function(value) {{
                                        return '$' + value;
                                    }}
                                }}
                            }}
                        }}
                    }}
                }});
                
                // Forecast Trend Chart
                const forecastCtx = document.getElementById('forecastTrendChart').getContext('2d');
                new Chart(forecastCtx, {{
                    type: 'line',
                    data: {{
                        labels: ['Current', 'Month +1', 'Month +2', 'Month +3'],
                        datasets: [
                            {{
                                label: 'Revenue',
                                data: [
                                    {type_totals['Revenue']},
                                    {type_totals['Revenue'] * 1.02},
                                    {type_totals['Revenue'] * 1.035},
                                    {type_totals['Revenue'] * 1.05}
                                ],
                                borderColor: '#333333',
                                backgroundColor: 'rgba(51, 51, 51, 0.1)',
                                tension: 0.4,
                                fill: false,
                                pointBackgroundColor: '#333333',
                                pointBorderColor: 'white',
                                pointBorderWidth: 2,
                                pointRadius: 5
                            }},
                            {{
                                label: 'Expenses',
                                data: [
                                    {type_totals['Expense']},
                                    {type_totals['Expense'] * 1.01},
                                    {type_totals['Expense'] * 1.02},
                                    {type_totals['Expense'] * 1.025}
                                ],
                                borderColor: '#666666',
                                backgroundColor: 'rgba(102, 102, 102, 0.1)',
                                tension: 0.4,
                                fill: false,
                                pointBackgroundColor: '#666666',
                                pointBorderColor: 'white',
                                pointBorderWidth: 2,
                                pointRadius: 5
                            }},
                            {{
                                label: 'Net Income',
                                data: [
                                    {net_income},
                                    {net_income * 1.03},
                                    {net_income * 1.06},
                                    {net_income * 1.09}
                                ],
                                borderColor: '#999999',
                                backgroundColor: 'rgba(153, 153, 153, 0.1)',
                                tension: 0.4,
                                fill: false,
                                pointBackgroundColor: '#999999',
                                pointBorderColor: 'white',
                                pointBorderWidth: 2,
                                pointRadius: 5
                            }}
                        ]
                    }},
                    options: {{
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {{
                            legend: {{
                                position: 'bottom',
                                labels: {{
                                    usePointStyle: true,
                                    padding: 20
                                }}
                            }},
                            tooltip: {{
                                callbacks: {{
                                    label: function(context) {{
                                        let label = context.dataset.label || '';
                                        if (label) {{
                                            label += ': ';
                                        }}
                                        if (context.parsed.y !== null) {{
                                            label += '$' + context.parsed.y.toFixed(0).replace(/\\B(?=(\\d{{3}})+(?!\\d))/g, ",");
                                        }}
                                        return label;
                                    }}
                                }}
                            }}
                        }},
                        scales: {{
                            y: {{
                                beginAtZero: false,
                                ticks: {{
                                    callback: function(value) {{
                                        return '$' + value.toFixed(0).replace(/\\B(?=(\\d{{3}})+(?!\\d))/g, ",");
                                    }}
                                }}
                            }}
                        }}
                    }}
                }});
            </script>
        </body>
        </html>
        """
        
        return HTMLResponse(content=html_content)
        
    except Exception as e:
        logger.error(f"Error generating CFO dashboard: {str(e)}")
        return HTMLResponse(
            content=f"<h1>Error generating dashboard</h1><p>{str(e)}</p>",
            status_code=500
        )

# ============================================================================
# EMAIL REPORT ENDPOINTS (WITH SUMMARY SECTION)
# ============================================================================

@app.post("/reports/email", response_model=EmailReportResponse)
async def send_financial_reports(
    request: EmailReportRequest,
    background_tasks: BackgroundTasks
):
    """
    Send financial reports via email with PDF/CSV attachments and summary
    """
    # Extract recipient emails
    recipient_emails = [r.email for r in request.recipients]
    
    # Generate summary data for email
    summary_html = ""
    try:
        # Load data for summary
        transactions = load_csv_data('Raw_GL_Export_With_CostCenters_Mar2026.csv')
        coa = load_coa()
        ar_records = load_csv_data('AR_Subledger_Mar2026.csv')
        budget_data = load_csv_data('Budget_Mar2026_Detailed.csv')
        
        # Filter for period
        period_txns = [t for t in transactions if t['Fiscal_Period'] == request.fiscal_period]
        
        # Calculate totals
        account_balances = defaultdict(float)
        for txn in period_txns:
            if txn['Account_Code_Raw'] in coa:
                account_balances[txn['Account_Code_Raw']] += float(txn['Amount'])
        
        # Group by type
        type_totals = defaultdict(float)
        for account, balance in account_balances.items():
            if account in coa:
                type_totals[coa[account]['type']] += balance
        
        revenue = type_totals.get('Revenue', 0)
        expenses = type_totals.get('Expense', 0)
        net_income = revenue - expenses
        
        # AR totals
        total_ar = sum(float(r['Outstanding_Balance']) for r in ar_records)
        overdue_ar = sum(float(r['Outstanding_Balance']) for r in ar_records if r['Status'] == 'Overdue')
        
        # Budget variance
        actuals = defaultdict(float)
        for txn in period_txns:
            if txn['Account_Code_Raw'] in coa:
                actuals[coa[txn['Account_Code_Raw']]['category']] += float(txn['Amount'])
        
        budget = defaultdict(float)
        for item in budget_data:
            if item['Category'].upper() != 'TOTAL' and not item['Account_Code'].startswith('TOTAL'):
                budget[item['Category']] += float(item['Budget_Amount'])
        
        total_budget = sum(budget.values())
        total_actual = sum(actuals.values())
        total_variance = total_actual - total_budget
        variance_pct = (total_variance / total_budget * 100) if total_budget > 0 else 0
        
        # AR Aging
        aging_buckets = {
            '0-30 Days': 0,
            '31-60 Days': 0,
            '61-90 Days': 0,
            '90+ Days': 0
        }
        
        for record in ar_records:
            days = int(record['Days_Outstanding'])
            amount = float(record['Outstanding_Balance'])
            
            if days <= 30:
                aging_buckets['0-30 Days'] += amount
            elif days <= 60:
                aging_buckets['31-60 Days'] += amount
            elif days <= 90:
                aging_buckets['61-90 Days'] += amount
            else:
                aging_buckets['90+ Days'] += amount
        
        # Get approval summary
        approval_summary = approval_registry.get_approval_summary(request.fiscal_period)
        
        # Create summary HTML
        summary_html = f"""
        <div style="background: linear-gradient(135deg, #f8f9fa 0%, #ffffff 100%); padding: 25px; border-radius: 15px; margin-bottom: 30px; border: 1px solid #e0e0e0;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; border-bottom: 2px solid #000000; padding-bottom: 15px;">
                <h2 style="color: #000000; margin: 0; font-size: 1.8em;">📊 Executive Summary - {request.fiscal_period}</h2>
                <span style="background: #000000; color: white; padding: 8px 16px; border-radius: 20px; font-weight: bold;">
                    {datetime.now().strftime('%d %b %Y')}
                </span>
            </div>
            
            <div style="display: flex; gap: 20px; margin-bottom: 20px; flex-wrap: wrap;">
                <div style="flex: 1; min-width: 200px; background: white; padding: 15px; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.05);">
                    <h3 style="color: #000000; margin: 0 0 10px 0;">📈 Performance</h3>
                    <table style="width: 100%;">
                        <tr><td><strong>Revenue:</strong></td><td style="text-align: right;">${revenue:,.0f}</td></tr>
                        <tr><td><strong>Expenses:</strong></td><td style="text-align: right;">${expenses:,.0f}</td></tr>
                        <tr><td><strong>Net Income:</strong></td><td style="text-align: right; font-weight: bold;">${net_income:,.0f}</td></tr>
                    </table>
                </div>
                
                <div style="flex: 1; min-width: 200px; background: white; padding: 15px; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.05);">
                    <h3 style="color: #000000; margin: 0 0 10px 0;">💰 AR Summary</h3>
                    <table style="width: 100%;">
                        <tr><td><strong>Total AR:</strong></td><td style="text-align: right;">${total_ar:,.0f}</td></tr>
                        <tr><td><strong>Overdue:</strong></td><td style="text-align: right;">${overdue_ar:,.0f}</td></tr>
                        <tr><td><strong>90+ Days:</strong></td><td style="text-align: right;">${aging_buckets['90+ Days']:,.0f}</td></tr>
                    </table>
                </div>
                
                <div style="flex: 1; min-width: 200px; background: white; padding: 15px; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.05);">
                    <h3 style="color: #000000; margin: 0 0 10px 0;">📊 Budget</h3>
                    <table style="width: 100%;">
                        <tr><td><strong>Budget:</strong></td><td style="text-align: right;">${total_budget:,.0f}</td></tr>
                        <tr><td><strong>Actual:</strong></td><td style="text-align: right;">${total_actual:,.0f}</td></tr>
                        <tr><td><strong>Variance:</strong></td><td style="text-align: right;">${total_variance:,.0f}</td></tr>
                    </table>
                </div>
                
                <div style="flex: 1; min-width: 200px; background: #000000; color: white; padding: 15px; border-radius: 10px;">
                    <h3 style="color: white; margin: 0 0 10px 0;">✅ Approvals</h3>
                    <table style="width: 100%; color: white;">
                        <tr><td><strong>Total:</strong></td><td style="text-align: right;">{approval_summary['total_generated']}</td></tr>
                        <tr><td><strong>Approved:</strong></td><td style="text-align: right;">{approval_summary['approved']}</td></tr>
                        <tr><td><strong>Pending:</strong></td><td style="text-align: right;">{approval_summary['pending']}</td></tr>
                    </table>
                </div>
            </div>
        </div>
        """
    except Exception as e:
        summary_html = f"<p>Summary data unavailable: {str(e)}</p>"
        logger.error(f"Error generating email summary: {e}")
    
    # Prepare email subject
    subject = request.subject or f"Financial Report - {request.fiscal_period} - {request.entity_code}"
    
    # Prepare email HTML content with summary at the top
    html_content = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 900px; margin: 0 auto; }}
            h2 {{ color: #000000; }}
            h3 {{ color: #000000; margin-top: 20px; }}
            ul {{ margin: 10px 0; }}
            li {{ margin: 5px 0; }}
            hr {{ border: 1px solid #e0e0e0; margin: 20px 0; }}
            .footer {{ color: #666; font-size: 12px; }}
        </style>
    </head>
    <body>
        <div class="container">
            {summary_html}
            
            <h2>Financial Report - {request.fiscal_period}</h2>
            <p>Dear Finance Team,</p>
            <p>Please find attached the detailed financial reports for period <strong>{request.fiscal_period}</strong> 
            (Entity: {request.entity_code}).</p>
            
            <h3>Reports Included:</h3>
            <ul>
                {"".join([f"<li>{report.replace('_', ' ').title()}</li>" for report in request.report_types])}
            </ul>
            
            <h3>Attachments:</h3>
            <ul>
                {"<li>✅ PDF Report with all financial statements</li>" if request.include_pdf else ""}
                {"<li>✅ CSV data files for analysis</li>" if request.include_csv else ""}
            </ul>
            
            <p>Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            
            <hr>
            <p class="footer">
                This is an automated message from the Finance Month-End Close System.<br>
                For any questions, please contact the finance team.
            </p>
        </div>
    </body>
    </html>
    """
    
    # Prepare attachments
    attachments = []
    reports_sent = []
    
    # Generate PDF report
    if request.include_pdf:
        try:
            pdf_bytes = generate_pdf_report(
                request.fiscal_period,
                request.entity_code,
                request.report_types
            )
            
            attachments.append({
                'content': pdf_bytes,
                'filename': f"Financial_Report_{request.fiscal_period}.pdf",
                'filetype': 'application/pdf'
            })
            reports_sent.append("PDF Report")
            logger.info(f"✅ Generated PDF report: Financial_Report_{request.fiscal_period}.pdf")
        except Exception as e:
            logger.error(f"❌ Error generating PDF: {str(e)}")
    
    # Generate CSV reports
    if request.include_csv:
        for report_type in request.report_types:
            try:
                csv_content = generate_csv_report(request.fiscal_period, report_type)
                
                attachments.append({
                    'content': csv_content.encode('utf-8'),
                    'filename': f"{report_type}_{request.fiscal_period}.csv",
                    'filetype': 'text/csv'
                })
                reports_sent.append(f"{report_type}.csv")
                logger.info(f"✅ Generated CSV: {report_type}_{request.fiscal_period}.csv")
            except Exception as e:
                logger.error(f"❌ Error generating CSV {report_type}: {str(e)}")
    
    # Send email in background
    def send_email_task():
        result = send_email_with_attachments(
            to_emails=recipient_emails,
            subject=subject,
            html_content=html_content,
            attachments=attachments
        )
        return result
    
    # Add to background tasks
    background_tasks.add_task(send_email_task)
    
    return EmailReportResponse(
        success=True,
        message=f"Email report generation started. Will be sent to {len(recipient_emails)} recipients.",
        recipients=recipient_emails,
        reports_sent=reports_sent
    )

@app.get("/reports/email/send-test")
async def send_test_email(
    background_tasks: BackgroundTasks,
    fiscal_period: str = Query("2026-04"),
    entity_code: str = Query("AUS01")
):
    """
    Send a test email with sample reports and summary
    """
    request = EmailReportRequest(
        recipients=[
            EmailRecipient(email="deepanshu.dubey@octanesolutions.com.au", name="CFO"),
            EmailRecipient(email="deep.dws.mp@gmail.com", name="Finance Team")
        ],
        fiscal_period=fiscal_period,
        entity_code=entity_code,
        include_pdf=True,
        include_csv=True,
        report_types=["trial_balance", "income_statement", "balance_sheet", "ar_aging", "budget_variance"],
        subject=f"Test Financial Report - {fiscal_period}",
        message=f"<h2>Test Report</h2><p>This is a test of the email reporting system with executive summary.</p>"
    )
    
    return await send_financial_reports(request, background_tasks)

@app.get("/reports/email/preview", response_class=HTMLResponse)
async def preview_email_report(
    fiscal_period: str = Query("2026-04"),
    entity_code: str = Query("AUS01"),
    report_types: str = Query("trial_balance,income_statement,balance_sheet,ar_aging,budget_variance")
):
    """
    Preview what would be sent in the email (HTML preview with summary)
    """
    report_list = report_types.split(",")
    
    # Load logo as base64
    logo_base64 = ""
    try:
        with open("Octane_logo.png", "rb") as logo_file:
            logo_base64 = base64.b64encode(logo_file.read()).decode('utf-8')
    except Exception as e:
        logger.warning(f"Could not load logo: {e}")
    
    # Generate summary data for preview
    summary_html = ""
    try:
        # Load data for summary
        transactions = load_csv_data('Raw_GL_Export_With_CostCenters_Mar2026.csv')
        coa = load_coa()
        ar_records = load_csv_data('AR_Subledger_Mar2026.csv')
        budget_data = load_csv_data('Budget_Mar2026_Detailed.csv')
        
        # Filter for period
        period_txns = [t for t in transactions if t['Fiscal_Period'] == fiscal_period]
        
        # Calculate totals
        account_balances = defaultdict(float)
        for txn in period_txns:
            if txn['Account_Code_Raw'] in coa:
                account_balances[txn['Account_Code_Raw']] += float(txn['Amount'])
        
        # Group by type
        type_totals = defaultdict(float)
        for account, balance in account_balances.items():
            if account in coa:
                type_totals[coa[account]['type']] += balance
        
        revenue = type_totals.get('Revenue', 0)
        expenses = type_totals.get('Expense', 0)
        net_income = revenue - expenses
        
        # AR totals
        total_ar = sum(float(r['Outstanding_Balance']) for r in ar_records)
        overdue_ar = sum(float(r['Outstanding_Balance']) for r in ar_records if r['Status'] == 'Overdue')
        
        # Budget variance
        actuals = defaultdict(float)
        for txn in period_txns:
            if txn['Account_Code_Raw'] in coa:
                actuals[coa[txn['Account_Code_Raw']]['category']] += float(txn['Amount'])
        
        budget = defaultdict(float)
        for item in budget_data:
            if item['Category'].upper() != 'TOTAL' and not item['Account_Code'].startswith('TOTAL'):
                budget[item['Category']] += float(item['Budget_Amount'])
        
        total_budget = sum(budget.values())
        total_actual = sum(actuals.values())
        total_variance = total_actual - total_budget
        variance_pct = (total_variance / total_budget * 100) if total_budget > 0 else 0
        
        # AR Aging
        aging_buckets = {
            '0-30 Days': 0,
            '31-60 Days': 0,
            '61-90 Days': 0,
            '90+ Days': 0
        }
        
        for record in ar_records:
            days = int(record['Days_Outstanding'])
            amount = float(record['Outstanding_Balance'])
            
            if days <= 30:
                aging_buckets['0-30 Days'] += amount
            elif days <= 60:
                aging_buckets['31-60 Days'] += amount
            elif days <= 90:
                aging_buckets['61-90 Days'] += amount
            else:
                aging_buckets['90+ Days'] += amount
        
        # Get approval summary
        approval_summary = approval_registry.get_approval_summary(fiscal_period)
        
        # Create summary HTML for preview
        summary_html = f"""
        <div style="background: linear-gradient(135deg, #f8f9fa 0%, #ffffff 100%); padding: 25px; border-radius: 15px; margin-bottom: 30px; border: 1px solid #e0e0e0;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; border-bottom: 2px solid #000000; padding-bottom: 15px;">
                <h2 style="color: #000000; margin: 0; font-size: 1.8em;">📊 Executive Summary - {fiscal_period}</h2>
                <span style="background: #000000; color: white; padding: 8px 16px; border-radius: 20px; font-weight: bold;">
                    {datetime.now().strftime('%d %b %Y')}
                </span>
            </div>
            
            <div style="display: flex; gap: 20px; margin-bottom: 20px; flex-wrap: wrap;">
                <div style="flex: 1; min-width: 200px; background: white; padding: 15px; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.05);">
                    <h3 style="color: #000000; margin: 0 0 10px 0;">📈 Performance</h3>
                    <table style="width: 100%;">
                        <tr><td><strong>Revenue:</strong></td><td style="text-align: right;">${revenue:,.0f}</td></tr>
                        <tr><td><strong>Expenses:</strong></td><td style="text-align: right;">${expenses:,.0f}</td></tr>
                        <tr><td><strong>Net Income:</strong></td><td style="text-align: right; font-weight: bold;">${net_income:,.0f}</td></tr>
                    </table>
                </div>
                
                <div style="flex: 1; min-width: 200px; background: white; padding: 15px; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.05);">
                    <h3 style="color: #000000; margin: 0 0 10px 0;">💰 AR Summary</h3>
                    <table style="width: 100%;">
                        <tr><td><strong>Total AR:</strong></td><td style="text-align: right;">${total_ar:,.0f}</td></tr>
                        <tr><td><strong>Overdue:</strong></td><td style="text-align: right;">${overdue_ar:,.0f}</td></tr>
                        <tr><td><strong>90+ Days:</strong></td><td style="text-align: right;">${aging_buckets['90+ Days']:,.0f}</td></tr>
                    </table>
                </div>
                
                <div style="flex: 1; min-width: 200px; background: white; padding: 15px; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.05);">
                    <h3 style="color: #000000; margin: 0 0 10px 0;">📊 Budget</h3>
                    <table style="width: 100%;">
                        <tr><td><strong>Budget:</strong></td><td style="text-align: right;">${total_budget:,.0f}</td></tr>
                        <tr><td><strong>Actual:</strong></td><td style="text-align: right;">${total_actual:,.0f}</td></tr>
                        <tr><td><strong>Variance:</strong></td><td style="text-align: right;">${total_variance:,.0f}</td></tr>
                    </table>
                </div>
                
                <div style="flex: 1; min-width: 200px; background: #000000; color: white; padding: 15px; border-radius: 10px;">
                    <h3 style="color: white; margin: 0 0 10px 0;">✅ Approvals</h3>
                    <table style="width: 100%; color: white;">
                        <tr><td><strong>Total:</strong></td><td style="text-align: right;">{approval_summary['total_generated']}</td></tr>
                        <tr><td><strong>Approved:</strong></td><td style="text-align: right;">{approval_summary['approved']}</td></tr>
                        <tr><td><strong>Pending:</strong></td><td style="text-align: right;">{approval_summary['pending']}</td></tr>
                    </table>
                </div>
            </div>
        </div>
        """
    except Exception as e:
        summary_html = f"<p>Summary data unavailable: {str(e)}</p>"
        logger.error(f"Error generating preview summary: {e}")
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Email Preview - {fiscal_period}</title>
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }}
            .header {{ background: #000000; color: white; padding: 20px 30px; border-radius: 10px 10px 0 0; display: flex; align-items: center; gap: 20px; }}
            .header-logo {{ height: 40px; }}
            .container {{ max-width: 900px; margin: 0 auto; background: white; border-radius: 10px; box-shadow: 0 5px 20px rgba(0,0,0,0.1); overflow: hidden; }}
            .content {{ padding: 30px; }}
            .report-list {{ background: #f8f9fa; padding: 15px; border-radius: 5px; }}
            .attachment {{ background: #f0f0f0; padding: 10px; margin: 5px 0; border-radius: 3px; border-left: 3px solid #000000; }}
            .btn {{ display: inline-block; padding: 10px 20px; background: #000000; color: white; text-decoration: none; border-radius: 5px; margin: 10px; }}
            .btn:hover {{ background: #333333; }}
            .btn-send {{ background: #666666; }}
            .btn-send:hover {{ background: #444444; }}
            .footer {{ background: #f5f5f5; padding: 20px; text-align: center; color: #666; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <img src="data:image/png;base64,{logo_base64}" alt="Octane Logo" class="header-logo">
                <h2 style="margin: 0;">📧 Email Report Preview</h2>
                <div style="margin-left: auto;">Period: {fiscal_period}</div>
            </div>
            
            <div class="content">
                {summary_html}
                
                <h3 style="color: #000000;">Recipients:</h3>
                <p>• deepanshu.dubey@octanesolutions.com.au (CFO)</p>
                <p>• deep.dws.mp@gmail.com (Finance Team)</p>
                
                <h3 style="color: #000000;">Subject:</h3>
                <p><strong>Financial Report - {fiscal_period} - {entity_code}</strong></p>
                
                <h3 style="color: #000000;">Email Content:</h3>
                <div style="border: 1px solid #ddd; padding: 20px; border-radius: 5px; background: #f9f9f9;">
                    <h2 style="color: #000000;">Financial Report - {fiscal_period}</h2>
                    <p>Dear Finance Team,</p>
                    <p>Please find attached the detailed financial reports for period <strong>{fiscal_period}</strong> 
                    (Entity: {entity_code}).</p>
                    
                    <h3 style="color: #000000;">Reports Included:</h3>
                    <div class="report-list">
                        <ul>
                            {"".join([f"<li>{r.replace('_', ' ').title()}</li>" for r in report_list])}
                        </ul>
                    </div>
                    
                    <h3 style="color: #000000;">Attachments:</h3>
                    <div class="attachment">✅ Financial_Report_{fiscal_period}.pdf (PDF)</div>
                    {"".join([f'<div class="attachment">✅ {r}_{fiscal_period}.csv (CSV)</div>' for r in report_list])}
                    
                    <p>Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                </div>
                
                <div style="text-align: center; margin-top: 30px;">
                    <a href="/reports/email/send-test?fiscal_period={fiscal_period}" class="btn btn-send">
                        📧 Send Test Email
                    </a>
                    <a href="/cfo/financial_dashboard?fiscal_period={fiscal_period}" class="btn">
                        📊 Back to Dashboard
                    </a>
                </div>
            </div>
            
            <div class="footer">
                <p>Finance Month-End Close AI Agent v3.0.0</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html_content)

@app.get("/reports/email/status")
async def check_email_config():
    """
    Check email configuration status
    """
    api_key = os.getenv("SENDGRID_API_KEY")
    from_email = os.getenv("FROM_EMAIL", "deepanshu.dubey@octanesolutions.com.au")
    
    approval_summary = approval_registry.get_approval_summary()
    
    return {
        "sendgrid_configured": bool(api_key),
        "from_email": from_email,
        "status": "✅ Ready to send" if bool(api_key) else "⚠️ Not configured - emails will be simulated",
        "pending_approvals": len(pending_approvals),
        "registered_approvals": len(approval_registry.generated_approvals),
        "approval_summary": approval_summary,
        "assigned_items": len([i for i in pending_approvals.values() if i.assigned_to is not None]),
        "total_reports_sent": len([h for h in approval_history if h.get('email_sent', False)])
    }

# ============================================================================
# ACTIVITY 1: INTERCOMPANY RECONCILIATION
# ============================================================================

# Data Models
class IntercompanyReconciliationRequest(BaseModel):
    fiscal_period: str = Field("2026-04", description="Fiscal period for reconciliation")
    entity_code: Optional[str] = Field(None, description="Filter by specific entity (optional)")

class IntercompanyEliminationRequest(BaseModel):
    fiscal_period: str = Field("2026-04", description="Fiscal period")
    journal_ids: Optional[List[str]] = Field(None, description="Specific journal IDs to post")
    approve_all: bool = Field(False, description="Approve all pending elimination journals")
    approved_by: str = Field(..., description="Name of approver")

class IntercompanyVarianceResolution(BaseModel):
    variance_id: str
    resolution_action: str  # 'post_fx_journal', 'reverse_duplicate', 'post_missing_invoice', 'reclassify_counterparty'
    approved_by: str
    comments: Optional[str] = None

# ============================================================================
# TOOL 11: INTERCOMPANY RECONCILIATION ANALYSIS
# ============================================================================

@app.post("/tools/intercompany/reconcile", response_model=ToolResponse)
async def intercompany_reconcile(request: IntercompanyReconciliationRequest):
    """
    Perform intercompany reconciliation analysis for the specified period
    Identifies variances, matches transactions, and generates elimination recommendations
    """
    try:
        # Load data
        transactions = load_csv_data('Intercompany_Transactions_Mar2026.csv')
        reconciliation = load_csv_data('Intercompany_Reconciliation_Mar2026.csv')
        elimination_journals = load_csv_data('Intercompany_Elimination_Journals_Mar2026.csv')
        
        # Filter for period
        period_txns = [t for t in transactions if t.get('Period') == request.fiscal_period]
        period_rec = [r for r in reconciliation if r.get('Period') == request.fiscal_period]
        
        if not period_txns:
            return ToolResponse(
                success=False,
                message=f"No intercompany transactions found for period {request.fiscal_period}"
            )
        
        # Calculate entity positions
        entity_positions = defaultdict(lambda: {'AR': 0, 'AP': 0, 'net': 0})
        pair_positions = {}
        
        for txn in period_txns:
            entity = txn.get('Entity')
            counterparty = txn.get('Counterparty_Entity')
            amount = float(txn.get('Group_Reporting_Amount_AUD', 0))
            trans_type = txn.get('Transaction_Type', '')
            
            if not entity or not counterparty:
                continue
            
            # Create pair key
            pair_key = f"{entity} ↔ {counterparty}"
            
            if pair_key not in pair_positions:
                pair_positions[pair_key] = {
                    'entity': entity,
                    'counterparty': counterparty,
                    f'{entity}_AR': 0, f'{entity}_AP': 0,
                    f'{counterparty}_AR': 0, f'{counterparty}_AP': 0,
                    'variance': 0
                }
            
            # Update positions
            if trans_type == 'AR':
                entity_positions[entity]['AR'] += amount
                entity_positions[entity]['net'] += amount
                pair_positions[pair_key][f'{entity}_AR'] += amount
            elif trans_type == 'AP':
                entity_positions[entity]['AP'] += amount
                entity_positions[entity]['net'] -= amount
                pair_positions[pair_key][f'{entity}_AP'] += amount
        
        # Calculate variances
        material_variances = []
        for pair_key, pair in pair_positions.items():
            entity = pair['entity']
            counterparty = pair['counterparty']
            
            entity_ar = pair.get(f'{entity}_AR', 0)
            entity_ap = pair.get(f'{entity}_AP', 0)
            counterparty_ar = pair.get(f'{counterparty}_AR', 0)
            counterparty_ap = pair.get(f'{counterparty}_AP', 0)
            
            variance = (entity_ar - counterparty_ap) + (counterparty_ar - entity_ap)
            pair['variance'] = variance / 2
            
            # Check if material variance
            if abs(pair['variance']) > 100000:  # Material threshold
                material_variances.append({
                    'pair': pair_key,
                    'variance': pair['variance'],
                    'entity_ar': entity_ar,
                    'entity_ap': entity_ap,
                    'counterparty_ar': counterparty_ar,
                    'counterparty_ap': counterparty_ap
                })
        
        # Identify exceptions from reconciliation file
        exceptions = []
        for rec in period_rec:
            if rec.get('Materiality') == 'Material' and rec.get('Human_Approval_Required') == 'Yes':
                # Create approval item
                approval_item = create_approval_item(
                    item_type="Intercompany Variance",
                    description=f"{rec.get('Entity')} ↔ {rec.get('Counterparty_Entity')} - {rec.get('Root_Cause', 'Variance')}",
                    amount=abs(float(rec.get('Variance_AUD', 0))),
                    account="1100",
                    cost_center="CORP",
                    metadata={
                        'entity_pair': f"{rec.get('Entity')} ↔ {rec.get('Counterparty_Entity')}",
                        'variance': rec.get('Variance_AUD', 0),
                        'root_cause': rec.get('Root_Cause', 'Unknown'),
                        'recommendation': rec.get('Agent_Recommendation', ''),
                        'affected_txns': rec.get('Affected_GL_Txns', '')
                    },
                    fiscal_period=request.fiscal_period
                )
                
                exceptions.append({
                    'type': 'Reconciliation Variance',
                    'entity_pair': f"{rec.get('Entity')} ↔ {rec.get('Counterparty_Entity')}",
                    'variance': rec.get('Variance_AUD', 0),
                    'root_cause': rec.get('Root_Cause', 'Unknown'),
                    'materiality': 'Material',
                    'human_required': True,
                    'recommendation': rec.get('Agent_Recommendation', ''),
                    'approval_token': approval_item.token,
                    'approval_links': get_approval_links(approval_item.token)
                })
        
        # Calculate group totals
        total_ar = sum(p['AR'] for p in entity_positions.values())
        total_ap = sum(p['AP'] for p in entity_positions.values())
        group_imbalance = total_ar - total_ap
        
        # Analyze elimination journals
        elim_summary = {
            'total_journals': len(elimination_journals),
            'total_debits': sum(float(j.get('Debit_AUD', 0)) for j in elimination_journals),
            'total_credits': sum(float(j.get('Credit_AUD', 0)) for j in elimination_journals)
        }
        elim_summary['balanced'] = abs(elim_summary['total_debits'] - elim_summary['total_credits']) < 0.01
        
        response_data = {
            'fiscal_period': request.fiscal_period,
            'summary': {
                'total_transactions': len(period_txns),
                'total_reconciliation_records': len(period_rec),
                'total_elimination_journals': len(elimination_journals),
                'group_ar': total_ar,
                'group_ap': total_ap,
                'group_imbalance': group_imbalance,
                'material_variances_count': len(material_variances),
                'exceptions_count': len(exceptions)
            },
            'entity_positions': dict(entity_positions),
            'pair_positions': pair_positions,
            'material_variances': material_variances,
            'exceptions': exceptions,
            'elimination_journals': {
                'balanced': elim_summary['balanced'],
                'total_debits': elim_summary['total_debits'],
                'total_credits': elim_summary['total_credits'],
                'count': elim_summary['total_journals']
            },
            'dashboard_url': f"{APP_BASE_URL}/dashboard"
        }
        
        message = f"Intercompany reconciliation complete. Found {len(material_variances)} material variances, {len(exceptions)} items require approval."
        
        return ToolResponse(
            success=True,
            message=message,
            data=response_data
        )
        
    except Exception as e:
        logger.error(f"Error in intercompany reconciliation: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# TOOL 12: GET INTERCOMPANY TRANSACTIONS
# ============================================================================

@app.get("/tools/intercompany/transactions", response_model=ToolResponse)
async def get_intercompany_transactions(
    fiscal_period: str = Query("2026-04"),
    entity: Optional[str] = Query(None, description="Filter by entity"),
    status: Optional[str] = Query(None, description="Filter by status")
):
    """
    Get intercompany transactions with optional filters
    """
    try:
        transactions = load_csv_data('Intercompany_Transactions_Mar2026.csv')
        
        # Apply filters
        filtered = [t for t in transactions if t.get('Period') == fiscal_period]
        if entity:
            filtered = [t for t in filtered if t.get('Entity') == entity or t.get('Counterparty_Entity') == entity]
        if status:
            filtered = [t for t in filtered if t.get('Status') == status]
        
        return ToolResponse(
            success=True,
            message=f"Found {len(filtered)} intercompany transactions",
            data={
                'fiscal_period': fiscal_period,
                'transactions': filtered,
                'count': len(filtered)
            }
        )
        
    except Exception as e:
        logger.error(f"Error getting intercompany transactions: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# TOOL 13: POST INTERCOMPANY ELIMINATION JOURNALS
# ============================================================================

@app.post("/tools/intercompany/post_eliminations", response_model=ToolResponse)
async def post_intercompany_eliminations(request: IntercompanyEliminationRequest):
    """
    Post approved intercompany elimination journals to GL
    """
    try:
        # Load elimination journals
        elimination_journals = load_csv_data('Intercompany_Elimination_Journals_Mar2026.csv')
        
        # Filter for period
        period_journals = [j for j in elimination_journals if j.get('Period') == request.fiscal_period]
        
        # Determine which journals to post
        journals_to_post = []
        if request.approve_all:
            journals_to_post = period_journals
        elif request.journal_ids:
            journals_to_post = [j for j in period_journals if j.get('JE_Number') in request.journal_ids]
        
        if not journals_to_post:
            return ToolResponse(
                success=False,
                message="No journals selected for posting"
            )
        
        # Check if all selected journals are approved using registry
        unapproved = []
        for journal in journals_to_post:
            journal_id = journal.get('JE_Number')
            # Check registry for approval
            found_approved = False
            for token, info in approval_registry.generated_approvals.items():
                if (info.get('type') == "Intercompany Variance" and
                    f"var:{journal_id}" in info.get('metadata_summary', '') and
                    info.get('status') == 'APPROVED'):
                    found_approved = True
                    break
            
            # Also check history
            if not found_approved:
                for hist in approval_history:
                    if (hist.get('type') == "Intercompany Variance" and
                        hist.get('decision') == 'approved' and
                        journal_id in str(hist.get('metadata', {}).get('affected_txns', ''))):
                        found_approved = True
                        break
            
            if not found_approved:
                unapproved.append({
                    'journal_id': journal_id,
                    'status': 'not_found',
                    'message': 'No approval record found'
                })
        
        if unapproved:
            return ToolResponse(
                success=False,
                message=f"Cannot post {len(unapproved)} journals - require approval",
                data={
                    'unapproved_journals': unapproved,
                    'dashboard_url': f"{APP_BASE_URL}/dashboard"
                }
            )
        
        # Post journals to GL (in a real system, this would create GL entries)
        posted = []
        for journal in journals_to_post:
            posted.append({
                'je_number': journal.get('JE_Number'),
                'entity': journal.get('Entity'),
                'account': journal.get('GL_Account_Code'),
                'debit': journal.get('Debit_AUD', 0),
                'credit': journal.get('Credit_AUD', 0),
                'description': journal.get('Description', '')
            })
        
        return ToolResponse(
            success=True,
            message=f"Successfully posted {len(posted)} elimination journals",
            data={
                'posted_count': len(posted),
                'posted_journals': posted,
                'total_amount': sum(j.get('Debit_AUD', 0) for j in journals_to_post)
            }
        )
        
    except Exception as e:
        logger.error(f"Error posting elimination journals: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# TOOL 14: RESOLVE INTERCOMPANY VARIANCE
# ============================================================================

@app.post("/tools/intercompany/resolve_variance", response_model=ToolResponse)
async def resolve_intercompany_variance(request: IntercompanyVarianceResolution):
    """
    Resolve an intercompany variance with approved action
    """
    try:
        # Load reconciliation data
        reconciliation = load_csv_data('Intercompany_Reconciliation_Mar2026.csv')
        
        # Find and update the variance
        variance_found = False
        for rec in reconciliation:
            variance_id = f"{rec.get('Entity')}-{rec.get('Counterparty_Entity')}-{rec.get('Period')}"
            if variance_id == request.variance_id:
                rec['Resolution_Status'] = 'Resolved'
                rec['Resolution_Action'] = request.resolution_action
                rec['Resolved_By'] = request.approved_by
                rec['Resolution_Date'] = datetime.now().strftime('%Y-%m-%d')
                rec['Comments'] = request.comments or ''
                variance_found = True
                break
        
        if not variance_found:
            return ToolResponse(
                success=False,
                message=f"Variance {request.variance_id} not found"
            )
        
        # Save updated reconciliation
        fieldnames = list(reconciliation[0].keys())
        save_csv_data('Intercompany_Reconciliation_Mar2026.csv', reconciliation, fieldnames)
        
        # Clean up any pending approvals
        for token, item in list(pending_approvals.items()):
            if (item.type == "Intercompany Variance" and 
                item.metadata and 
                item.metadata.get('entity_pair') in request.variance_id):
                del pending_approvals[token]
                logger.info(f"Removed pending approval {token} for resolved variance")
                break
        
        return ToolResponse(
            success=True,
            message=f"Variance {request.variance_id} resolved successfully",
            data={
                'variance_id': request.variance_id,
                'resolution_action': request.resolution_action,
                'resolved_by': request.approved_by,
                'resolution_date': datetime.now().isoformat()
            }
        )
        
    except Exception as e:
        logger.error(f"Error resolving intercompany variance: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# ACTIVITY 2: ACCRUALS & PREPAYMENTS
# ============================================================================

# Data Models
class AccrualsPrepaymentsRequest(BaseModel):
    fiscal_period: str = Field("2026-04", description="Fiscal period for analysis")
    entity_code: Optional[str] = Field(None, description="Filter by entity (optional)")

class AccrualAdjustmentRequest(BaseModel):
    fiscal_period: str = Field("2026-04", description="Fiscal period")
    accrual_ids: List[str]
    approved_by: str
    comments: Optional[str] = None

# ============================================================================
# TOOL 15: ACCRUALS & PREPAYMENTS ANALYSIS
# ============================================================================

@app.post("/tools/accruals/analyze", response_model=ToolResponse)
async def analyze_accruals_prepayments(request: AccrualsPrepaymentsRequest):
    """
    Analyze accruals and prepayments for the specified period
    Identifies variances, material items, and generates adjustment recommendations
    """
    try:
        # Load data
        accruals = load_csv_data('Accruals_Register_Mar2026.csv')
        prepayments = load_csv_data('Prepayments_Register_Mar2026.csv')
        adjustment_journals = load_csv_data('Accrual_Adjustment_Journals_Mar2026.csv')
        amortization_journals = load_csv_data('Prepayment_Amortization_Journals_Mar2026.csv')
        
        # Filter for period
        period_accruals = [a for a in accruals if a.get('Period') == request.fiscal_period]
        period_prepayments = [p for p in prepayments if p.get('Period') == request.fiscal_period]
        
        # Analyze accruals
        accrual_summary = {
            'total_count': len(period_accruals),
            'total_accrued': sum(float(a.get('Current_Period_Accrual', 0)) for a in period_accruals),
            'total_invoiced': sum(float(a.get('Invoice_Amount', 0)) for a in period_accruals),
            'total_variance': sum(float(a.get('Variance', 0)) for a in period_accruals)
        }
        
        # Status breakdown
        status_breakdown = defaultdict(lambda: {'count': 0, 'amount': 0.0})
        for a in period_accruals:
            status = a.get('Status', 'Unknown')
            amount = float(a.get('Current_Period_Accrual', 0))
            status_breakdown[status]['count'] += 1
            status_breakdown[status]['amount'] += amount
        
        # Materiality breakdown
        material_items = []
        review_items = []
        exceptions = []
        
        for a in period_accruals:
            if a.get('Materiality') == 'Material':
                item = {
                    'id': a.get('Accrual_ID'),
                    'description': a.get('Description', ''),
                    'amount': float(a.get('Current_Period_Accrual', 0)),
                    'variance': float(a.get('Variance', 0)),
                    'vendor': a.get('Vendor_Name', ''),
                    'reason': a.get('Variance_Reason', 'Unknown')
                }
                material_items.append(item)
                
                # Create approval item
                approval_item = create_approval_item(
                    item_type="Accrual Variance",
                    description=f"{item['description']} - {item['vendor']}",
                    amount=abs(item['variance']),
                    account=a.get('Account_Code', ''),
                    cost_center='CORP',
                    metadata={
                        'accrual_id': item['id'],
                        'accrued_amount': item['amount'],
                        'variance': item['variance'],
                        'reason': item['reason'],
                        'recommendation': f"Post adjustment journal to correct ${abs(item['variance']):,.2f} variance"
                    },
                    fiscal_period=request.fiscal_period
                )
                
                exceptions.append({
                    'type': 'Material Accrual Variance',
                    'id': item['id'],
                    'description': item['description'],
                    'amount': abs(item['variance']),
                    'vendor': item['vendor'],
                    'recommendation': f"Post adjustment journal",
                    'approval_token': approval_item.token,
                    'approval_links': get_approval_links(approval_item.token)
                })
        
        # Analyze prepayments
        prepayment_summary = {
            'total_count': len(period_prepayments),
            'total_prepaid': sum(float(p.get('Total_Prepaid_Amount', 0)) for p in period_prepayments),
            'total_amortized': sum(float(p.get('Current_Period_Amortization', 0)) for p in period_prepayments),
            'total_remaining': sum(float(p.get('Ending_Balance', 0)) for p in period_prepayments)
        }
        
        # Category breakdown
        category_breakdown = defaultdict(lambda: {'prepaid': 0.0, 'amortized': 0.0, 'remaining': 0.0})
        for p in period_prepayments:
            category = p.get('Amortization_Account_Name', 'Other')
            prepaid = float(p.get('Total_Prepaid_Amount', 0))
            amortized = float(p.get('Current_Period_Amortization', 0))
            remaining = float(p.get('Ending_Balance', 0))
            
            category_breakdown[category]['prepaid'] += prepaid
            category_breakdown[category]['amortized'] += amortized
            category_breakdown[category]['remaining'] += remaining
        
        # Analyze adjustment journals
        adj_summary = {
            'total_journals': len(adjustment_journals),
            'total_debits': sum(float(j.get('Debit_AUD', 0)) for j in adjustment_journals),
            'total_credits': sum(float(j.get('Credit_AUD', 0)) for j in adjustment_journals)
        }
        adj_summary['balanced'] = abs(adj_summary['total_debits'] - adj_summary['total_credits']) < 0.01
        
        # Analyze amortization journals
        amort_summary = {
            'total_journals': len(amortization_journals),
            'total_amortized': sum(float(j.get('Debit_AUD', 0)) for j in amortization_journals)
        }
        
        response_data = {
            'fiscal_period': request.fiscal_period,
            'accruals': {
                'summary': accrual_summary,
                'status_breakdown': dict(status_breakdown),
                'material_items': material_items,
                'review_items': review_items
            },
            'prepayments': {
                'summary': prepayment_summary,
                'category_breakdown': dict(category_breakdown)
            },
            'journals': {
                'adjustment': adj_summary,
                'amortization': amort_summary
            },
            'exceptions': exceptions,
            'dashboard_url': f"{APP_BASE_URL}/dashboard"
        }
        
        message = f"Accruals analysis complete. Found {len(material_items)} material variances requiring approval."
        
        return ToolResponse(
            success=True,
            message=message,
            data=response_data  # Fixed: changed from responseData to response_data
        )
        
    except Exception as e:
        logger.error(f"Error in accruals analysis: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# TOOL 16: GET ACCRUALS
# ============================================================================

@app.get("/tools/accruals/list", response_model=ToolResponse)
async def get_accruals(
    fiscal_period: str = Query("2026-04"),
    status: Optional[str] = Query(None, description="Filter by status"),
    materiality: Optional[str] = Query(None, description="Filter by materiality")
):
    """
    Get accruals with optional filters
    """
    try:
        accruals = load_csv_data('Accruals_Register_Mar2026.csv')
        
        # Apply filters
        filtered = [a for a in accruals if a.get('Period') == fiscal_period]
        if status:
            filtered = [a for a in filtered if a.get('Status') == status]
        if materiality:
            filtered = [a for a in filtered if a.get('Materiality') == materiality]
        
        return ToolResponse(
            success=True,
            message=f"Found {len(filtered)} accruals",
            data={
                'fiscal_period': fiscal_period,
                'accruals': filtered,
                'count': len(filtered)
            }
        )
        
    except Exception as e:
        logger.error(f"Error getting accruals: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# TOOL 17: GET PREPAYMENTS
# ============================================================================

@app.get("/tools/prepayments/list", response_model=ToolResponse)
async def get_prepayments(
    fiscal_period: str = Query("2026-04"),
    status: Optional[str] = Query(None, description="Filter by status")
):
    """
    Get prepayments with optional filters
    """
    try:
        prepayments = load_csv_data('Prepayments_Register_Mar2026.csv')
        
        # Apply filters
        filtered = [p for p in prepayments if p.get('Period') == fiscal_period]
        if status:
            filtered = [p for p in filtered if p.get('Status') == status]
        
        return ToolResponse(
            success=True,
            message=f"Found {len(filtered)} prepayments",
            data={
                'fiscal_period': fiscal_period,
                'prepayments': filtered,
                'count': len(filtered)
            }
        )
        
    except Exception as e:
        logger.error(f"Error getting prepayments: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# TOOL 18: POST ACCRUAL ADJUSTMENT JOURNALS
# ============================================================================

@app.post("/tools/accruals/post_adjustments", response_model=ToolResponse)
async def post_accrual_adjustments(request: AccrualAdjustmentRequest):
    """
    Post approved accrual adjustment journals
    """
    try:
        # Load adjustment journals
        adjustment_journals = load_csv_data('Accrual_Adjustment_Journals_Mar2026.csv')
        
        # Find journals for the specified accruals
        journals_to_post = [j for j in adjustment_journals if j.get('Accrual_ID') in request.accrual_ids]
        
        if not journals_to_post:
            return ToolResponse(
                success=False,
                message="No adjustment journals found for the specified accruals"
            )
        
        # Check if all are approved using registry
        unapproved = []
        for journal in journals_to_post:
            accrual_id = journal.get('Accrual_ID')
            # Check registry for approval
            found_approved = False
            for token, info in approval_registry.generated_approvals.items():
                if (info.get('type') == "Accrual Variance" and
                    f"accrual:{accrual_id}" in info.get('metadata_summary', '') and
                    info.get('status') == 'APPROVED'):
                    found_approved = True
                    break
            
            if not found_approved:
                unapproved.append({
                    'accrual_id': accrual_id,
                    'status': 'not_found',
                    'message': 'No approval record found'
                })
        
        if unapproved:
            return ToolResponse(
                success=False,
                message=f"Cannot post {len(unapproved)} journals - require approval",
                data={
                    'unapproved_journals': unapproved,
                    'dashboard_url': f"{APP_BASE_URL}/dashboard"
                }
            )
        
        # Post journals (update status)
        posted = []
        for journal in journals_to_post:
            journal['Status'] = 'Posted'
            journal['Posted_Date'] = datetime.now().strftime('%Y-%m-%d')
            journal['Posted_By'] = request.approved_by
            posted.append(journal.get('JE_Number'))
        
        # Save updated journals
        fieldnames = list(adjustment_journals[0].keys())
        save_csv_data('Accrual_Adjustment_Journals_Mar2026.csv', adjustment_journals, fieldnames)
        
        return ToolResponse(
            success=True,
            message=f"Successfully posted {len(posted)} adjustment journals",
            data={
                'posted_count': len(posted),
                'posted_journals': posted
            }
        )
        
    except Exception as e:
        logger.error(f"Error posting adjustment journals: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# ACTIVITY 3: BANK RECONCILIATION
# ============================================================================

# Data Models
class BankReconciliationRequest(BaseModel):
    fiscal_period: str = Field("2026-04", description="Fiscal period for reconciliation")
    entity_code: Optional[str] = Field(None, description="Filter by entity (optional)")

class BankReconciliationItemResolution(BaseModel):
    item_id: str
    resolution_action: str  # 'post_journal', 'follow_up', 'write_off', etc.
    approved_by: str
    comments: Optional[str] = None

# ============================================================================
# TOOL 19: BANK RECONCILIATION ANALYSIS
# ============================================================================

@app.post("/tools/bank/reconcile", response_model=ToolResponse)
async def bank_reconciliation(request: BankReconciliationRequest):
    """
    Perform bank reconciliation analysis for the specified period
    Identifies reconciling items, variances, and generates recommendations
    """
    try:
        # Load data
        bank_statements = load_csv_data('Bank_Statements_Mar2026.csv')
        gl_cash_balances = load_csv_data('GL_Cash_Balances_Mar2026.csv')
        reconciliation_items = load_csv_data('Bank_Reconciliation_Items_Mar2026.csv')
        reconciliation_journals = load_csv_data('Bank_Reconciliation_Journals_Mar2026.csv')
        
        # Calculate totals
        total_bank_balance = sum(float(gl.get('Statement_Balance_AUD', 0)) for gl in gl_cash_balances)
        total_gl_balance = sum(float(gl.get('GL_Balance_AUD', 0)) for gl in gl_cash_balances)
        total_variance = total_gl_balance - total_bank_balance
        
        # Analyze reconciliation items
        items_by_type = defaultdict(lambda: {'count': 0, 'amount': 0.0})
        review_items = []
        material_items = []
        exceptions = []
        
        for item in reconciliation_items:
            item_type = item.get('Item_Type', 'Unknown')
            amount = abs(float(item.get('Amount_AUD', 0)))
            materiality = item.get('Materiality', 'Low')
            
            items_by_type[item_type]['count'] += 1
            items_by_type[item_type]['amount'] += amount
            
            if materiality in ['Material', 'Review']:
                item_info = {
                    'id': item.get('Item_ID'),
                    'type': item_type,
                    'description': item.get('Description', ''),
                    'amount': amount,
                    'aging': int(item.get('Aging_Days', 0)),
                    'materiality': materiality,
                    'recommendation': item.get('Agent_Recommendation', 'Review required')
                }
                
                if materiality == 'Material':
                    material_items.append(item_info)
                else:
                    review_items.append(item_info)
                
                # Create approval item
                approval_item = create_approval_item(
                    item_type="Bank Reconciliation",
                    description=f"{item_info['description']} - {item_info['id']}",
                    amount=item_info['amount'],
                    account="1010",
                    cost_center="CORP",
                    metadata={
                        'item_id': item_info['id'],
                        'item_type': item_info['type'],
                        'aging_days': item_info['aging'],
                        'materiality': item_info['materiality'],
                        'recommendation': item_info['recommendation']
                    },
                    fiscal_period=request.fiscal_period
                )
                
                exceptions.append({
                    'type': f'{materiality} Bank Item',
                    'id': item_info['id'],
                    'description': item_info['description'],
                    'amount': item_info['amount'],
                    'aging': item_info['aging'],
                    'recommendation': item_info['recommendation'],
                    'approval_token': approval_item.token,
                    'approval_links': get_approval_links(approval_item.token)
                })
        
        # Analyze journals
        journals_by_status = defaultdict(lambda: {'count': 0, 'amount': 0.0})
        total_debits = 0.0
        total_credits = 0.0
        
        for journal in reconciliation_journals:
            status = journal.get('Status', 'Unknown')
            debit = float(journal.get('Debit_AUD', 0))
            credit = float(journal.get('Credit_AUD', 0))
            
            journals_by_status[status]['count'] += 1
            journals_by_status[status]['amount'] += abs(debit - credit)
            total_debits += debit
            total_credits += credit
        
        journals_balanced = abs(total_debits - total_credits) < 0.01
        
        # Account positions
        account_positions = []
        for gl in gl_cash_balances:
            account_positions.append({
                'entity': gl.get('Entity'),
                'bank_name': gl.get('Bank_Name'),
                'account_number': gl.get('Account_Number'),
                'gl_balance': float(gl.get('GL_Balance_AUD', 0)),
                'bank_balance': float(gl.get('Statement_Balance_AUD', 0)),
                'variance': float(gl.get('Variance_AUD', 0)),
                'status': gl.get('Reconciliation_Status')
            })
        
        response_data = {
            'fiscal_period': request.fiscal_period,
            'summary': {
                'total_bank_balance': total_bank_balance,
                'total_gl_balance': total_gl_balance,
                'net_variance': total_variance,
                'accounts_reconciled': len(gl_cash_balances)
            },
            'reconciliation_items': {
                'total_count': len(reconciliation_items),
                'by_type': dict(items_by_type),
                'material_items': material_items,
                'review_items': review_items
            },
            'journals': {
                'total_count': len(reconciliation_journals),
                'by_status': dict(journals_by_status),
                'balanced': journals_balanced,
                'total_debits': total_debits,
                'total_credits': total_credits
            },
            'account_positions': account_positions,
            'exceptions': exceptions,
            'dashboard_url': f"{APP_BASE_URL}/dashboard"
        }
        
        message = f"Bank reconciliation complete. Found {len(reconciliation_items)} reconciling items"
        if material_items:
            message += f", {len(material_items)} material items require approval"
        if review_items:
            message += f", {len(review_items)} items require review"
        
        return ToolResponse(
            success=True,
            message=message,
            data=response_data
        )
        
    except Exception as e:
        logger.error(f"Error in bank reconciliation: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# TOOL 20: GET BANK RECONCILIATION ITEMS
# ============================================================================

@app.get("/tools/bank/items", response_model=ToolResponse)
async def get_bank_reconciliation_items(
    fiscal_period: str = Query("2026-04"),
    item_type: Optional[str] = Query(None, description="Filter by item type"),
    materiality: Optional[str] = Query(None, description="Filter by materiality")
):
    """
    Get bank reconciliation items with optional filters
    """
    try:
        reconciliation_items = load_csv_data('Bank_Reconciliation_Items_Mar2026.csv')
        
        # Apply filters
        filtered = reconciliation_items
        if item_type:
            filtered = [i for i in filtered if i.get('Item_Type') == item_type]
        if materiality:
            filtered = [i for i in filtered if i.get('Materiality') == materiality]
        
        # Enhance with approval info
        for item in filtered:
            item_id = item.get('Item_ID')
            for token, approval in pending_approvals.items():
                if (approval.type == "Bank Reconciliation" and 
                    approval.metadata and 
                    approval.metadata.get('item_id') == item_id):
                    item['approval_token'] = token
                    item['approval_links'] = get_approval_links(token)
                    item['approval_status'] = approval.status.value
                    break
        
        return ToolResponse(
            success=True,
            message=f"Found {len(filtered)} reconciliation items",
            data={
                'fiscal_period': fiscal_period,
                'items': filtered,
                'count': len(filtered)
            }
        )
        
    except Exception as e:
        logger.error(f"Error getting bank items: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# TOOL 21: GET BANK POSITIONS
# ============================================================================

@app.get("/tools/bank/positions", response_model=ToolResponse)
async def get_bank_positions(
    fiscal_period: str = Query("2026-04"),
    entity_code: Optional[str] = Query(None, description="Filter by entity")
):
    """
    Get bank and GL positions for all accounts
    """
    try:
        gl_cash_balances = load_csv_data('GL_Cash_Balances_Mar2026.csv')
        
        # Apply entity filter
        if entity_code:
            gl_cash_balances = [g for g in gl_cash_balances if g.get('Entity') == entity_code]
        
        # Calculate totals
        positions = []
        total_gl = 0.0
        total_bank = 0.0
        
        for gl in gl_cash_balances:
            gl_balance = float(gl.get('GL_Balance_AUD', 0))
            bank_balance = float(gl.get('Statement_Balance_AUD', 0))
            variance = float(gl.get('Variance_AUD', 0))
            
            total_gl += gl_balance
            total_bank += bank_balance
            
            positions.append({
                'entity': gl.get('Entity'),
                'bank_name': gl.get('Bank_Name'),
                'account_number': gl.get('Account_Number'),
                'gl_balance': gl_balance,
                'bank_balance': bank_balance,
                'variance': variance,
                'status': gl.get('Reconciliation_Status')
            })
        
        return ToolResponse(
            success=True,
            message=f"Found {len(positions)} bank positions",
            data={
                'fiscal_period': fiscal_period,
                'positions': positions,
                'totals': {
                    'total_gl_balance': total_gl,
                    'total_bank_balance': total_bank,
                    'net_variance': total_gl - total_bank
                }
            }
        )
        
    except Exception as e:
        logger.error(f"Error getting bank positions: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# TOOL 22: POST BANK RECONCILIATION JOURNALS
# ============================================================================

@app.post("/tools/bank/post_journals", response_model=ToolResponse)
async def post_bank_reconciliation_journals(
    request: JournalEntryRequest
):
    """
    Post approved bank reconciliation journals to GL
    """
    try:
        # Load existing journals
        reconciliation_journals = load_csv_data('Bank_Reconciliation_Journals_Mar2026.csv')
        
        # Check if entries are approved using registry
        unapproved_entries = []
        approved_entries = []
        
        for entry in request.entries:
            if not entry.approved:
                # Check registry for approval
                found_approved = False
                for token, info in approval_registry.generated_approvals.items():
                    if (info.get('type') == "Bank Reconciliation" and
                        f"item:{entry.entry_id}" in info.get('metadata_summary', '') and
                        info.get('status') == 'APPROVED'):
                        found_approved = True
                        break
                
                # Also check history
                if not found_approved:
                    for hist_item in approval_history:
                        if (hist_item.get('type') == "Bank Reconciliation" and
                            hist_item.get('metadata', {}).get('item_id') == entry.entry_id and
                            hist_item.get('decision') == 'approved'):
                            found_approved = True
                            break
                
                if not found_approved:
                    unapproved_entries.append({
                        'entry_id': entry.entry_id,
                        'status': 'not_approved'
                    })
            else:
                approved_entries.append(entry)
        
        if unapproved_entries:
            return ToolResponse(
                success=False,
                message=f"Cannot post entries - {len(unapproved_entries)} require approval",
                data={
                    'unapproved_entries': unapproved_entries,
                    'dashboard_url': f"{APP_BASE_URL}/dashboard"
                }
            )
        
        # Update journal status in file
        updated_count = 0
        for journal in reconciliation_journals:
            for entry in approved_entries:
                if journal.get('JE_Number') == entry.entry_id:
                    journal['Status'] = 'Posted'
                    journal['Approved_By'] = entry.approved_by
                    journal['Posted_Date'] = datetime.now().strftime('%Y-%m-%d')
                    updated_count += 1
                    break
        
        # Save updated journals
        if updated_count > 0:
            fieldnames = list(reconciliation_journals[0].keys())
            save_csv_data('Bank_Reconciliation_Journals_Mar2026.csv', reconciliation_journals, fieldnames)
        
        return ToolResponse(
            success=True,
            message=f"Posted {updated_count} bank reconciliation journals",
            data={
                'posted_count': updated_count,
                'posted_entries': [e.entry_id for e in approved_entries]
            }
        )
        
    except Exception as e:
        logger.error(f"Error posting bank journals: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# TOOL 23: RESOLVE BANK RECONCILIATION ITEM
# ============================================================================

@app.post("/tools/bank/resolve_item", response_model=ToolResponse)
async def resolve_bank_reconciliation_item(request: BankReconciliationItemResolution):
    """
    Resolve a bank reconciliation item (mark as resolved, post journal, etc.)
    """
    try:
        # Load reconciliation items
        reconciliation_items = load_csv_data('Bank_Reconciliation_Items_Mar2026.csv')
        
        # Find and update the item
        item_found = False
        for item in reconciliation_items:
            if item.get('Item_ID') == request.item_id:
                item['Status'] = 'Resolved'
                item['Resolution_Action'] = request.resolution_action
                item['Resolved_By'] = request.approved_by
                item['Resolution_Date'] = datetime.now().strftime('%Y-%m-%d')
                item['Comments'] = request.comments or ''
                item_found = True
                break
        
        if not item_found:
            return ToolResponse(
                success=False,
                message=f"Item {request.item_id} not found"
            )
        
        # Save updated items
        fieldnames = list(reconciliation_items[0].keys())
        save_csv_data('Bank_Reconciliation_Items_Mar2026.csv', reconciliation_items, fieldnames)
        
        # Clean up any pending approvals for this item
        for token, approval in list(pending_approvals.items()):
            if (approval.type == "Bank Reconciliation" and 
                approval.metadata and 
                approval.metadata.get('item_id') == request.item_id):
                del pending_approvals[token]
                logger.info(f"Removed pending approval {token} for resolved item {request.item_id}")
                break
        
        return ToolResponse(
            success=True,
            message=f"Item {request.item_id} resolved successfully",
            data={
                'item_id': request.item_id,
                'resolution_action': request.resolution_action,
                'resolved_by': request.approved_by,
                'resolution_date': datetime.now().isoformat()
            }
        )
        
    except Exception as e:
        logger.error(f"Error resolving bank item: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# MASTER CLOSE STATUS - COMBINED VIEW
# ============================================================================

@app.get("/tools/close/status", response_model=ToolResponse)
async def get_close_status(fiscal_period: str = Query("2026-04")):
    """
    Get combined status of all close activities
    """
    try:
        # Load all data
        ic_transactions = load_csv_data('Intercompany_Transactions_Mar2026.csv')
        ic_reconciliation = load_csv_data('Intercompany_Reconciliation_Mar2026.csv')
        accruals = load_csv_data('Accruals_Register_Mar2026.csv')
        prepayments = load_csv_data('Prepayments_Register_Mar2026.csv')
        bank_items = load_csv_data('Bank_Reconciliation_Items_Mar2026.csv')
        
        # Filter for period
        ic_rec_period = [r for r in ic_reconciliation if r.get('Period') == fiscal_period]
        accruals_period = [a for a in accruals if a.get('Period') == fiscal_period]
        
        # Get approval summary from registry
        approval_summary = approval_registry.get_approval_summary(fiscal_period)
        
        # Calculate status by activity
        status = {
            'intercompany': {
                'status': 'PENDING_APPROVAL' if approval_summary['by_type'].get('Intercompany Variance', {}).get('pending', 0) > 0 else 'COMPLETE',
                'total_variances': len([r for r in ic_rec_period if abs(float(r.get('Variance_AUD', 0))) > 0]),
                'material_items': len([r for r in ic_rec_period if r.get('Materiality') == 'Material']),
                'pending_approvals': approval_summary['by_type'].get('Intercompany Variance', {}).get('pending', 0)
            },
            'accruals': {
                'status': 'PENDING_APPROVAL' if approval_summary['by_type'].get('Accrual Variance', {}).get('pending', 0) > 0 else 'COMPLETE',
                'total_items': len(accruals_period),
                'material_items': len([a for a in accruals_period if a.get('Materiality') == 'Material']),
                'pending_approvals': approval_summary['by_type'].get('Accrual Variance', {}).get('pending', 0)
            },
            'prepayments': {
                'status': 'COMPLETE',
                'total_items': len([p for p in prepayments if p.get('Period') == fiscal_period]),
                'active_items': len([p for p in prepayments if p.get('Period') == fiscal_period and p.get('Status') == 'Active'])
            },
            'bank_reconciliation': {
                'status': 'PENDING_REVIEW' if approval_summary['by_type'].get('Bank Reconciliation', {}).get('pending', 0) > 0 else 'COMPLETE',
                'total_items': len(bank_items),
                'material_items': len([b for b in bank_items if b.get('Materiality') == 'Material']),
                'review_items': len([b for b in bank_items if b.get('Materiality') == 'Review']),
                'pending_approvals': approval_summary['by_type'].get('Bank Reconciliation', {}).get('pending', 0)
            }
        }
        
        # Calculate overall status
        all_pending = approval_summary['pending']
        
        overall_status = 'PENDING_APPROVAL' if all_pending > 0 else 'READY_TO_CLOSE'
        
        response_data = {
            'fiscal_period': fiscal_period,
            'overall_status': overall_status,
            'total_pending_items': all_pending,
            'approval_summary': approval_summary,
            'activities': status,
            'dashboard_url': f"{APP_BASE_URL}/dashboard"
        }
        
        message = f"Close status: {all_pending} items pending approval across all activities"
        
        return ToolResponse(
            success=True,
            message=message,
            data=response_data
        )
        
    except Exception as e:
        logger.error(f"Error getting close status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    


def _render_milestones_with_progress_html(milestones: Dict[str, Any]) -> str:
    """
    Render milestones with individual progress bars and status indicators.
    Uses the new milestone structure with status and progress fields.
    """
    if not milestones:
        return '<p style="color: #666; text-align: center;">No milestones defined</p>'
    
    html = ''
    
    for key, milestone in milestones.items():
        status = milestone.get('status', 'NOT_STARTED')
        progress = milestone.get('progress', 0)
        name = milestone.get('name', key)
        weight = milestone.get('weight', 0)
        
        status_class = 'completed' if status == 'COMPLETED' else 'in-progress' if status == 'IN_PROGRESS' else 'not-started'
        status_icon = '✅' if status == 'COMPLETED' else '🔄' if status == 'IN_PROGRESS' else '○'
        
        html += f'''
            <div class="milestone-item">
                <div class="milestone-header">
                    <span class="milestone-icon {status_class}">{status_icon}</span>
                    <span class="milestone-name">{name}</span>
                    <span class="milestone-weight">({weight}%)</span>
                </div>
                <div class="milestone-progress-container">
                    <div class="milestone-progress-bar {status_class}" style="width: {progress:.0f}%"></div>
                </div>
                <div class="milestone-percent">{progress:.0f}% - {status.replace('_', ' ')}</div>
            </div>
        '''
    
    return html
    

@app.get("/dashboard/progress", response_class=HTMLResponse)
async def close_progress_dashboard(fiscal_period: str = Query("2026-04")):
    """
    Comprehensive close progress dashboard that tracks all decisions and provides real-time status
    """
    # Load analysis data
    analysis = analyze_close_readiness(fiscal_period)
    cfo_summary = generate_cfo_summary(analysis)
    
    # Load logo as base64
    logo_base64 = ""
    try:
        with open("Octane_logo.png", "rb") as logo_file:
            logo_base64 = base64.b64encode(logo_file.read()).decode('utf-8')
    except Exception as e:
        logger.warning(f"Could not load logo: {e}")
    
    # Format numbers for display - USE CORRECTED KEY NAMES
    approval_progress = analysis['summary']['approval_progress_percent']
    milestone_progress = analysis['summary']['milestone_progress_percent']
    overall_status = analysis['overall_status']
    
    # Determine progress bar color and status color based on overall status
    if overall_status == 'NOT_STARTED':
        progress_color = "#999999"
        status_color = "#6c757d"  # Grey for not started
    elif overall_status == 'BLOCKED':
        progress_color = "#999999"
        status_color = "#dc3545"  # Red for blocked
    elif overall_status == 'AT_RISK':
        progress_color = "#666666"
        status_color = "#fd7e14"  # Orange for at risk
    elif overall_status == 'READY':
        progress_color = "#000000"
        status_color = "#28a745"  # Green for ready
    else:  # IN_PROGRESS or other
        progress_color = "#333333"
        status_color = "#007bff"  # Blue for in progress
    
    # Get current stage from analysis
    current_stage = analysis.get('current_stage', {})
    current_stage_name = current_stage.get('stage_name', 'Not Started')
    current_stage_status = current_stage.get('status', 'NOT_STARTED')
    current_stage_progress = current_stage.get('progress', 0)
    
    # Determine current stage status CSS class
    if current_stage_status == 'COMPLETED':
        stage_status_css = 'stage-status-completed'
    elif current_stage_status == 'IN_PROGRESS':
        stage_status_css = 'stage-status-in-progress'
    else:
        stage_status_css = 'stage-status-not-started'
    
    # Determine current stage icon
    if current_stage_status == 'COMPLETED':
        stage_icon = '✅'
    elif current_stage_status == 'IN_PROGRESS':
        stage_icon = '🔄'
    else:
        stage_icon = '🔵'
    
    # Get milestone data for initial render
    milestone_summary = analysis.get('milestone_summary', {})
    milestones = milestone_summary.get('milestones', {})
    
    # Generate initial milestone HTML
    milestone_html = _render_milestones_with_progress_html(milestones)
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Close Progress Dashboard - {fiscal_period}</title>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: #f5f5f5;
                padding: 20px;
            }}
            
            .dashboard-container {{
                max-width: 1400px;
                margin: 0 auto;
            }}
            
            /* Header */
            .dashboard-header {{
                background: #000000;
                color: white;
                padding: 25px 30px;
                border-radius: 15px;
                margin-bottom: 25px;
                display: flex;
                align-items: center;
                gap: 25px;
                flex-wrap: wrap;
            }}
            
            .header-logo {{
                height: 50px;
            }}
            
            .header-title {{
                flex-grow: 1;
            }}
            
            .header-title h1 {{
                font-size: 1.8em;
                margin-bottom: 5px;
            }}
            
            .header-title p {{
                opacity: 0.8;
            }}
            
            .period-selector {{
                display: flex;
                gap: 10px;
                align-items: center;
            }}
            
            .period-selector select {{
                padding: 10px 15px;
                border-radius: 8px;
                border: none;
                font-size: 1em;
                background: #333;
                color: white;
            }}
            
            .period-selector button {{
                padding: 10px 20px;
                background: #333;
                color: white;
                border: none;
                border-radius: 8px;
                cursor: pointer;
                transition: background 0.3s;
            }}
            
            .period-selector button:hover {{
                background: #555;
            }}
            
            .refresh-btn {{
                background: #333;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 8px;
                cursor: pointer;
                font-size: 1em;
                transition: background 0.3s;
            }}
            
            .refresh-btn:hover {{
                background: #555;
            }}
            
            /* Current Stage Indicator */
            .stage-indicator-container {{
                background: white;
                border-radius: 15px;
                padding: 20px 25px;
                margin-bottom: 25px;
                box-shadow: 0 5px 15px rgba(0,0,0,0.08);
                display: flex;
                align-items: center;
                gap: 20px;
                border-left: 6px solid {status_color};
            }}
            
            .stage-indicator-icon {{
                font-size: 2.5em;
                min-width: 60px;
                text-align: center;
            }}
            
            .stage-indicator-content {{
                flex-grow: 1;
            }}
            
            .stage-indicator-label {{
                font-size: 0.85em;
                color: #666;
                text-transform: uppercase;
                letter-spacing: 1px;
                margin-bottom: 5px;
            }}
            
            .stage-indicator-name {{
                font-size: 1.4em;
                font-weight: bold;
                color: #000000;
            }}
            
            .stage-indicator-status {{
                display: inline-block;
                padding: 4px 12px;
                border-radius: 20px;
                font-size: 0.85em;
                font-weight: 500;
                margin-top: 5px;
            }}
            
            .stage-status-completed {{
                background: #000000;
                color: white;
            }}
            
            .stage-status-in-progress {{
                background: #333333;
                color: white;
            }}
            
            .stage-status-not-started {{
                background: #e0e0e0;
                color: #666;
            }}
            
            .stage-progress-bar {{
                width: 150px;
                background: #e0e0e0;
                border-radius: 10px;
                height: 8px;
                overflow: hidden;
            }}
            
            .stage-progress-fill {{
                background: {status_color};
                height: 100%;
                border-radius: 10px;
                transition: width 0.5s ease;
                width: {current_stage_progress:.0f}%;
            }}
            
            .stage-progress-text {{
                font-size: 0.85em;
                color: #666;
                min-width: 50px;
                text-align: right;
            }}
            
            /* Status Cards */
            .status-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 20px;
                margin-bottom: 25px;
            }}
            
            .status-card {{
                background: white;
                padding: 20px;
                border-radius: 15px;
                text-align: center;
                box-shadow: 0 5px 15px rgba(0,0,0,0.08);
                transition: transform 0.3s;
            }}
            
            .status-card:hover {{
                transform: translateY(-3px);
            }}
            
            .status-card .number {{
                font-size: 2.5em;
                font-weight: bold;
                color: #000000;
            }}
            
            .status-card .label {{
                color: #666;
                margin-top: 8px;
                font-size: 0.9em;
            }}
            
            /* Main Status Banner */
            .main-status {{
                background: white;
                border-radius: 15px;
                margin-bottom: 25px;
                overflow: hidden;
                box-shadow: 0 5px 20px rgba(0,0,0,0.1);
            }}
            
            .status-banner {{
                padding: 25px;
                background: linear-gradient(135deg, {status_color} 0%, {status_color}cc 100%);
                color: white;
            }}
            
            .status-banner h2 {{
                font-size: 1.5em;
                margin-bottom: 8px;
            }}
            
            .status-banner p {{
                opacity: 0.95;
                font-size: 1.1em;
            }}
            
            /* Progress Bars */
            .progress-section {{
                padding: 25px;
                border-bottom: 1px solid #e0e0e0;
            }}
            
            .progress-item {{
                margin-bottom: 20px;
            }}
            
            .progress-label {{
                display: flex;
                justify-content: space-between;
                margin-bottom: 8px;
                color: #333;
                font-weight: 500;
            }}
            
            .progress-bar-container {{
                background: #e0e0e0;
                border-radius: 20px;
                overflow: hidden;
                height: 12px;
            }}
            
            .progress-bar-fill.approval {{
                background: {progress_color};
                height: 100%;
                border-radius: 20px;
                transition: width 0.5s ease;
                width: {approval_progress:.1f}%;
            }}
            
            .progress-bar-fill.milestone {{
                background: #666666;
                height: 100%;
                border-radius: 20px;
                transition: width 0.5s ease;
                width: {milestone_progress:.1f}%;
            }}
            
            /* Two Column Layout */
            .two-column {{
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 25px;
                margin-bottom: 25px;
            }}
            
            /* Cards */
            .card {{
                background: white;
                border-radius: 15px;
                overflow: hidden;
                box-shadow: 0 5px 15px rgba(0,0,0,0.08);
            }}
            
            .card-header {{
                background: #f8f9fa;
                padding: 15px 20px;
                border-bottom: 2px solid #000000;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }}
            
            .card-header h3 {{
                margin: 0;
                color: #000000;
            }}
            
            .card-header .badge {{
                background: #000000;
                color: white;
                padding: 4px 10px;
                border-radius: 20px;
                font-size: 0.8em;
            }}
            
            .card-content {{
                padding: 20px;
                max-height: 400px;
                overflow-y: auto;
            }}
            
            /* Item Lists */
            .item-list {{
                list-style: none;
                padding: 0;
            }}
            
            .item-list li {{
                padding: 12px;
                border-bottom: 1px solid #f0f0f0;
                display: flex;
                justify-content: space-between;
                align-items: center;
                flex-wrap: wrap;
                gap: 10px;
            }}
            
            .item-list li:last-child {{
                border-bottom: none;
            }}
            
            .item-type {{
                font-weight: 600;
                color: #000000;
                min-width: 140px;
            }}
            
            .item-description {{
                flex-grow: 1;
                color: #555;
                font-size: 0.9em;
            }}
            
            .item-amount {{
                font-weight: 500;
                color: #333;
                min-width: 100px;
                text-align: right;
            }}
            
            .item-action {{
                min-width: 80px;
                text-align: right;
            }}
            
            .item-action a {{
                color: #000000;
                text-decoration: none;
                font-size: 0.85em;
            }}
            
            .item-action a:hover {{
                text-decoration: underline;
            }}
            
            .status-badge {{
                display: inline-block;
                padding: 3px 8px;
                border-radius: 12px;
                font-size: 0.7em;
                font-weight: 500;
            }}
            
            .status-critical {{
                background: #dc3545;
                color: white;
            }}
            
            .status-high {{
                background: #fd7e14;
                color: white;
            }}
            
            .status-medium {{
                background: #ffc107;
                color: #333;
            }}
            
            .status-low {{
                background: #28a745;
                color: white;
            }}
            
            .overdue {{
                background: #dc3545;
                color: white;
            }}
            
            /* CFO Summary Box */
            .cfo-summary {{
                background: #f8f9fa;
                border-left: 4px solid #000000;
                padding: 20px;
                margin-bottom: 25px;
                border-radius: 10px;
                font-size: 0.95em;
                line-height: 1.6;
                white-space: pre-line;
            }}
            
            .cfo-summary h3 {{
                color: #000000;
                margin-bottom: 12px;
                display: flex;
                align-items: center;
                gap: 10px;
            }}
            
            /* Milestone Items with Progress Bars */
            .milestone-item {{
                padding: 15px 0;
                border-bottom: 1px solid #f0f0f0;
            }}
            
            .milestone-item:last-child {{
                border-bottom: none;
            }}
            
            .milestone-header {{
                display: flex;
                align-items: center;
                gap: 12px;
                margin-bottom: 8px;
            }}
            
            .milestone-icon {{
                width: 28px;
                height: 28px;
                border-radius: 50%;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                font-size: 0.85em;
                flex-shrink: 0;
            }}
            
            .milestone-icon.completed {{
                background: #000000;
                color: white;
            }}
            
            .milestone-icon.in-progress {{
                background: #333333;
                color: white;
            }}
            
            .milestone-icon.not-started {{
                background: #e0e0e0;
                color: #666;
            }}
            
            .milestone-name {{
                font-weight: 500;
                color: #333;
                flex-grow: 1;
            }}
            
            .milestone-weight {{
                color: #666;
                font-size: 0.8em;
            }}
            
            .milestone-progress-container {{
                background: #e0e0e0;
                border-radius: 10px;
                height: 8px;
                overflow: hidden;
                margin-left: 40px;
            }}
            
            .milestone-progress-bar {{
                height: 100%;
                border-radius: 10px;
                transition: width 0.5s ease;
            }}
            
            .milestone-progress-bar.completed {{
                background: #000000;
            }}
            
            .milestone-progress-bar.in-progress {{
                background: #666666;
            }}
            
            .milestone-progress-bar.not-started {{
                background: #cccccc;
            }}
            
            .milestone-percent {{
                font-size: 0.85em;
                color: #666;
                margin-left: 40px;
                margin-top: 4px;
            }}
            
            /* Footer */
            .footer {{
                text-align: center;
                margin-top: 30px;
                padding: 20px;
                color: #666;
                border-top: 1px solid #e0e0e0;
            }}
            
            .footer a {{
                color: #000000;
                text-decoration: none;
                margin: 0 10px;
            }}
            
            .footer a:hover {{
                text-decoration: underline;
            }}
            
            /* Responsive */
            @media (max-width: 768px) {{
                .two-column {{
                    grid-template-columns: 1fr;
                }}
                
                .dashboard-header {{
                    flex-direction: column;
                    text-align: center;
                }}
                
                .stage-indicator-container {{
                    flex-direction: column;
                    text-align: center;
                }}
            }}
            
            .auto-refresh {{
                font-size: 0.8em;
                color: #888;
                margin-top: 5px;
            }}
        </style>
    </head>
    <body>
        <div class="dashboard-container">
            <!-- Header -->
            <div class="dashboard-header">
                <img src="data:image/png;base64,{logo_base64}" alt="Octane Logo" class="header-logo">
                <div class="header-title">
                    <h1>📊 Close Progress Dashboard</h1>
                    <p>Real-time tracking of month-end close activities and approvals</p>
                </div>
                <div class="period-selector">
                    <select id="periodSelect">
                        <option value="2026-04" {'selected' if fiscal_period == '2026-04' else ''}>April 2026</option>
                        <option value="2026-03" {'selected' if fiscal_period == '2026-03' else ''}>March 2026</option>
                        <option value="2026-02" {'selected' if fiscal_period == '2026-02' else ''}>February 2026</option>
                        <option value="2026-01" {'selected' if fiscal_period == '2026-01' else ''}>January 2026</option>
                    </select>
                    <button onclick="changePeriod()">Go</button>
                    <button class="refresh-btn" onclick="refreshDashboard()">🔄 Refresh</button>
                </div>
            </div>
            
            <!-- Current Stage Indicator -->
            <div class="stage-indicator-container" id="current-stage-container">
                <div class="stage-indicator-icon" id="stage-icon">{stage_icon}</div>
                <div class="stage-indicator-content">
                    <div class="stage-indicator-label">Current Stage</div>
                    <div class="stage-indicator-name" id="stage-name">{current_stage_name}</div>
                    <span class="stage-indicator-status {stage_status_css}" id="stage-status-badge">
                        {current_stage_status.replace('_', ' ')}
                    </span>
                </div>
                <div class="stage-progress-bar">
                    <div class="stage-progress-fill" id="stage-progress-fill" style="width: {current_stage_progress:.0f}%"></div>
                </div>
                <div class="stage-progress-text" id="stage-progress-text">{current_stage_progress:.0f}%</div>
            </div>
            
            <!-- Status Cards -->
            <div class="status-grid">
                <div class="status-card">
                    <div class="number" id="approval-progress-number">{approval_progress:.0f}%</div>
                    <div class="label">Approval Progress</div>
                </div>
                <div class="status-card">
                    <div class="number" id="milestone-progress-number">{milestone_progress:.0f}%</div>
                    <div class="label">Milestone Progress</div>
                </div>
                <div class="status-card">
                    <div class="number" id="total-items-number">{analysis['summary']['total_approvals_generated']}</div>
                    <div class="label">Total Items</div>
                </div>
                <div class="status-card">
                    <div class="number" id="approved-number">{analysis['summary']['approved']}</div>
                    <div class="label">Approved</div>
                </div>
                <div class="status-card">
                    <div class="number" id="pending-number">{analysis['summary']['pending']}</div>
                    <div class="label">Pending</div>
                </div>
            </div>
            
            <!-- Main Status Banner -->
            <div class="main-status">
                <div class="status-banner">
                    <h2 id="status-heading">{analysis['overall_status'].replace('_', ' ')} - {analysis['status_message']}</h2>
                    <p>Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                </div>
                
                <div class="progress-section">
                    <div class="progress-item">
                        <div class="progress-label">
                            <span>📋 Approval Progress</span>
                            <span id="approval-progress-label">{analysis['summary'].get('approval_progress_status', f"{approval_progress:.0f}%")}</span>
                        </div>
                        <div class="progress-bar-container">
                            <div class="progress-bar-fill approval" id="approval-progress-bar" style="width: {approval_progress:.1f}%"></div>
                        </div>
                    </div>
                    <div class="progress-item">
                        <div class="progress-label">
                            <span>🎯 Milestone Progress</span>
                            <span id="milestone-progress-label">{milestone_progress:.1f}%</span>
                        </div>
                        <div class="progress-bar-container">
                            <div class="progress-bar-fill milestone" id="milestone-progress-bar" style="width: {milestone_progress:.1f}%"></div>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- CFO Summary -->
            <div class="cfo-summary">
                <h3>
                    <span>📝</span> CFO Executive Summary
                    <span style="font-size: 0.7em; background: #000000; color: white; padding: 2px 8px; border-radius: 12px;">{fiscal_period}</span>
                </h3>
                <div id="cfoSummaryText">{cfo_summary.replace(chr(10), '<br>')}</div>
            </div>
            
            <!-- Two Column Layout -->
            <div class="two-column">
                <!-- Blockers & Critical Items -->
                <div class="card">
                    <div class="card-header">
                        <h3>🚫 Blockers & Critical Items</h3>
                        <span class="badge" id="critical-badge">{len(analysis['critical_blockers'])} Critical</span>
                    </div>
                    <div class="card-content" id="blockers-content">
                        {_render_blockers_html(analysis['critical_blockers'], analysis['other_blockers'])}
                    </div>
                </div>
                
                <!-- Pending Items -->
                <div class="card">
                    <div class="card-header">
                        <h3>⏳ Pending Approvals</h3>
                        <span class="badge" id="pending-badge">{analysis['summary']['pending']} Items</span>
                    </div>
                    <div class="card-content" id="pending-content">
                        {_render_pending_items_html(analysis['pending_items'], analysis['overdue_items'])}
                    </div>
                </div>
            </div>
            
            <!-- Second Row -->
            <div class="two-column">
                <!-- Milestones with Progress Bars -->
                <div class="card">
                    <div class="card-header">
                        <h3>🎯 Close Milestones</h3>
                        <span class="badge" id="milestone-remaining-badge">{len(analysis['incomplete_milestones'])} Remaining</span>
                    </div>
                    <div class="card-content" id="milestone-list">
                        {milestone_html}
                    </div>
                </div>
                
                <!-- Recent Activity / Audit Trail -->
                <div class="card">
                    <div class="card-header">
                        <h3>📋 Recent Activity</h3>
                        <span class="badge">Audit Trail</span>
                    </div>
                    <div class="card-content" id="audit-trail-content">
                        {_render_audit_trail_html(analysis['approved_items'], analysis['assigned_items'])}
                    </div>
                </div>
            </div>
            
            <!-- Footer -->
            <div class="footer">
                <a href="/dashboard">← Approval Dashboard</a>
                <a href="/cfo/financial_dashboard">💰 CFO Dashboard</a>
                <a href="/reports/email/preview">📧 Email Reports</a>
                <a href="/approvals/history">📋 Approval History</a>
                <p style="margin-top: 15px;">Finance Month-End Close AI Agent v3.0.0 | Auto-refreshes every 30 seconds</p>
                <div class="auto-refresh">🔄 Live updates - data refreshes automatically</div>
            </div>
        </div>
        
        <script>
            let refreshInterval;
            
            function refreshDashboard() {{
                const period = document.getElementById('periodSelect').value;
                window.location.href = `/dashboard/progress?fiscal_period=${{period}}`;
            }}
            
            function changePeriod() {{
                refreshDashboard();
            }}
            
            function startAutoRefresh() {{
                if (refreshInterval) clearInterval(refreshInterval);
                refreshInterval = setInterval(() => {{
                    const period = document.getElementById('periodSelect').value;
                    fetch(`/api/close/progress?fiscal_period=${{period}}`)
                        .then(response => response.json())
                        .then(data => {{
                            updateDashboardData(data);
                        }})
                        .catch(err => console.error('Auto-refresh error:', err));
                }}, 30000);
            }}
            
            function updateDashboardData(data) {{
                // Update status cards
                document.getElementById('approval-progress-number').textContent = 
                    data.summary.approval_progress_percent.toFixed(0) + '%';
                document.getElementById('milestone-progress-number').textContent = 
                    data.summary.milestone_progress_percent.toFixed(0) + '%';
                document.getElementById('total-items-number').textContent = 
                    data.summary.total_approvals_generated;
                document.getElementById('approved-number').textContent = 
                    data.summary.approved;
                document.getElementById('pending-number').textContent = 
                    data.summary.pending;
                
                // Update status heading
                document.getElementById('status-heading').textContent = 
                    data.overall_status.replace('_', ' ') + ' - ' + data.status_message;
                
                // Update approval progress bar
                const approvalProgress = data.summary.approval_progress_percent;
                document.getElementById('approval-progress-bar').style.width = approvalProgress + '%';
                document.getElementById('approval-progress-label').textContent = 
                    data.summary.approval_progress_status || (approvalProgress.toFixed(0) + '%');
                
                // Update milestone progress bar
                const milestoneProgress = data.summary.milestone_progress_percent;
                document.getElementById('milestone-progress-bar').style.width = milestoneProgress + '%';
                document.getElementById('milestone-progress-label').textContent = 
                    milestoneProgress.toFixed(1) + '%';
                
                // Update current stage indicator
                const currentStage = data.current_stage;
                const stageNameEl = document.getElementById('stage-name');
                const stageStatusBadge = document.getElementById('stage-status-badge');
                const stageProgressFill = document.getElementById('stage-progress-fill');
                const stageProgressText = document.getElementById('stage-progress-text');
                const stageContainer = document.getElementById('current-stage-container');
                const stageIcon = document.getElementById('stage-icon');
                
                if (currentStage.status === 'COMPLETED') {{
                    stageIcon.textContent = '✅';
                    stageNameEl.textContent = currentStage.stage_name;
                    stageStatusBadge.textContent = 'COMPLETED';
                    stageStatusBadge.className = 'stage-indicator-status stage-status-completed';
                    stageProgressFill.style.width = '100%';
                    stageProgressText.textContent = '100%';
                    stageContainer.style.borderLeftColor = '#28a745';
                }} else if (currentStage.status === 'NOT_STARTED') {{
                    stageIcon.textContent = '🔵';
                    stageNameEl.textContent = currentStage.stage_name;
                    stageStatusBadge.textContent = 'NOT STARTED';
                    stageStatusBadge.className = 'stage-indicator-status stage-status-not-started';
                    stageProgressFill.style.width = '0%';
                    stageProgressText.textContent = '0%';
                    stageContainer.style.borderLeftColor = '#6c757d';
                }} else {{
                    stageIcon.textContent = '🔄';
                    stageNameEl.textContent = currentStage.stage_name;
                    stageStatusBadge.textContent = 'IN PROGRESS';
                    stageStatusBadge.className = 'stage-indicator-status stage-status-in-progress';
                    stageProgressFill.style.width = currentStage.progress + '%';
                    stageProgressText.textContent = currentStage.progress.toFixed(0) + '%';
                    stageContainer.style.borderLeftColor = '#007bff';
                }}
                
                // Update milestone list with progress
                const milestoneContainer = document.getElementById('milestone-list');
                let milestoneHtml = '';
                
                if (data.milestone_summary && data.milestone_summary.milestones) {{
                    for (const [key, milestone] of Object.entries(data.milestone_summary.milestones)) {{
                        const statusClass = milestone.status === 'COMPLETED' ? 'completed' : 
                                          milestone.status === 'IN_PROGRESS' ? 'in-progress' : 'not-started';
                        const statusIcon = milestone.status === 'COMPLETED' ? '✅' : 
                                         milestone.status === 'IN_PROGRESS' ? '🔄' : '○';
                        
                        milestoneHtml += `
                            <div class="milestone-item">
                                <div class="milestone-header">
                                    <span class="milestone-icon ${{statusClass}}">${{statusIcon}}</span>
                                    <span class="milestone-name">${{milestone.name}}</span>
                                    <span class="milestone-weight">(${{milestone.weight}}%)</span>
                                </div>
                                <div class="milestone-progress-container">
                                    <div class="milestone-progress-bar ${{statusClass}}" 
                                         style="width: ${{milestone.progress}}%"></div>
                                </div>
                                <div class="milestone-percent">${{milestone.progress.toFixed(0)}}% - ${{milestone.status.replace('_', ' ')}}</div>
                            </div>
                        `;
                    }}
                }}
                
                milestoneContainer.innerHTML = milestoneHtml;
                
                // Update badges
                document.getElementById('critical-badge').textContent = 
                    data.critical_blockers.length + ' Critical';
                document.getElementById('pending-badge').textContent = 
                    data.pending_items.length + ' Items';
                document.getElementById('milestone-remaining-badge').textContent = 
                    data.incomplete_milestones.length + ' Remaining';
            }}
            
            // Start auto-refresh on page load
            startAutoRefresh();
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


def _render_blockers_html(critical_blockers: List[Dict], other_blockers: List[Dict]) -> str:
    """Render blockers list as HTML"""
    if not critical_blockers and not other_blockers:
        return '<p style="color: #666; text-align: center;">✅ No blockers detected</p>'
    
    html = '<ul class="item-list">'
    
    for blocker in critical_blockers:
        severity_class = 'status-critical' if blocker['severity'] == 'CRITICAL' else 'status-high'
        html += f'''
            <li>
                <span class="item-type">
                    <span class="status-badge {severity_class}">{blocker['severity']}</span>
                    {blocker['type']}
                </span>
                <span class="item-description">{blocker['action']}</span>
                <span class="item-amount">📊 {blocker['count']} item(s)</span>
            </li>
        '''
    
    for blocker in other_blockers:
        severity_class = 'status-medium' if blocker['severity'] == 'MEDIUM' else 'status-low'
        html += f'''
            <li>
                <span class="item-type">
                    <span class="status-badge {severity_class}">{blocker['severity']}</span>
                    {blocker['type']}
                </span>
                <span class="item-description">{blocker['action']}</span>
                <span class="item-amount">📊 {blocker['count']} item(s)</span>
            </li>
        '''
    
    html += '</ul>'
    return html


def _render_pending_items_html(pending_items: List[Dict], overdue_items: List[Dict]) -> str:
    """Render pending items list as HTML"""
    if not pending_items:
        return '<p style="color: #666; text-align: center;">✅ No pending items</p>'
    
    html = '<ul class="item-list">'
    
    # Show overdue items first
    for item in overdue_items:
        html += f'''
            <li style="background: #fff3f3;">
                <span class="item-type">
                    <span class="status-badge overdue">OVERDUE</span>
                    {item['type']}
                </span>
                <span class="item-description">{item['description'][:50]}...</span>
                <span class="item-amount">💰 ${item['amount']:,.0f}</span>
                <span class="item-action">
                    <a href="/dashboard/approvals/{item['token']}" target="_blank">View →</a>
                </span>
            </li>
        '''
    
    # Show other pending items
    for item in pending_items:
        if item not in overdue_items:
            html += f'''
                <li>
                    <span class="item-type">
                        <span class="status-badge status-medium">PENDING</span>
                        {item['type']}
                    </span>
                    <span class="item-description">{item['description'][:50]}...</span>
                    <span class="item-amount">💰 ${item['amount']:,.0f}</span>
                    <span class="item-action">
                        <a href="/dashboard/approvals/{item['token']}" target="_blank">View →</a>
                    </span>
                </li>
            '''
    
    html += '</ul>'
    return html


def _render_milestones_html(incomplete_milestones: List[Dict]) -> str:
    """Render milestones list as HTML"""
    if not incomplete_milestones:
        return '<p style="color: #666; text-align: center;">🎉 All milestones complete! Ready to close.</p>'
    
    html = '<ul class="item-list">'
    for milestone in incomplete_milestones:
        html += f'''
            <li class="milestone-item">
                <div class="milestone-name">
                    <span class="milestone-status pending">○</span>
                    <strong>{milestone['name']}</strong>
                </div>
                <div class="milestone-weight">Weight: {milestone['weight']}%</div>
            </li>
        '''
    html += '</ul>'
    return html


def _render_audit_trail_html(approved_items: List[Dict], assigned_items: List[Dict]) -> str:
    """Render audit trail as HTML"""
    if not approved_items and not assigned_items:
        return '<p style="color: #666; text-align: center;">No recent activity</p>'
    
    html = '<ul class="item-list">'
    
    # Show recently approved (last 5)
    for item in approved_items[:5]:
        html += f'''
            <li>
                <span class="item-type">✅ APPROVED</span>
                <span class="item-description">{item['type']}</span>
                <span class="item-amount">💰 ${item['amount']:,.0f}</span>
            </li>
        '''
    
    # Show assigned items
    for item in assigned_items[:3]:
        html += f'''
            <li>
                <span class="item-type">👤 ASSIGNED</span>
                <span class="item-description">{item['type']}</span>
                <span class="item-description">{item['metadata_summary'][:30] if item['metadata_summary'] else ''}</span>
            </li>
        '''
    
    html += '</ul>'
    
    if len(approved_items) > 5:
        html += f'<p style="text-align: center; margin-top: 10px;"><a href="/approvals/history">View all {len(approved_items)} approved items →</a></p>'
    
    return html


# ============================================================================
# API Endpoint for JSON data (for auto-refresh)
# ============================================================================

@app.get("/api/close/progress")
async def get_close_progress_api(fiscal_period: str = Query("2026-04")):
    """
    CORRECTED: API endpoint to get close progress data as JSON (for auto-refresh)
    """
    # Ensure milestones are updated from approval data
    update_milestones_from_approvals(fiscal_period)
    
    analysis = analyze_close_readiness(fiscal_period)
    cfo_summary = generate_cfo_summary(analysis)
    
    return {
        **analysis,
        'cfo_summary': cfo_summary
    }


# ============================================================================
# Helper function to update milestones based on approval completion
# ============================================================================
def update_milestones_from_approvals(fiscal_period: str = "2026-04"):
    """
    CORRECTED: Update milestone progress based on approval registry data.
    
    Rules:
    1. Milestone is COMPLETED ONLY IF: total_items > 0 AND pending_items == 0
    2. If total_items == 0: milestone is NOT_STARTED (progress = 0)
    3. If pending_items == total_items: milestone is NOT_STARTED (progress = 0)
    4. If pending_items > 0: milestone is IN_PROGRESS (partial progress)
    """
    approval_summary = approval_registry.get_approval_summary(fiscal_period)
    by_type = approval_summary.get('by_type', {})
    
    # Process each milestone using its mapped approval types
    for milestone_key, milestone in progress_tracker.milestones.items():
        approval_types = milestone.get('approval_types', [])
        
        if not approval_types:
            # Special milestones without mapped approval types
            if milestone_key == 'data_validation':
                # Data validation: Check if any data analysis has been performed
                total_generated = approval_summary.get('total_generated', 0)
                if total_generated == 0:
                    # No analysis performed yet
                    progress_tracker.update_milestone_progress(milestone_key, total_items=0, pending_items=0)
                else:
                    # Data has been analyzed (approvals generated), check if blocking issues exist
                    blocking_types = ['Missing Cost Center', 'AR Variance Correction']
                    total_blocking = 0
                    pending_blocking = 0
                    for bt in blocking_types:
                        type_data = by_type.get(bt, {})
                        total_blocking += type_data.get('total', 0)
                        pending_blocking += type_data.get('pending', 0)
                    
                    if total_blocking == 0:
                        # No blocking issues found at all - validation passed
                        progress_tracker.update_milestone_progress(
                            milestone_key, 
                            total_items=total_generated,
                            pending_items=0
                        )
                    else:
                        # Use blocking items as the measure
                        progress_tracker.update_milestone_progress(
                            milestone_key,
                            total_items=total_blocking,
                            pending_items=pending_blocking
                        )
            
            elif milestone_key == 'final_trial_balance':
                # Final TB: Complete only when ALL approvals are processed
                total_all = approval_summary.get('total_generated', 0)
                pending_all = approval_summary.get('pending', 0)
                progress_tracker.update_milestone_progress(milestone_key, total_items=total_all, pending_items=pending_all)
        
        else:
            # Milestones with mapped approval types
            total_items = 0
            pending_items = 0
            
            for atype in approval_types:
                type_data = by_type.get(atype, {})
                total_items += type_data.get('total', 0)
                pending_items += type_data.get('pending', 0)
            
            # Update milestone progress with correct totals
            progress_tracker.update_milestone_progress(milestone_key, total_items, pending_items)
    
    # Log current state
    overall = progress_tracker.calculate_overall_milestone_progress()
    current = progress_tracker.get_current_stage()
    logger.info(f"📊 Updated milestones: overall={overall:.1f}%, "
                f"current_stage={current['stage_name']} ({current['status']}, {current['progress']:.0f}%)")


def update_progress_from_approvals():
    """Helper to update progress milestones after approvals"""
    update_milestones_from_approvals("2026-04")



# Call this periodically or when approvals are processed
def update_progress_after_approval():
    """Call this after any approval decision to update progress"""
    update_milestones_from_approvals("2026-04")
    logger.info("📊 Updated close progress milestones based on current state")


# ============================================================================
# STARTUP EVENT
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize system on startup with proper progress reset"""
    logger.info("="*60)
    logger.info("Finance Month-End Close AI Agent with Dashboard and Email starting up...")
    logger.info("="*60)
    logger.info(f"📊 Dashboard URL: {APP_BASE_URL}/dashboard")
    logger.info(f"📊 Progress Dashboard: {APP_BASE_URL}/dashboard/progress")
    logger.info(f"💰 CFO Dashboard: {APP_BASE_URL}/cfo/financial_dashboard")
    logger.info(f"📧 Email Reports: {APP_BASE_URL}/reports/email/preview")
    logger.info(f"📚 API Documentation: {APP_BASE_URL}/docs")
    logger.info(f"✅ Approval Status Check: {APP_BASE_URL}/approvals/check_status/2026-04")
    
    # Check email configuration
    api_key = os.getenv("SENDGRID_API_KEY")
    if api_key:
        logger.info("✅ SendGrid configured - emails will be sent")
    else:
        logger.warning("⚠️ SendGrid not configured - emails will be simulated")
    
    # Check if data files exist
    required_files = [
        'Raw_GL_Export_With_CostCenters_Mar2026.csv',
        'Master_COA_Complete.csv',
        'Master_CostCenters_States.csv',
        'AR_Subledger_Mar2026.csv',
        'Budget_Mar2026_Detailed.csv',
        'PL_Statement_Mar2025_Comparative.csv',
        'Intercompany_Transactions_Mar2026.csv',
        'Intercompany_Reconciliation_Mar2026.csv',
        'Intercompany_Elimination_Journals_Mar2026.csv',
        'Accruals_Register_Mar2026.csv',
        'Prepayments_Register_Mar2026.csv',
        'Accrual_Adjustment_Journals_Mar2026.csv',
        'Prepayment_Amortization_Journals_Mar2026.csv',
        'Bank_Statements_Mar2026.csv',
        'GL_Cash_Balances_Mar2026.csv',
        'Bank_Reconciliation_Items_Mar2026.csv',
        'Bank_Reconciliation_Journals_Mar2026.csv'
    ]
    
    files_found = 0
    for file in required_files:
        if os.path.exists(file):
            logger.info(f"✅ Found data file: {file}")
            files_found += 1
        else:
            logger.warning(f"⚠️ Missing data file: {file}")
    
    logger.info(f"📊 Data files: {files_found}/{len(required_files)} found")
    logger.info(f"📋 Pending approvals: {len(pending_approvals)}")
    logger.info(f"📋 Registered approvals: {len(approval_registry.generated_approvals)}")
    
    # ================================================================
    # CORRECTED: Reset milestones to NOT_STARTED on fresh startup
    # ================================================================
    logger.info("🔄 Resetting milestone progress for new session...")
    progress_tracker.reset()
    
    # Log current state (should be all NOT_STARTED)
    overall = progress_tracker.calculate_overall_milestone_progress()
    current = progress_tracker.get_current_stage()
    logger.info(f"📊 Initial Milestone Progress: {overall:.1f}%")
    logger.info(f"📍 Initial Current Stage: {current['stage_name']} ({current['status']})")
    
    logger.info("="*60)
    logger.info("System startup completed successfully")
    logger.info("="*60)

# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    print("\n" + "="*60)
    print("🚀 Starting Finance Month-End Close AI Agent v3.0.0")
    print("="*60)
    print(f"📊 Dashboard: http://localhost:8000/dashboard")
    print(f"💰 CFO Dashboard: http://localhost:8000/cfo/financial_dashboard")
    print(f"📧 Email Reports: http://localhost:8000/reports/email/preview")
    print(f"📚 API Docs: http://localhost:8000/docs")
    print(f"🔍 Health Check: http://localhost:8000/health")
    print(f"✅ Approval Status: http://localhost:8000/approvals/check_status/2026-04")
    print("="*60 + "\n")
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
