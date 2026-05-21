"""
IBM Bob Demo Dataset Generator
Creates 1,000 records each for:
- IBM BOB 1: Group P&L Line Items
- IBM BOB 2: Workforce Cost & Output
- IBM BOB 3: ESG Cost & KPI
- Enhanced GL with 3,000 additional records
"""

import csv
import random
from datetime import datetime, timedelta
from decimal import Decimal

# Reference Data
ENTITIES = ['AUS01', 'NZL01', 'PNG01', 'FJI01']
COST_CENTERS = ['NSW', 'VIC', 'QLD', 'WA', 'SA', 'TAS', 'NT', 'ACT', 'CORP', 'IT', 'FIN', 'HR', 'MKT', 'OPS', 'R&D']
COST_CENTER_NAMES = {
    'NSW': 'New South Wales Operations',
    'VIC': 'Victoria Operations',
    'QLD': 'Queensland Operations',
    'WA': 'Western Australia Operations',
    'SA': 'South Australia Operations',
    'TAS': 'Tasmania Operations',
    'NT': 'Northern Territory Operations',
    'ACT': 'Australian Capital Territory',
    'CORP': 'Corporate Head Office',
    'IT': 'Information Technology',
    'FIN': 'Finance & Accounting',
    'HR': 'Human Resources',
    'MKT': 'Marketing & Sales',
    'OPS': 'Operations & Logistics',
    'R&D': 'Research & Development'
}

VENDORS = ['IBM Australia', 'Google Ads', 'QBE Insurance', 'Energy Australia', 'Melbourne Airport', 
           'Deloitte', 'LinkedIn', 'SAP Australia', 'Qantas Commercial', 'Officeworks', 'AWS', 
           'Snowflake', 'Microsoft', 'Oracle', 'Salesforce']

# P&L Specific Data
PL_SECTIONS = {
    'Revenue': ['4000', '4010', '4020'],
    'Cost of revenue': ['6000', '6010', '6020', '6030'],
    'General and administrative': ['5000', '5010', '5300', '5320'],
    'Sales and marketing': ['5500', '5510', '5520'],
    'Research and development': ['5200', '5210', '5700'],
    'Other operating expenses': ['5100', '5110', '5120'],
    'Other income / expense': ['4100', '5910', '5920'],
    'Tax provision': ['2210']
}

PL_LINE_ITEMS = {
    '4000': ('Product sales', 'Operating Revenue'),
    '4010': ('Service revenue', 'Operating Revenue'),
    '4020': ('Subscription revenue', 'Operating Revenue'),
    '4100': ('Interest income', 'Non-Operating Revenue'),
    '5000': ('Salaries and wages', 'Personnel'),
    '5010': ('Employee benefits', 'Personnel'),
    '5100': ('Office rent', 'Facilities'),
    '5110': ('Utilities', 'Facilities'),
    '5120': ('Office supplies', 'Facilities'),
    '5200': ('Software licenses', 'IT'),
    '5210': ('Cloud services', 'IT'),
    '5300': ('Professional services', 'External'),
    '5320': ('Audit fees', 'External'),
    '5500': ('Campaign spend', 'Sales'),
    '5510': ('Advertising', 'Sales'),
    '5520': ('Events', 'Sales'),
    '5700': ('Training', 'Development'),
    '5910': ('Interest expense', 'Finance'),
    '5920': ('FX Loss', 'Finance'),
    '6000': ('Cost of goods sold', 'COGS'),
    '6010': ('Direct materials', 'COGS'),
    '6020': ('Direct labor', 'COGS'),
    '6030': ('Manufacturing overhead', 'COGS'),
    '2210': ('Income tax payable', 'Current Liabilities')
}

# Workforce Data
BUSINESS_UNITS = ['Finance', 'IT', 'Sales', 'Operations', 'Commercial', 'FP&A', 'Procurement', 'Customer Care']
DEPARTMENTS = ['Finance', 'IT', 'Sales', 'Operations', 'Commercial', 'FP&A', 'Procurement', 'Customer Care']
ROLES = ['Finance Analyst', 'Data Engineer', 'Customer Service Lead', 'Operations Planner', 
         'Revenue Analyst', 'FP&A Manager', 'Procurement Specialist', 'Inventory Coordinator',
         'Sales Manager', 'Controller']
OUTPUT_METRICS = {
    'Finance': 'close_tasks',
    'IT': 'tickets_resolved',
    'Sales': 'deals_supported',
    'Operations': 'flights_supported',
    'Commercial': 'revenue_cases',
    'FP&A': 'forecast_models',
    'Procurement': 'pos_processed',
    'Customer Care': 'cases_resolved'
}
RISK_FLAGS = [None, 'High overtime', 'Low utilisation high cost', 'Contractor dependency']
PERFORMANCE_RATINGS = ['Low', 'Medium', 'High']

# ESG Data
ESG_CATEGORIES = ['Energy usage', 'Renewable sourcing premium', 'Carbon offsets', 'Fleet emissions',
                  'Waste reduction', 'Sustainable packaging', 'Supplier ESG premium', 'Compliance assurance']
ESG_ACCOUNTS = {
    'Energy usage': ('5110', 'Utilities'),
    'Renewable sourcing premium': ('6000', 'Cost of Goods Sold'),
    'Carbon offsets': ('5300', 'Professional Services'),
    'Fleet emissions': ('5400', 'Travel'),
    'Waste reduction': ('5600', 'Telecommunications'),
    'Sustainable packaging': ('6010', 'Direct Materials'),
    'Supplier ESG premium': ('6010', 'Direct Materials'),
    'Compliance assurance': ('5320', 'Audit Fees')
}
ESG_SUPPLIERS = ['Energy Australia', 'Origin Energy', 'Climate Active Advisor', 'Carbon Neutral Pty Ltd',
                 'Sustainable Packaging Co', 'Green Freight', 'EcoVadis', 'Bureau Veritas']
ESG_KPIS = ['tCO2e avoided', 'renewable_kwh', 'waste_kg_reduced', 'supplier_score', 'audit_evidence_count']
DISCLOSURE_STATUS = ['Complete', 'Partial', 'Missing']
AUDIT_READINESS = ['Ready', 'Needs review', 'Partial']

CURRENCIES = ['AUD', 'NZD', 'USD', 'GBP']
TAX_CODES = ['GST', 'GST-FREE', 'INPUT', 'EXPORT']
SOURCE_SYSTEMS = ['Manual Entry', 'API Import', 'SAP', 'Oracle', 'Workday']

def generate_march_date():
    """Generate a random date in March 2026"""
    day = random.randint(1, 31)
    return f"2026-03-{day:02d}"

def generate_amount(min_val=1000, max_val=500000):
    """Generate a random amount"""
    return round(random.uniform(min_val, max_val), 2)

def get_pl_section_for_account(account_code):
    """Get P&L section for an account code"""
    for section, accounts in PL_SECTIONS.items():
        if account_code in accounts:
            return section
    return 'Other operating expenses'

# ============================================================================
# IBM BOB 1: Group P&L Line Items Generator
# ============================================================================
def generate_pl_line_items(start_txn=4209, start_invoice=1, count=1000):
    """Generate P&L line items"""
    records = []
    
    for i in range(count):
        txn_id = f"TXN{start_txn + i:06d}"
        entity = random.choice(ENTITIES)
        posting_date = generate_march_date()
        
        # Select account and get details
        section = random.choice(list(PL_SECTIONS.keys()))
        account_code = random.choice(PL_SECTIONS[section])
        line_item, category = PL_LINE_ITEMS.get(account_code, ('Other', 'Other'))
        
        cost_center = random.choice(COST_CENTERS)
        vendor = random.choice(VENDORS)
        invoice_num = f"BOB-PL-{start_invoice + i:04d}"
        po_number = f"PO-PL-{random.randint(1000, 9999)}"
        
        # Amount logic: Revenue is positive, expenses are positive (will be shown as expenses)
        if account_code.startswith('4'):
            amount = generate_amount(50000, 500000)
        elif account_code.startswith('6'):
            amount = generate_amount(20000, 150000)
        else:
            amount = generate_amount(3000, 200000)
        
        record = {
            'Demo_Task': 'IBM BOB 1 - Group P&L',
            'Fiscal_Period': '2026-03',
            'Txn_ID': txn_id,
            'Entity': entity,
            'Posting_Date': posting_date,
            'Account_Code': account_code,
            'P_L_Section': section,
            'P_L_Line_Item': line_item,
            'Category': category,
            'Cost_Center': cost_center,
            'Cost_Center_Name': COST_CENTER_NAMES[cost_center],
            'Vendor_or_Customer': vendor,
            'Invoice_Number': invoice_num,
            'PO_Number': po_number,
            'Amount_AUD': amount,
            'Input_or_Calculated': 'Input',
            'Close_Readiness_Flag': random.choice(['Ready', 'Ready', 'Ready', 'Pending review']),
            'Anomaly_Flag': random.choice(['None', 'None', 'None', 'High variance']),
            'Approval_Required': random.choice(['No', 'No', 'No', 'Yes']),
            'Source_File_Target': 'Raw_GL_Export_With_CostCenters_Mar2026_IBMBOB_Enhanced.csv'
        }
        records.append(record)
    
    return records

# ============================================================================
# IBM BOB 2: Workforce Cost & Output Generator
# ============================================================================
def generate_workforce_records(start_txn=5209, count=1000):
    """Generate workforce cost and output records"""
    records = []
    
    for i in range(count):
        emp_id = f"EMP{random.randint(1000, 9999)}"
        business_unit = random.choice(BUSINESS_UNITS)
        department = business_unit
        role = random.choice(ROLES)
        entity = random.choice(ENTITIES)
        cost_center = random.choice(COST_CENTERS)
        
        # Generate costs
        salary = generate_amount(5000, 20000)
        overtime = generate_amount(0, 2500) if random.random() > 0.3 else 0
        benefits = generate_amount(500, 3000)
        contractor = generate_amount(0, 15000) if random.random() > 0.6 else 0
        total_cost = salary + overtime + benefits + contractor
        
        # Generate output metrics
        hours = round(random.uniform(120, 185), 1)
        utilisation = round(random.uniform(55, 98), 1)
        output_metric = OUTPUT_METRICS.get(business_unit, 'tasks_completed')
        output_volume = random.randint(40, 300)
        revenue_supported = generate_amount(10000, 800000)
        labour_cost_per_output = round(total_cost / output_volume, 2)
        
        performance = random.choice(PERFORMANCE_RATINGS)
        risk_flag = random.choice(RISK_FLAGS)
        
        if risk_flag:
            action = 'Review allocation / approve exception'
        else:
            action = 'No action'
        
        txn_id = f"TXN{start_txn + i:06d}"
        
        record = {
            'Demo_Task': 'IBM BOB 2 - Workforce',
            'Fiscal_Period': '2026-03',
            'Employee_ID': emp_id,
            'Business_Unit': business_unit,
            'Department': department,
            'Role': role,
            'Entity': entity,
            'Cost_Center': cost_center,
            'Cost_Center_Name': COST_CENTER_NAMES[cost_center],
            'Salary_AUD': round(salary, 2),
            'Overtime_AUD': round(overtime, 2),
            'Benefits_AUD': round(benefits, 2),
            'Contractor_Cost_AUD': round(contractor, 2),
            'Total_Workforce_Cost_AUD': round(total_cost, 2),
            'Hours_Worked': hours,
            'Utilisation_Percent': utilisation,
            'Output_Metric': output_metric,
            'Output_Volume': output_volume,
            'Revenue_or_Value_Supported_AUD': round(revenue_supported, 2),
            'Labour_Cost_Per_Output': labour_cost_per_output,
            'Performance_Rating': performance,
            'Risk_Flag': risk_flag if risk_flag else 'None',
            'Recommended_Action': action,
            'Linked_GL_Txn_ID': txn_id,
            'Source_File_Target': 'IBMBOB_Workforce_Cost_Output_Mar2026.csv + Raw_GL_Export_With_CostCenters_Mar2026_IBMBOB_Enhanced.csv'
        }
        records.append(record)
    
    return records

# ============================================================================
# IBM BOB 3: ESG Cost & KPI Generator
# ============================================================================
def generate_esg_records(start_txn=6209, start_esg=1, count=1000):
    """Generate ESG cost and KPI records"""
    records = []
    
    for i in range(count):
        esg_id = f"ESG-MAR26-{start_esg + i:04d}"
        txn_id = f"TXN{start_txn + i:06d}"
        entity = random.choice(ENTITIES)
        cost_center = random.choice(COST_CENTERS)
        
        category = random.choice(ESG_CATEGORIES)
        account_code, account_name = ESG_ACCOUNTS[category]
        supplier = random.choice(ESG_SUPPLIERS)
        invoice_num = f"BOB-ESG-{start_esg + i:04d}"
        po_number = f"PO-ESG-{random.randint(1000, 9999)}"
        spend = generate_amount(3000, 120000)
        
        # KPI metrics
        kpi = random.choice(ESG_KPIS)
        kpi_target = round(random.uniform(50, 1000), 2)
        kpi_actual = round(kpi_target * random.uniform(0.65, 1.25), 2)
        kpi_attainment = round((kpi_actual / kpi_target) * 100, 1)
        
        # Environmental metrics
        carbon = round(random.uniform(20, 550), 2)
        renewable = round(random.uniform(1, 99), 1)
        supplier_score = random.randint(45, 99)
        
        # Financial impact
        wc_impact = round(random.uniform(-50000, 85000), 2)
        margin_impact = round(random.uniform(-0.8, 0.4), 2)
        
        # Flags and status
        misclassification = random.choice(['Yes', 'No', 'No', 'No'])
        leakage = 'ESG spend posted to non-ESG account or missing KPI link' if misclassification == 'Yes' else 'None'
        disclosure = random.choice(DISCLOSURE_STATUS)
        audit = random.choice(AUDIT_READINESS)
        
        # Approval logic
        if spend > 100000 or audit == 'Needs review':
            action = 'CFO approval for material ESG spend'
            approval = 'Yes'
        elif misclassification == 'Yes':
            action = 'Reclassify and link to KPI evidence'
            approval = 'Yes'
        else:
            action = 'No action'
            approval = 'No'
        
        record = {
            'Demo_Task': 'IBM BOB 3 - ESG',
            'Fiscal_Period': '2026-03',
            'ESG_Record_ID': esg_id,
            'Linked_GL_Txn_ID': txn_id,
            'Entity': entity,
            'Cost_Center': cost_center,
            'Cost_Center_Name': COST_CENTER_NAMES[cost_center],
            'ESG_Category': category,
            'Account_Code': account_code,
            'Account_Name': account_name,
            'Supplier': supplier,
            'Invoice_Number': invoice_num,
            'PO_Number': po_number,
            'Spend_AUD': round(spend, 2),
            'Sustainability_KPI': kpi,
            'KPI_Target': kpi_target,
            'KPI_Actual': kpi_actual,
            'KPI_Attainment_Percent': kpi_attainment,
            'Carbon_tCO2e': carbon,
            'Renewable_Source_Percent': renewable,
            'Supplier_ESG_Score': supplier_score,
            'Working_Capital_Impact_AUD': wc_impact,
            'Margin_Impact_Points': margin_impact,
            'Misclassification_Flag': misclassification,
            'Leakage_Flag': leakage,
            'Disclosure_Evidence_Status': disclosure,
            'Audit_Readiness': audit,
            'Recommended_Action': action,
            'Approval_Required': approval,
            'Source_File_Target': 'IBMBOB_ESG_Cost_KPI_Mar2026.csv + Raw_GL_Export_With_CostCenters_Mar2026_IBMBOB_Enhanced.csv'
        }
        records.append(record)
    
    return records

# ============================================================================
# Enhanced GL Generator
# ============================================================================
def generate_enhanced_gl_records(pl_records, workforce_records, esg_records):
    """Generate enhanced GL records from all three datasets"""
    gl_records = []
    
    # From P&L records
    for pl in pl_records:
        posting_date = pl['Posting_Date']
        invoice_date = (datetime.strptime(posting_date, '%Y-%m-%d') - timedelta(days=random.randint(1, 10))).strftime('%Y-%m-%d')
        
        record = {
            'Txn_ID': pl['Txn_ID'],
            'Posting_Date_Raw': posting_date,
            'Invoice_Date_Raw': invoice_date,
            'Fiscal_Period': pl['Fiscal_Period'],
            'Entity': pl['Entity'],
            'Account_Code_Raw': pl['Account_Code'],
            'Cost_Center_Raw': '',
            'Cost_Center': pl['Cost_Center'],
            'Vendor_Name_Raw': pl['Vendor_or_Customer'],
            'Invoice_Number': pl['Invoice_Number'],
            'PO_Number': pl['PO_Number'],
            'Currency': random.choice(CURRENCIES),
            'Amount': pl['Amount_AUD'],
            'Tax_Code': random.choice(TAX_CODES),
            'Narrative': f"P&L transaction - {pl['P_L_Line_Item']}",
            'Source_System': random.choice(SOURCE_SYSTEMS)
        }
        gl_records.append(record)
    
    # From Workforce records (salary postings)
    for wf in workforce_records:
        posting_date = generate_march_date()
        invoice_date = posting_date
        
        record = {
            'Txn_ID': wf['Linked_GL_Txn_ID'],
            'Posting_Date_Raw': posting_date,
            'Invoice_Date_Raw': invoice_date,
            'Fiscal_Period': wf['Fiscal_Period'],
            'Entity': wf['Entity'],
            'Account_Code_Raw': '5000',  # Salaries and wages
            'Cost_Center_Raw': '',
            'Cost_Center': wf['Cost_Center'],
            'Vendor_Name_Raw': f"Payroll - {wf['Employee_ID']}",
            'Invoice_Number': f"PAY-{wf['Employee_ID']}-MAR26",
            'PO_Number': '',
            'Currency': 'AUD',
            'Amount': wf['Total_Workforce_Cost_AUD'],
            'Tax_Code': 'GST-FREE',
            'Narrative': f"Workforce cost - {wf['Role']} - {wf['Department']}",
            'Source_System': 'Workday'
        }
        gl_records.append(record)
    
    # From ESG records
    for esg in esg_records:
        posting_date = generate_march_date()
        invoice_date = (datetime.strptime(posting_date, '%Y-%m-%d') - timedelta(days=random.randint(1, 7))).strftime('%Y-%m-%d')
        
        record = {
            'Txn_ID': esg['Linked_GL_Txn_ID'],
            'Posting_Date_Raw': posting_date,
            'Invoice_Date_Raw': invoice_date,
            'Fiscal_Period': esg['Fiscal_Period'],
            'Entity': esg['Entity'],
            'Account_Code_Raw': esg['Account_Code'],
            'Cost_Center_Raw': '',
            'Cost_Center': esg['Cost_Center'],
            'Vendor_Name_Raw': esg['Supplier'],
            'Invoice_Number': esg['Invoice_Number'],
            'PO_Number': esg['PO_Number'],
            'Currency': random.choice(CURRENCIES),
            'Amount': esg['Spend_AUD'],
            'Tax_Code': random.choice(TAX_CODES),
            'Narrative': f"ESG spend - {esg['ESG_Category']}",
            'Source_System': random.choice(SOURCE_SYSTEMS)
        }
        gl_records.append(record)
    
    return gl_records

# ============================================================================
# Main Execution
# ============================================================================
def main():
    print("IBM Bob Demo Dataset Generator")
    print("=" * 60)
    
    # Generate datasets
    print("\n1. Generating IBM BOB 1 - Group P&L Line Items (1,000 records)...")
    pl_records = generate_pl_line_items(count=1000)
    
    print("2. Generating IBM BOB 2 - Workforce Cost & Output (1,000 records)...")
    workforce_records = generate_workforce_records(count=1000)
    
    print("3. Generating IBM BOB 3 - ESG Cost & KPI (1,000 records)...")
    esg_records = generate_esg_records(count=1000)
    
    print("4. Generating Enhanced GL records (3,000 records)...")
    gl_records = generate_enhanced_gl_records(pl_records, workforce_records, esg_records)
    
    # Write P&L records
    print("\n5. Writing IBM BOB 1 dataset...")
    with open('IBMBOB_Demo_Assets_Mar2026/IBMBOB_Group_PL_LineItems_Mar2026_GENERATED.csv', 'w', newline='', encoding='utf-8') as f:
        if pl_records:
            writer = csv.DictWriter(f, fieldnames=pl_records[0].keys())
            writer.writeheader()
            writer.writerows(pl_records)
    
    # Write Workforce records
    print("6. Writing IBM BOB 2 dataset...")
    with open('IBMBOB_Demo_Assets_Mar2026/IBMBOB_Workforce_Cost_Output_Mar2026_GENERATED.csv', 'w', newline='', encoding='utf-8') as f:
        if workforce_records:
            writer = csv.DictWriter(f, fieldnames=workforce_records[0].keys())
            writer.writeheader()
            writer.writerows(workforce_records)
    
    # Write ESG records
    print("7. Writing IBM BOB 3 dataset...")
    with open('IBMBOB_Demo_Assets_Mar2026/IBMBOB_ESG_Cost_KPI_Mar2026_GENERATED.csv', 'w', newline='', encoding='utf-8') as f:
        if esg_records:
            writer = csv.DictWriter(f, fieldnames=esg_records[0].keys())
            writer.writeheader()
            writer.writerows(esg_records)
    
    # Write Enhanced GL records
    print("8. Writing Enhanced GL dataset...")
    with open('IBMBOB_Demo_Assets_Mar2026/Raw_GL_Export_With_CostCenters_Mar2026_IBMBOB_Enhanced_GENERATED.csv', 'w', newline='', encoding='utf-8') as f:
        if gl_records:
            writer = csv.DictWriter(f, fieldnames=gl_records[0].keys())
            writer.writeheader()
            writer.writerows(gl_records)
    
    print("\n" + "=" * 60)
    print("✓ Dataset generation complete!")
    print(f"  - P&L Line Items: {len(pl_records)} records")
    print(f"  - Workforce Records: {len(workforce_records)} records")
    print(f"  - ESG Records: {len(esg_records)} records")
    print(f"  - Enhanced GL Records: {len(gl_records)} records")
    print("\nFiles created in IBMBOB_Demo_Assets_Mar2026/ directory")
    print("=" * 60)

if __name__ == "__main__":
    main()

# Made with Bob
