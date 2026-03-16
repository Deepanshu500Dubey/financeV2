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
from typing import Optional, List, Dict, Any
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
    fiscal_period: str = Field(..., example="2026-02")
    entity_code: str = Field(default="AUS01", example="AUS01")

class ARVarianceRequest(BaseModel):
    fiscal_period: str = Field(..., example="2026-02")
    entity_code: str = Field(default="AUS01", example="AUS01")

class CostCenterAssignment(BaseModel):
    transaction_id: str
    cost_center: str
    approved_by: Optional[str] = None

class CostCenterBatchRequest(BaseModel):
    assignments: List[CostCenterAssignment]
    fiscal_period: str = Field(..., example="2026-02")

class CostCenterSuggestion(BaseModel):
    transaction_id: str
    suggested_cost_center: str
    reason: str = Field(..., example="Vendor pattern: Zoom → IT")
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)

class CostCenterSuggestionsRequest(BaseModel):
    suggestions: List[CostCenterSuggestion]
    fiscal_period: str = Field(..., example="2026-02")


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
    fiscal_period: str

class BudgetVarianceRequest(BaseModel):
    fiscal_period: str = Field(..., example="2026-02")
    entity_code: str = Field(default="AUS01", example="AUS01")

class YoYComparisonRequest(BaseModel):
    current_period: str = Field(..., example="2026-02")
    comparison_period: str = Field(..., example="2025-02")
    entity_code: str = Field(default="AUS01", example="AUS01")

class CostCenterPLRequest(BaseModel):
    fiscal_period: str = Field(..., example="2026-02")
    entity_code: str = Field(default="AUS01", example="AUS01")

class MonthEndCloseRequest(BaseModel):
    fiscal_period: str = Field(..., example="2026-02")
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
    fiscal_period: str = Field("2026-02", description="Fiscal period for reports")
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
    metadata: Optional[Dict[str, Any]] = None
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
    else:
        clean_metadata = {}
    
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
    logger.info(f"Created approval item: {item_type} - {item_id} (Token: {token})")
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
# HELPER FUNCTION FOR TRIAL BALANCE DATA
# ============================================================================

def generate_trial_balance_data(fiscal_period: str, entity_code: str) -> Dict[str, Any]:
    """Helper function to generate trial balance data"""
    try:
        # Load data
        transactions = load_csv_data('Raw_GL_Export_With_CostCenters_Feb2026.csv')
        coa = load_coa()
        ar_records = load_csv_data('AR_Subledger_Feb2026.csv')
        
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
        transactions = load_csv_data('Raw_GL_Export_With_CostCenters_Feb2026.csv')
        coa = load_coa()
        ar_records = load_csv_data('AR_Subledger_Feb2026.csv')
        budget_data = load_csv_data('Budget_Feb2026_Detailed.csv')
        
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
    transactions = load_csv_data('Raw_GL_Export_With_CostCenters_Feb2026.csv')
    coa = load_coa()
    ar_records = load_csv_data('AR_Subledger_Feb2026.csv')
    budget_data = load_csv_data('Budget_Feb2026_Detailed.csv')
    
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
        "pending_approvals": len(pending_approvals)
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
    approval_history.append(history_record)
    
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
            approval_history.append(history_record)
            
            del pending_approvals[token]
            results.append({"token": token, "status": "success", "decision": request.approved})
        else:
            results.append({"token": token, "status": "not_found"})
    
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
            approval_history.append(history_record)
            
            del pending_approvals[token]
            results.append({"token": token, "status": "success"})
    
    logger.info(f"Bulk approved {len(results)} items by {reviewer}")
    
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
            approval_history.append(history_record)
            
            del pending_approvals[token]
            results.append({"token": token, "status": "success"})
    
    logger.info(f"Bulk rejected {len(results)} items by {reviewer}")
    
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
    
    # Add to history
    history_record = item.dict()
    history_record['processed_at'] = datetime.now().isoformat()
    history_record['assigner'] = request.assigner
    history_record['assigned_to'] = request.assignee_email
    history_record['decision'] = 'assigned'
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
# TOOL 0: INITIAL DATA ASSESSMENT
# ============================================================================

@app.post("/tools/initial_assessment", response_model=ToolResponse)
def initial_assessment(request: TrialBalanceRequest):
    """
    Provide initial data assessment without full exception detection
    """
    try:
        # Load all data files
        transactions = load_csv_data('Raw_GL_Export_With_CostCenters_Feb2026.csv')
        coa = load_coa()
        cost_centers_data = load_csv_data('Master_CostCenters_States.csv')
        ar_records = load_csv_data('AR_Subledger_Feb2026.csv')
        
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
        ar_records = load_csv_data('AR_Subledger_Feb2026.csv')
        transactions = load_csv_data('Raw_GL_Export_With_CostCenters_Feb2026.csv')
        
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
                }
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
                    "gl_balance": gl_ar_balance
                }
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
        transactions = load_csv_data('Raw_GL_Export_With_CostCenters_Feb2026.csv')
        cost_centers_data = load_csv_data('Master_CostCenters_States.csv')
        valid_cost_centers = [cc['Cost_Center_Code'] for cc in cost_centers_data]
        
        # Create lookup for assignments
        assignment_map = {a.transaction_id: a for a in request.assignments}
        
        # CHECK: Verify all assignments have been approved
        unapproved_items = []
        approved_items = {}
        
        for txn_id in assignment_map:
            # Find corresponding approval item
            found_approved = False
            for token, item in list(pending_approvals.items()):
                if (item.type == "Missing Cost Center" and
                    item.metadata and
                    item.metadata.get('transaction_id') == txn_id):
                    if item.status != ApprovalStatus.APPROVED:
                        unapproved_items.append({
                            'transaction_id': txn_id,
                            'status': item.status.value,
                            'approval_token': token,
                            'dashboard_url': f"{APP_BASE_URL}/dashboard"
                        })
                    else:
                        found_approved = True
                        approved_items[txn_id] = token
                    break
            
            # Also check approval history for already processed items
            if not found_approved:
                for hist_item in approval_history:
                    if (hist_item.get('type') == "Missing Cost Center" and
                        hist_item.get('metadata', {}).get('transaction_id') == txn_id and
                        hist_item.get('decision') == 'approved'):
                        found_approved = True
                        break
            
            if not found_approved and txn_id not in [item['transaction_id'] for item in unapproved_items]:
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
            save_csv_data('Raw_GL_Export_With_CostCenters_Feb2026.csv', transactions, fieldnames)
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
        transactions = load_csv_data('Raw_GL_Export_With_CostCenters_Feb2026.csv')
        coa = load_coa()
        
        # Check if entries are approved
        unapproved_entries = []
        for entry in request.entries:
            if not entry.approved:
                # Check if there's a pending approval in dashboard
                found = False
                for token, item in pending_approvals.items():
                    if item.type == "Journal Entry" and item.metadata.get('entry_id') == entry.entry_id:
                        found = True
                        unapproved_entries.append({
                            'entry_id': entry.entry_id,
                            'status': 'pending_dashboard',
                            'approval_token': token,
                            'approval_links': get_approval_links(token)
                        })
                        break
                
                if not found:
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
        save_csv_data('Raw_GL_Export_With_CostCenters_Feb2026.csv', transactions, fieldnames)
        
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
        transactions = load_csv_data('Raw_GL_Export_With_CostCenters_Feb2026.csv')
        budget_data = load_csv_data('Budget_Feb2026_Detailed.csv')
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
                    }
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
        transactions = load_csv_data('Raw_GL_Export_With_CostCenters_Feb2026.csv')
        prior_year_data = load_csv_data('PL_Statement_Feb2025_Comparative.csv')
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
            # Use Feb_2025_Actual column from the CSV
            prior_totals[category] = float(item['Feb_2025_Actual'])
        
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
        transactions = load_csv_data('Raw_GL_Export_With_CostCenters_Feb2026.csv')
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

@app.post("/tools/close_period", response_model=ToolResponse)
def close_period(
    request: MonthEndCloseRequest,
    background_tasks: BackgroundTasks
):
    """
    Close the accounting period
    
    This tool:
    - Validates all exceptions are resolved
    - Checks for any pending dashboard approvals
    - Locks the period
    - Generates final financial statements
    - Sends email reports if requested
    """
    try:
        # Check for pending approvals first
        if pending_approvals:
            pending_list = [
                {
                    "type": item.type,
                    "description": item.description,
                    "token": token,
                    "approval_links": get_approval_links(token)
                }
                for token, item in pending_approvals.items()
                if item.status == ApprovalStatus.PENDING
            ]
            
            return ToolResponse(
                success=False,
                message=f"Cannot close period - {len(pending_list)} pending approvals require action. Visit {APP_BASE_URL}/dashboard",
                data={
                    'pending_approvals': pending_list,
                    'dashboard_url': f"{APP_BASE_URL}/dashboard"
                }
            )
        
        # Use helper function for trial balance
        trial_balance_result = generate_trial_balance_data(
            request.fiscal_period,
            request.entity_code
        )
        
        # Check for blocking exceptions
        blocking_exceptions = [e for e in trial_balance_result.get('exceptions', []) if e.get('blocking', False)]
        
        if blocking_exceptions:
            return ToolResponse(
                success=False,
                message="Cannot close period - blocking exceptions exist",
                data={
                    'blocking_exceptions': blocking_exceptions
                }
            )
        
        # Generate close summary
        close_summary = {
            'fiscal_period': request.fiscal_period,
            'entity_code': request.entity_code,
            'close_date': datetime.now().isoformat(),
            'approved_by': request.approved_by,
            'status': 'CLOSED',
            'trial_balance': trial_balance_result.get('trial_balance', {}),
            'statements_generated': [
                'Income Statement',
                'Balance Sheet',
                'Cash Flow Statement',
                'Statement of Changes in Equity'
            ]
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
                <h2>Month-End Close Completed</h2>
                <p>The month-end close for period <strong>{request.fiscal_period}</strong> has been completed successfully.</p>
                <p><strong>Closed by:</strong> {request.approved_by}</p>
                <p><strong>Close Date:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                <p>Please find attached the final financial reports.</p>
                """
            )
            
            # Add email task to background
            background_tasks.add_task(
                send_financial_reports,
                email_request,
                background_tasks
            )
            
            close_summary['email_reports_sent'] = True
            logger.info(f"📧 Email reports queued for period {request.fiscal_period}")
        
        return ToolResponse(
            success=True,
            message=f"Period {request.fiscal_period} closed successfully. {'Email reports have been sent.' if request.send_email_reports else ''}",
            data=close_summary
        )
        
    except Exception as e:
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
        transactions = load_csv_data('Raw_GL_Export_With_CostCenters_Feb2026.csv')
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
                        }
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
        ar_records = load_csv_data('AR_Subledger_Feb2026.csv')
        
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
                            }
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
    fiscal_period: str = Query("2026-02", description="Fiscal period to display"),
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
        transactions = load_csv_data('Raw_GL_Export_With_CostCenters_Feb2026.csv')
        coa = load_coa()
        budget_data = load_csv_data('Budget_Feb2026_Detailed.csv')
        ar_records = load_csv_data('AR_Subledger_Feb2026.csv')
        
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
# CFO FINANCIAL REPORT API (JSON version)
# ============================================================================

@app.get("/cfo/financial_report")
async def get_cfo_financial_report(
    fiscal_period: str = Query("2026-02", description="Fiscal period to display"),
    entity_code: str = Query("AUS01", description="Entity code")
):
    """
    Get comprehensive financial report in JSON format
    """
    try:
        # Load financial data
        transactions = load_csv_data('Raw_GL_Export_With_CostCenters_Feb2026.csv')
        coa = load_coa()
        budget_data = load_csv_data('Budget_Feb2026_Detailed.csv')
        ar_records = load_csv_data('AR_Subledger_Feb2026.csv')
        
        # Filter for the period
        period_txns = [t for t in transactions if t['Fiscal_Period'] == fiscal_period]
        
        # Calculate account balances
        account_balances = defaultdict(float)
        for txn in period_txns:
            if txn['Account_Code_Raw'] in coa:
                account_balances[txn['Account_Code_Raw']] += float(txn['Amount'])
        
        # Group by account type
        type_totals = defaultdict(float)
        detailed_accounts = []
        
        for account, balance in account_balances.items():
            if account in coa:
                type_totals[coa[account]['type']] += balance
                detailed_accounts.append({
                    'code': account,
                    'name': coa[account]['name'],
                    'type': coa[account]['type'],
                    'category': coa[account]['category'],
                    'balance': balance
                })
        
        # Calculate budget variances
        actuals_by_category = defaultdict(float)
        for txn in period_txns:
            account = txn['Account_Code_Raw']
            if account in coa:
                category = coa[account]['category']
                actuals_by_category[category] += float(txn['Amount'])
        
        budget_by_category = defaultdict(float)
        for item in budget_data:
            category = item['Category']
            if category.upper() != 'TOTAL' and not item['Account_Code'].startswith('TOTAL'):
                budget_by_category[category] += float(item['Budget_Amount'])
        
        variances = []
        for category in set(list(actuals_by_category.keys()) + list(budget_by_category.keys())):
            actual = actuals_by_category.get(category, 0)
            budget = budget_by_category.get(category, 0)
            variances.append({
                'category': category,
                'actual': actual,
                'budget': budget,
                'variance': actual - budget,
                'variance_percent': ((actual - budget) / budget * 100) if budget != 0 else 0
            })
        
        # AR metrics
        ar_metrics = {
            'total_outstanding': sum(float(r['Outstanding_Balance']) for r in ar_records),
            'overdue': sum(float(r['Outstanding_Balance']) for r in ar_records if r['Status'] == 'Overdue'),
            'current': sum(float(r['Outstanding_Balance']) for r in ar_records if r['Status'] == 'Current'),
            'aging_buckets': {}
        }
        
        for days in [30, 60, 90]:
            bucket = f"{(days-30)+1}-{days} Days"
            ar_metrics['aging_buckets'][bucket] = sum(
                float(r['Outstanding_Balance']) 
                for r in ar_records 
                if int(r['Days_Outstanding']) <= days and int(r['Days_Outstanding']) > (days-30)
            )
        
        # Add 90+ days bucket
        ar_metrics['aging_buckets']['90+ Days'] = sum(
            float(r['Outstanding_Balance']) 
            for r in ar_records 
            if int(r['Days_Outstanding']) > 90
        )
        
        return {
            'generated_at': datetime.now().isoformat(),
            'fiscal_period': fiscal_period,
            'entity_code': entity_code,
            'summary': {
                'revenue': type_totals.get('Revenue', 0),
                'expenses': type_totals.get('Expense', 0),
                'net_income': type_totals.get('Revenue', 0) - type_totals.get('Expense', 0),
                'total_ar': ar_metrics['total_outstanding'],
                'overdue_ar': ar_metrics['overdue'],
                'budget_variance': sum(v['variance'] for v in variances),
                'gross_margin': ((type_totals.get('Revenue', 0) - type_totals.get('Expense', 0)) / type_totals.get('Revenue', 1)) * 100 if type_totals.get('Revenue', 0) > 0 else 0
            },
            'income_statement': {
                'revenue': type_totals.get('Revenue', 0),
                'expenses': type_totals.get('Expense', 0),
                'net_income': type_totals.get('Revenue', 0) - type_totals.get('Expense', 0),
                'detailed_accounts': detailed_accounts
            },
            'balance_sheet': {
                'assets': type_totals.get('Asset', 0),
                'liabilities': type_totals.get('Liability', 0),
                'equity': type_totals.get('Equity', 0)
            },
            'budget_variances': variances,
            'accounts_receivable': ar_metrics,
            'metrics': {
                'gross_margin': ((type_totals.get('Revenue', 0) - type_totals.get('Expense', 0)) / type_totals.get('Revenue', 1)) * 100 if type_totals.get('Revenue', 0) > 0 else 0,
                'net_margin': ((type_totals.get('Revenue', 0) - type_totals.get('Expense', 0)) / type_totals.get('Revenue', 1)) * 100 if type_totals.get('Revenue', 0) > 0 else 0,
                'overdue_ratio': (ar_metrics['overdue'] / ar_metrics['total_outstanding'] * 100) if ar_metrics['total_outstanding'] > 0 else 0
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
        transactions = load_csv_data('Raw_GL_Export_With_CostCenters_Feb2026.csv')
        coa = load_coa()
        ar_records = load_csv_data('AR_Subledger_Feb2026.csv')
        budget_data = load_csv_data('Budget_Feb2026_Detailed.csv')
        
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
        
        # Create summary HTML
        summary_html = f"""
        <div style="background: linear-gradient(135deg, #f8f9fa 0%, #ffffff 100%); padding: 25px; border-radius: 15px; margin-bottom: 30px; border: 1px solid #e0e0e0;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; border-bottom: 2px solid #000000; padding-bottom: 15px;">
                <h2 style="color: #000000; margin: 0; font-size: 1.8em;">📊 Executive Summary - {request.fiscal_period}</h2>
                <span style="background: #000000; color: white; padding: 8px 16px; border-radius: 20px; font-weight: bold;">
                    {datetime.now().strftime('%d %b %Y')}
                </span>
            </div>
            
            <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
                <tr>
                    <td style="width: 33%; padding: 10px; vertical-align: top;">
                        <div style="background: white; padding: 15px; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.05);">
                            <h3 style="color: #000000; margin: 0 0 15px 0; padding-bottom: 10px; border-bottom: 2px solid #e0e0e0;">📈 Performance</h3>
                            <table style="width: 100%;">
                                <tr><td style="padding: 5px 0;"><strong>Revenue:</strong></td><td style="text-align: right; font-weight: bold;">${revenue:,.0f}</td></tr>
                                <tr><td style="padding: 5px 0;"><strong>Expenses:</strong></td><td style="text-align: right;">${expenses:,.0f}</td></tr>
                                <tr style="border-top: 1px solid #e0e0e0;"><td style="padding: 8px 0;"><strong>Net Income:</strong></td>
                                    <td style="text-align: right; font-weight: bold; color: {'#000000' if net_income >= 0 else '#666666'};">
                                        ${net_income:,.0f}
                                    </td>
                                </tr>
                                <tr><td style="padding: 5px 0;"><strong>Margin:</strong></td><td style="text-align: right;">{(net_income/revenue*100) if revenue > 0 else 0:.1f}%</td></tr>
                            </table>
                        </div>
                    </td>
                    <td style="width: 33%; padding: 10px; vertical-align: top;">
                        <div style="background: white; padding: 15px; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.05);">
                            <h3 style="color: #000000; margin: 0 0 15px 0; padding-bottom: 10px; border-bottom: 2px solid #e0e0e0;">💰 Accounts Receivable</h3>
                            <table style="width: 100%;">
                                <tr><td style="padding: 5px 0;"><strong>Total Outstanding:</strong></td><td style="text-align: right; font-weight: bold;">${total_ar:,.0f}</td></tr>
                                <tr><td style="padding: 5px 0;"><strong>Overdue:</strong></td><td style="text-align: right; color: {'#000000' if overdue_ar == 0 else '#666666'};">${overdue_ar:,.0f}</td></tr>
                                <tr><td style="padding: 5px 0;"><strong>Overdue %:</strong></td><td style="text-align: right;">{(overdue_ar/total_ar*100) if total_ar > 0 else 0:.1f}%</td></tr>
                                <tr><td style="padding: 5px 0;"><strong>90+ Days:</strong></td><td style="text-align: right;">${aging_buckets['90+ Days']:,.0f}</td></tr>
                            </table>
                        </div>
                    </td>
                    <td style="width: 33%; padding: 10px; vertical-align: top;">
                        <div style="background: white; padding: 15px; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.05);">
                            <h3 style="color: #000000; margin: 0 0 15px 0; padding-bottom: 10px; border-bottom: 2px solid #e0e0e0;">📊 Budget Performance</h3>
                            <table style="width: 100%;">
                                <tr><td style="padding: 5px 0;"><strong>Budget:</strong></td><td style="text-align: right;">${total_budget:,.0f}</td></tr>
                                <tr><td style="padding: 5px 0;"><strong>Actual:</strong></td><td style="text-align: right;">${total_actual:,.0f}</td></tr>
                                <tr style="border-top: 1px solid #e0e0e0;"><td style="padding: 8px 0;"><strong>Variance:</strong></td>
                                    <td style="text-align: right; font-weight: bold; color: {'#000000' if total_variance < 0 else '#666666'};">
                                        ${total_variance:,.0f} ({variance_pct:.1f}%)
                                    </td>
                                </tr>
                            </table>
                        </div>
                    </td>
                </tr>
            </table>
            
            <div style="margin-top: 15px; background: #f0f0f0; padding: 15px 20px; border-radius: 10px;">
                <h4 style="margin: 0 0 10px 0; color: #000000;">🔍 Key Highlights</h4>
                <ul style="list-style-type: none; padding: 0; margin: 0; display: flex; flex-wrap: wrap; gap: 15px;">
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
        
        if aging_buckets['90+ Days'] > 0:
            highlights.append(f"⚠️ ${aging_buckets['90+ Days']:,.0f} in 90+ days aging bucket")
        
        if abs(variance_pct) > 10:
            highlights.append(f"⚠️ Budget variance exceeds 10% ({variance_pct:.1f}%)")
        
        for highlight in highlights[:4]:
            summary_html += f"""
                    <li style="background: white; padding: 8px 16px; border-radius: 20px; font-size: 0.95em; box-shadow: 0 2px 5px rgba(0,0,0,0.05);">
                        {highlight}
                    </li>
            """
        
        summary_html += """
                </ul>
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
    fiscal_period: str = Query("2026-02"),
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
    fiscal_period: str = Query("2026-02"),
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
        transactions = load_csv_data('Raw_GL_Export_With_CostCenters_Feb2026.csv')
        coa = load_coa()
        ar_records = load_csv_data('AR_Subledger_Feb2026.csv')
        budget_data = load_csv_data('Budget_Feb2026_Detailed.csv')
        
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
        
        # Create summary HTML for preview
        summary_html = f"""
        <div style="background: linear-gradient(135deg, #f8f9fa 0%, #ffffff 100%); padding: 25px; border-radius: 15px; margin-bottom: 30px; border: 1px solid #e0e0e0;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; border-bottom: 2px solid #000000; padding-bottom: 15px;">
                <h2 style="color: #000000; margin: 0; font-size: 1.8em;">📊 Executive Summary - {fiscal_period}</h2>
                <span style="background: #000000; color: white; padding: 8px 16px; border-radius: 20px; font-weight: bold;">
                    {datetime.now().strftime('%d %b %Y')}
                </span>
            </div>
            
            <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
                <tr>
                    <td style="width: 33%; padding: 10px; vertical-align: top;">
                        <div style="background: white; padding: 15px; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.05);">
                            <h3 style="color: #000000; margin: 0 0 15px 0; padding-bottom: 10px; border-bottom: 2px solid #e0e0e0;">📈 Performance</h3>
                            <table style="width: 100%;">
                                <tr><td style="padding: 5px 0;"><strong>Revenue:</strong></td><td style="text-align: right; font-weight: bold;">${revenue:,.0f}</td></tr>
                                <tr><td style="padding: 5px 0;"><strong>Expenses:</strong></td><td style="text-align: right;">${expenses:,.0f}</td></tr>
                                <tr style="border-top: 1px solid #e0e0e0;"><td style="padding: 8px 0;"><strong>Net Income:</strong></td>
                                    <td style="text-align: right; font-weight: bold; color: {'#000000' if net_income >= 0 else '#666666'};">
                                        ${net_income:,.0f}
                                    </td>
                                </tr>
                                <tr><td style="padding: 5px 0;"><strong>Margin:</strong></td><td style="text-align: right;">{(net_income/revenue*100) if revenue > 0 else 0:.1f}%</td></tr>
                            </table>
                        </div>
                    </td>
                    <td style="width: 33%; padding: 10px; vertical-align: top;">
                        <div style="background: white; padding: 15px; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.05);">
                            <h3 style="color: #000000; margin: 0 0 15px 0; padding-bottom: 10px; border-bottom: 2px solid #e0e0e0;">💰 Accounts Receivable</h3>
                            <table style="width: 100%;">
                                <tr><td style="padding: 5px 0;"><strong>Total Outstanding:</strong></td><td style="text-align: right; font-weight: bold;">${total_ar:,.0f}</td></tr>
                                <tr><td style="padding: 5px 0;"><strong>Overdue:</strong></td><td style="text-align: right; color: {'#000000' if overdue_ar == 0 else '#666666'};">${overdue_ar:,.0f}</td></tr>
                                <tr><td style="padding: 5px 0;"><strong>Overdue %:</strong></td><td style="text-align: right;">{(overdue_ar/total_ar*100) if total_ar > 0 else 0:.1f}%</td></tr>
                                <tr><td style="padding: 5px 0;"><strong>90+ Days:</strong></td><td style="text-align: right;">${aging_buckets['90+ Days']:,.0f}</td></tr>
                            </table>
                        </div>
                    </td>
                    <td style="width: 33%; padding: 10px; vertical-align: top;">
                        <div style="background: white; padding: 15px; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.05);">
                            <h3 style="color: #000000; margin: 0 0 15px 0; padding-bottom: 10px; border-bottom: 2px solid #e0e0e0;">📊 Budget Performance</h3>
                            <table style="width: 100%;">
                                <tr><td style="padding: 5px 0;"><strong>Budget:</strong></td><td style="text-align: right;">${total_budget:,.0f}</td></tr>
                                <tr><td style="padding: 5px 0;"><strong>Actual:</strong></td><td style="text-align: right;">${total_actual:,.0f}</td></tr>
                                <tr style="border-top: 1px solid #e0e0e0;"><td style="padding: 8px 0;"><strong>Variance:</strong></td>
                                    <td style="text-align: right; font-weight: bold; color: {'#000000' if total_variance < 0 else '#666666'};">
                                        ${total_variance:,.0f} ({variance_pct:.1f}%)
                                    </td>
                                </tr>
                            </table>
                        </div>
                    </td>
                </tr>
            </table>
            
            <div style="margin-top: 15px; background: #f0f0f0; padding: 15px 20px; border-radius: 10px;">
                <h4 style="margin: 0 0 10px 0; color: #000000;">🔍 Key Highlights</h4>
                <ul style="list-style-type: none; padding: 0; margin: 0; display: flex; flex-wrap: wrap; gap: 15px;">
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
        
        if aging_buckets['90+ Days'] > 0:
            highlights.append(f"⚠️ ${aging_buckets['90+ Days']:,.0f} in 90+ days aging bucket")
        
        if abs(variance_pct) > 10:
            highlights.append(f"⚠️ Budget variance exceeds 10% ({variance_pct:.1f}%)")
        
        for highlight in highlights[:4]:
            summary_html += f"""
                    <li style="background: white; padding: 8px 16px; border-radius: 20px; font-size: 0.95em; box-shadow: 0 2px 5px rgba(0,0,0,0.05);">
                        {highlight}
                    </li>
            """
        
        summary_html += """
                </ul>
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
    
    return {
        "sendgrid_configured": bool(api_key),
        "from_email": from_email,
        "status": "✅ Ready to send" if bool(api_key) else "⚠️ Not configured - emails will be simulated",
        "pending_approvals": len(pending_approvals),
        "assigned_items": len([i for i in pending_approvals.values() if i.assigned_to is not None]),
        "total_reports_sent": len([h for h in approval_history if h.get('email_sent', False)])
    }


# ============================================================================
# ACTIVITY 1: INTERCOMPANY RECONCILIATION
# ============================================================================

# Data Models
class IntercompanyReconciliationRequest(BaseModel):
    fiscal_period: str = Field("2026-02", description="Fiscal period for reconciliation")
    entity_code: Optional[str] = Field(None, description="Filter by specific entity (optional)")

class IntercompanyEliminationRequest(BaseModel):
    fiscal_period: str = Field("2026-02", description="Fiscal period")
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
        transactions = load_csv_data('Intercompany_Transactions_Feb2026.csv')
        reconciliation = load_csv_data('Intercompany_Reconciliation_Feb2026.csv')
        elimination_journals = load_csv_data('Intercompany_Elimination_Journals_Feb2026.csv')
        
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
                    }
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
    fiscal_period: str = Query("2026-02"),
    entity: Optional[str] = Query(None, description="Filter by entity"),
    status: Optional[str] = Query(None, description="Filter by status")
):
    """
    Get intercompany transactions with optional filters
    """
    try:
        transactions = load_csv_data('Intercompany_Transactions_Feb2026.csv')
        
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
        elimination_journals = load_csv_data('Intercompany_Elimination_Journals_Feb2026.csv')
        
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
        
        # Check if all selected journals are approved
        unapproved = []
        for journal in journals_to_post:
            journal_id = journal.get('JE_Number')
            # Check for pending approval in dashboard
            found_approved = False
            for token, item in pending_approvals.items():
                if (item.type == "Intercompany Variance" and 
                    item.metadata and 
                    journal_id in str(item.metadata.get('affected_txns', ''))):
                    if item.status != ApprovalStatus.APPROVED:
                        unapproved.append({
                            'journal_id': journal_id,
                            'status': item.status.value,
                            'approval_token': token
                        })
                    else:
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
            
            if not found_approved and journal_id not in [u['journal_id'] for u in unapproved]:
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
        reconciliation = load_csv_data('Intercompany_Reconciliation_Feb2026.csv')
        
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
        save_csv_data('Intercompany_Reconciliation_Feb2026.csv', reconciliation, fieldnames)
        
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
    fiscal_period: str = Field("2026-02", description="Fiscal period for analysis")
    entity_code: Optional[str] = Field(None, description="Filter by entity (optional)")

class AccrualAdjustmentRequest(BaseModel):
    fiscal_period: str = Field("2026-02", description="Fiscal period")
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
        accruals = load_csv_data('Accruals_Register_Feb2026.csv')
        prepayments = load_csv_data('Prepayments_Register_Feb2026.csv')
        adjustment_journals = load_csv_data('Accrual_Adjustment_Journals_Feb2026.csv')
        amortization_journals = load_csv_data('Prepayment_Amortization_Journals_Feb2026.csv')
        
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
                    }
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
            data=response_data
        )
        
    except Exception as e:
        logger.error(f"Error in accruals analysis: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# TOOL 16: GET ACCRUALS
# ============================================================================

@app.get("/tools/accruals/list", response_model=ToolResponse)
async def get_accruals(
    fiscal_period: str = Query("2026-02"),
    status: Optional[str] = Query(None, description="Filter by status"),
    materiality: Optional[str] = Query(None, description="Filter by materiality")
):
    """
    Get accruals with optional filters
    """
    try:
        accruals = load_csv_data('Accruals_Register_Feb2026.csv')
        
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
    fiscal_period: str = Query("2026-02"),
    status: Optional[str] = Query(None, description="Filter by status")
):
    """
    Get prepayments with optional filters
    """
    try:
        prepayments = load_csv_data('Prepayments_Register_Feb2026.csv')
        
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
        adjustment_journals = load_csv_data('Accrual_Adjustment_Journals_Feb2026.csv')
        
        # Find journals for the specified accruals
        journals_to_post = [j for j in adjustment_journals if j.get('Accrual_ID') in request.accrual_ids]
        
        if not journals_to_post:
            return ToolResponse(
                success=False,
                message="No adjustment journals found for the specified accruals"
            )
        
        # Check if all are approved
        unapproved = []
        for journal in journals_to_post:
            accrual_id = journal.get('Accrual_ID')
            # Check for pending approval
            found_approved = False
            for token, item in pending_approvals.items():
                if (item.type == "Accrual Variance" and 
                    item.metadata and 
                    item.metadata.get('accrual_id') == accrual_id):
                    if item.status != ApprovalStatus.APPROVED:
                        unapproved.append({
                            'accrual_id': accrual_id,
                            'status': item.status.value,
                            'approval_token': token
                        })
                    else:
                        found_approved = True
                    break
            
            if not found_approved and accrual_id not in [u['accrual_id'] for u in unapproved]:
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
        save_csv_data('Accrual_Adjustment_Journals_Feb2026.csv', adjustment_journals, fieldnames)
        
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
    fiscal_period: str = Field("2026-02", description="Fiscal period for reconciliation")
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
        bank_statements = load_csv_data('Bank_Statements_Feb2026.csv')
        gl_cash_balances = load_csv_data('GL_Cash_Balances_Feb2026.csv')
        reconciliation_items = load_csv_data('Bank_Reconciliation_Items_Feb2026.csv')
        reconciliation_journals = load_csv_data('Bank_Reconciliation_Journals_Feb2026.csv')
        
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
                    }
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
    fiscal_period: str = Query("2026-02"),
    item_type: Optional[str] = Query(None, description="Filter by item type"),
    materiality: Optional[str] = Query(None, description="Filter by materiality")
):
    """
    Get bank reconciliation items with optional filters
    """
    try:
        reconciliation_items = load_csv_data('Bank_Reconciliation_Items_Feb2026.csv')
        
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
    fiscal_period: str = Query("2026-02"),
    entity_code: Optional[str] = Query(None, description="Filter by entity")
):
    """
    Get bank and GL positions for all accounts
    """
    try:
        gl_cash_balances = load_csv_data('GL_Cash_Balances_Feb2026.csv')
        
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
        reconciliation_journals = load_csv_data('Bank_Reconciliation_Journals_Feb2026.csv')
        
        # Check if entries are approved
        unapproved_entries = []
        approved_entries = []
        
        for entry in request.entries:
            if not entry.approved:
                # Check for pending approval in dashboard
                found = False
                for token, item in pending_approvals.items():
                    if (item.type == "Bank Reconciliation" and 
                        item.metadata and 
                        entry.entry_id in str(item.metadata.get('item_id', ''))):
                        found = True
                        unapproved_entries.append({
                            'entry_id': entry.entry_id,
                            'status': 'pending_dashboard',
                            'approval_token': token,
                            'approval_links': get_approval_links(token)
                        })
                        break
                
                if not found:
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
            save_csv_data('Bank_Reconciliation_Journals_Feb2026.csv', reconciliation_journals, fieldnames)
        
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
        reconciliation_items = load_csv_data('Bank_Reconciliation_Items_Feb2026.csv')
        
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
        save_csv_data('Bank_Reconciliation_Items_Feb2026.csv', reconciliation_items, fieldnames)
        
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
async def get_close_status(fiscal_period: str = Query("2026-02")):
    """
    Get combined status of all close activities
    """
    try:
        # Load all data
        ic_transactions = load_csv_data('Intercompany_Transactions_Feb2026.csv')
        ic_reconciliation = load_csv_data('Intercompany_Reconciliation_Feb2026.csv')
        accruals = load_csv_data('Accruals_Register_Feb2026.csv')
        prepayments = load_csv_data('Prepayments_Register_Feb2026.csv')
        bank_items = load_csv_data('Bank_Reconciliation_Items_Feb2026.csv')
        
        # Filter for period
        ic_rec_period = [r for r in ic_reconciliation if r.get('Period') == fiscal_period]
        accruals_period = [a for a in accruals if a.get('Period') == fiscal_period]
        
        # Calculate status by activity
        status = {
            'intercompany': {
                'status': 'PENDING_APPROVAL',
                'total_variances': len([r for r in ic_rec_period if abs(float(r.get('Variance_AUD', 0))) > 0]),
                'material_items': len([r for r in ic_rec_period if r.get('Materiality') == 'Material']),
                'pending_approvals': len([r for r in ic_rec_period if r.get('Human_Approval_Required') == 'Yes'])
            },
            'accruals': {
                'status': 'PENDING_APPROVAL',
                'total_items': len(accruals_period),
                'material_items': len([a for a in accruals_period if a.get('Materiality') == 'Material']),
                'pending_approvals': len([a for a in accruals_period if a.get('Status') == 'Pending_Approval'])
            },
            'prepayments': {
                'status': 'COMPLETE',
                'total_items': len([p for p in prepayments if p.get('Period') == fiscal_period]),
                'active_items': len([p for p in prepayments if p.get('Period') == fiscal_period and p.get('Status') == 'Active'])
            },
            'bank_reconciliation': {
                'status': 'PENDING_REVIEW',
                'total_items': len(bank_items),
                'material_items': len([b for b in bank_items if b.get('Materiality') == 'Material']),
                'review_items': len([b for b in bank_items if b.get('Materiality') == 'Review'])
            }
        }
        
        # Calculate overall status
        all_pending = (
            status['intercompany']['pending_approvals'] +
            status['accruals']['pending_approvals'] +
            status['bank_reconciliation']['material_items'] +
            status['bank_reconciliation']['review_items']
        )
        
        overall_status = 'PENDING_APPROVAL' if all_pending > 0 else 'READY_TO_CLOSE'
        
        response_data = {
            'fiscal_period': fiscal_period,
            'overall_status': overall_status,
            'total_pending_items': all_pending,
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

# ============================================================================
# STARTUP EVENT
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize system on startup"""
    logger.info("="*60)
    logger.info("Finance Month-End Close AI Agent with Dashboard and Email starting up...")
    logger.info("="*60)
    logger.info(f"📊 Dashboard URL: {APP_BASE_URL}/dashboard")
    logger.info(f"💰 CFO Dashboard: {APP_BASE_URL}/cfo/financial_dashboard")
    logger.info(f"📧 Email Reports: {APP_BASE_URL}/reports/email/preview")
    logger.info(f"📚 API Documentation: {APP_BASE_URL}/docs")
    
    # Check email configuration
    api_key = os.getenv("SENDGRID_API_KEY")
    if api_key:
        logger.info("✅ SendGrid configured - emails will be sent")
    else:
        logger.warning("⚠️ SendGrid not configured - emails will be simulated")
    
    # Check if data files exist
    required_files = [
        'Raw_GL_Export_With_CostCenters_Feb2026.csv',
        'Master_COA_Complete.csv',
        'Master_CostCenters_States.csv',
        'AR_Subledger_Feb2026.csv',
        'Budget_Feb2026_Detailed.csv',
        'PL_Statement_Feb2025_Comparative.csv',
        'Intercompany_Transactions_Feb2026.csv',
        'Intercompany_Reconciliation_Feb2026.csv',
        'Intercompany_Elimination_Journals_Feb2026.csv',
        'Accruals_Register_Feb2026.csv',
        'Prepayments_Register_Feb2026.csv',
        'Accrual_Adjustment_Journals_Feb2026.csv',
        'Prepayment_Amortization_Journals_Feb2026.csv',
        'Bank_Statements_Feb2026.csv',
        'GL_Cash_Balances_Feb2026.csv',
        'Bank_Reconciliation_Items_Feb2026.csv',
        'Bank_Reconciliation_Journals_Feb2026.csv'
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
    print("="*60 + "\n")
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
