# IBM Bob Demo Datasets - Complete Documentation

**Generated:** April 29, 2026  
**Period:** March 2026 (2026-03)  
**Total Records:** 5,000 (1,000 each for 3 datasets + 3,000 GL records)

---

## Table of Contents

1. [Overview](#overview)
2. [Dataset Specifications](#dataset-specifications)
3. [IBM BOB 1 - Group P&L](#ibm-bob-1---group-pl)
4. [IBM BOB 2 - Workforce](#ibm-bob-2---workforce)
5. [IBM BOB 3 - ESG](#ibm-bob-3---esg)
6. [Enhanced GL Export](#enhanced-gl-export)
7. [Demo Prompts](#demo-prompts)
8. [Data Quality & Validation](#data-quality--validation)
9. [Import Instructions](#import-instructions)

---

## Overview

This dataset collection supports three IBM Bob demonstration scenarios focused on CFO-level financial analysis, workforce optimization, and ESG performance tracking. All data is for **March 2026 month-end close** and is designed to showcase AI-powered financial intelligence capabilities.

### Key Features

- **Realistic Financial Data**: Transaction amounts, dates, and patterns mirror real-world month-end close scenarios
- **Cross-Dataset Linkage**: All records link back to the Enhanced GL for full traceability
- **Approval Workflows**: Built-in flags for items requiring CFO/controller approval
- **Risk Indicators**: Automated flagging of anomalies, variances, and compliance issues
- **Audit-Ready**: Complete audit trails with source systems, invoice numbers, and PO references

---

## Dataset Specifications

| Dataset | File Name | Records | Purpose |
|---------|-----------|---------|---------|
| **IBM BOB 1** | `IBMBOB_Group_PL_LineItems_Mar2026_GENERATED.csv` | 1,000 | P&L statement line items for CFO reporting |
| **IBM BOB 2** | `IBMBOB_Workforce_Cost_Output_Mar2026_GENERATED.csv` | 1,000 | Workforce cost analysis and productivity metrics |
| **IBM BOB 3** | `IBMBOB_ESG_Cost_KPI_Mar2026_GENERATED.csv` | 1,000 | ESG spend tracking and sustainability KPIs |
| **Enhanced GL** | `Raw_GL_Export_With_CostCenters_Mar2026_IBMBOB_Enhanced_GENERATED.csv` | 3,000 | Complete GL postings linking all datasets |

### Reference Data

- **Entities**: AUS01, NZL01, PNG01, FJI01
- **Cost Centers**: 15 centers across NSW, VIC, QLD, WA, SA, TAS, NT, ACT, CORP, IT, FIN, HR, MKT, OPS, R&D
- **Currencies**: AUD, NZD, USD, GBP
- **Fiscal Period**: 2026-03 (March 2026)

---

## IBM BOB 1 - Group P&L

### Purpose
Create CFO-ready Profit & Loss statements with variance analysis, approval workflows, and close-readiness tracking.

### File Structure

**File:** `IBMBOB_Group_PL_LineItems_Mar2026_GENERATED.csv`  
**Records:** 1,000 line items  
**Columns:** 20 fields

#### Key Fields

| Field | Description | Sample Values |
|-------|-------------|---------------|
| `Txn_ID` | Unique transaction identifier | TXN004209 - TXN005208 |
| `Account_Code` | GL account code | 4000 (Revenue), 5000 (Expenses), 6000 (COGS) |
| `P_L_Section` | P&L statement section | Revenue, Cost of revenue, Operating expenses |
| `P_L_Line_Item` | Specific line item description | Product sales, Salaries and wages, Software licenses |
| `Category` | Transaction category | Operating Revenue, Personnel, COGS, IT, Sales |
| `Amount_AUD` | Transaction amount in AUD | 3,000 - 500,000 |
| `Close_Readiness_Flag` | Month-end close status | Ready, Pending review |
| `Anomaly_Flag` | Variance or anomaly indicator | None, High variance |
| `Approval_Required` | Requires CFO approval | Yes, No |

#### P&L Sections Covered

1. **Revenue** (Accounts 4000-4020)
   - Product sales
   - Service revenue
   - Subscription revenue

2. **Cost of Revenue** (Accounts 6000-6030)
   - Cost of goods sold
   - Direct materials
   - Direct labor
   - Manufacturing overhead

3. **Operating Expenses**
   - General and administrative (5000-5320)
   - Sales and marketing (5500-5520)
   - Research and development (5200-5700)
   - Other operating expenses (5100-5120)

4. **Other Income/Expense** (4100, 5910, 5920)
   - Interest income
   - Interest expense
   - FX gains/losses

5. **Tax Provision** (2210)
   - Income tax payable

### Demo Prompts

**Primary Prompt:**
```
Create a CFO-ready Profit & Loss statement using March 2026 month-end data only. 
Structure columns for March Actuals, MTD, YTD if available, and variance vs plan 
where available. Include Revenue, Cost of Revenue, Gross Profit, Operating Expenses, 
Income from Operations, Other Income/Expense, Income Before Tax, Tax Provision and 
Net Income. Use only source data, reconcile totals back to the enhanced GL, flag 
unusual variances and show items requiring approval before close.
```

**Expected Outputs:**
- Structured P&L with standard sections
- Variance analysis highlighting anomalies
- List of items requiring approval
- Reconciliation to GL totals
- Close-readiness assessment

---

## IBM BOB 2 - Workforce

### Purpose
Analyze workforce costs, productivity, and resource allocation to identify optimization opportunities and compliance risks.

### File Structure

**File:** `IBMBOB_Workforce_Cost_Output_Mar2026_GENERATED.csv`  
**Records:** 1,000 employee/contractor records  
**Columns:** 25 fields

#### Key Fields

| Field | Description | Sample Values |
|-------|-------------|---------------|
| `Employee_ID` | Unique employee identifier | EMP1000 - EMP9999 |
| `Business_Unit` | Department/function | Finance, IT, Sales, Operations, Commercial, FP&A |
| `Role` | Job title | Finance Analyst, Data Engineer, Sales Manager |
| `Salary_AUD` | Base salary for March | 5,000 - 20,000 |
| `Overtime_AUD` | Overtime pay | 0 - 2,500 |
| `Benefits_AUD` | Employee benefits | 500 - 3,000 |
| `Contractor_Cost_AUD` | External contractor costs | 0 - 15,000 |
| `Total_Workforce_Cost_AUD` | Total cost | Sum of above |
| `Hours_Worked` | Hours in March | 120 - 185 |
| `Utilisation_Percent` | Productivity utilization | 55% - 98% |
| `Output_Volume` | Units of work completed | 40 - 300 |
| `Revenue_or_Value_Supported_AUD` | Business value generated | 10,000 - 800,000 |
| `Labour_Cost_Per_Output` | Efficiency metric | Calculated |
| `Risk_Flag` | Compliance/efficiency risk | High overtime, Low utilisation high cost, Contractor dependency |
| `Recommended_Action` | AI recommendation | Review allocation / approve exception, No action |

#### Output Metrics by Business Unit

| Business Unit | Output Metric | Description |
|---------------|---------------|-------------|
| Finance | close_tasks | Month-end close tasks completed |
| IT | tickets_resolved | Support tickets resolved |
| Sales | deals_supported | Sales opportunities supported |
| Operations | flights_supported | Operational activities completed |
| Commercial | revenue_cases | Revenue recognition cases |
| FP&A | forecast_models | Financial models created |
| Procurement | pos_processed | Purchase orders processed |
| Customer Care | cases_resolved | Customer cases resolved |

### Demo Prompts

**Prompt 1: Cost-Revenue Correlation**
```
Using March financial and workforce data, correlate workforce cost with revenue 
or output by business unit and identify areas where labour cost is not aligned 
with business performance.
```

**Prompt 2: Salary Cost Analysis**
```
Using March workforce data, analyse salary costs by department, identify unusual 
changes, duplicate or high-overtime patterns, and highlight financial or compliance risks.
```

**Prompt 3: Cost-Output Efficiency**
```
From March month-end data, identify areas where workforce cost is increasing 
without a corresponding improvement in output or utilisation.
```

**Prompt 4: Resource Optimization**
```
Analyse workforce costs across departments and recommend resource allocation 
changes to improve utilisation and margin.
```

---

## IBM BOB 3 - ESG

### Purpose
Track ESG-related spending, measure sustainability KPIs, assess disclosure readiness, and quantify financial impact of ESG initiatives.

### File Structure

**File:** `IBMBOB_ESG_Cost_KPI_Mar2026_GENERATED.csv`  
**Records:** 1,000 ESG transactions  
**Columns:** 30 fields

#### Key Fields

| Field | Description | Sample Values |
|-------|-------------|---------------|
| `ESG_Record_ID` | Unique ESG record identifier | ESG-MAR26-0001 - ESG-MAR26-1000 |
| `ESG_Category` | Type of ESG spend | Energy usage, Carbon offsets, Renewable sourcing |
| `Spend_AUD` | ESG-related expenditure | 3,000 - 120,000 |
| `Sustainability_KPI` | KPI being tracked | tCO2e avoided, renewable_kwh, waste_kg_reduced |
| `KPI_Target` | Target value | Varies by KPI |
| `KPI_Actual` | Actual achievement | Varies by KPI |
| `KPI_Attainment_Percent` | Performance vs target | 65% - 125% |
| `Carbon_tCO2e` | Carbon emissions (tonnes CO2e) | 20 - 550 |
| `Renewable_Source_Percent` | % from renewable sources | 1% - 99% |
| `Supplier_ESG_Score` | Supplier sustainability rating | 45 - 99 |
| `Working_Capital_Impact_AUD` | Impact on working capital | -50,000 to +85,000 |
| `Margin_Impact_Points` | Impact on profit margin (bps) | -0.8 to +0.4 |
| `Misclassification_Flag` | Incorrect GL coding | Yes, No |
| `Leakage_Flag` | ESG spend not tracked | Description or None |
| `Disclosure_Evidence_Status` | Documentation completeness | Complete, Partial, Missing |
| `Audit_Readiness` | Ready for audit | Ready, Needs review, Partial |
| `Approval_Required` | Requires CFO approval | Yes, No |

#### ESG Categories

1. **Energy Usage** (Account 5110 - Utilities)
   - Electricity, gas, renewable energy purchases

2. **Renewable Sourcing Premium** (Account 6000 - COGS)
   - Premium paid for renewable/sustainable materials

3. **Carbon Offsets** (Account 5300 - Professional Services)
   - Carbon credit purchases, offset programs

4. **Fleet Emissions** (Account 5400 - Travel)
   - Vehicle emissions, green fleet initiatives

5. **Waste Reduction** (Account 5600 - Telecommunications)
   - Waste management, recycling programs

6. **Sustainable Packaging** (Account 6010 - Direct Materials)
   - Eco-friendly packaging materials

7. **Supplier ESG Premium** (Account 6010 - Direct Materials)
   - Premium for ESG-certified suppliers

8. **Compliance Assurance** (Account 5320 - Audit Fees)
   - ESG audits, certifications, compliance

### Demo Prompts

**Prompt 1: ESG Cost Leakage Detection**
```
From March financials, identify cost centres contributing to sustainability-related 
spend, detect ESG cost leakage or misclassification, quantify financial impact and 
recommend corrections.
```

**Prompt 2: Financial Impact Analysis**
```
Analyse March close data to determine how ESG activities have impacted working 
capital, margins and cash flow. Provide a CFO-level view of sustainability 
investment trade-offs.
```

**Prompt 3: Disclosure Readiness Assessment**
```
Based on March close outputs, assess ESG disclosure readiness. Validate completeness, 
traceability and auditability across finance, operations and supplier data.
```

**Prompt 4: Scenario Modeling**
```
Using March close as baseline, simulate a 10-15% increase in sustainability targets 
and model impact on cost structure, margins, supplier mix and compliance risk.
```

**Prompt 5: Board-Ready Narrative**
```
Generate a board-ready ESG performance narrative for March linking sustainability 
outcomes to financial performance, risk exposure and strategic priorities.
```

---

## Enhanced GL Export

### Purpose
Consolidated General Ledger export containing all transactions from the three IBM Bob datasets, providing complete audit trail and reconciliation capability.

### File Structure

**File:** `Raw_GL_Export_With_CostCenters_Mar2026_IBMBOB_Enhanced_GENERATED.csv`  
**Records:** 3,000 GL postings  
**Columns:** 16 fields

#### Record Composition

- **1,000 records** from P&L line items (TXN004209 - TXN005208)
- **1,000 records** from Workforce payroll postings (TXN005209 - TXN006208)
- **1,000 records** from ESG transactions (TXN006209 - TXN007208)

#### Key Fields

| Field | Description | Sample Values |
|-------|-------------|---------------|
| `Txn_ID` | Unique transaction ID | TXN004209 - TXN007208 |
| `Posting_Date_Raw` | GL posting date | 2026-03-01 to 2026-03-31 |
| `Invoice_Date_Raw` | Invoice/document date | Typically 1-10 days before posting |
| `Fiscal_Period` | Accounting period | 2026-03 |
| `Entity` | Legal entity | AUS01, NZL01, PNG01, FJI01 |
| `Account_Code_Raw` | GL account code | 4000-6030 |
| `Cost_Center` | Cost center code | NSW, VIC, QLD, etc. |
| `Vendor_Name_Raw` | Vendor/supplier name | Various vendors |
| `Invoice_Number` | Invoice reference | BOB-PL-xxxx, BOB-ESG-xxxx, PAY-EMPxxxx |
| `PO_Number` | Purchase order number | PO-PL-xxxx, PO-ESG-xxxx |
| `Currency` | Transaction currency | AUD, NZD, USD, GBP |
| `Amount` | Transaction amount | Varies by transaction type |
| `Tax_Code` | Tax treatment | GST, GST-FREE, INPUT, EXPORT |
| `Narrative` | Transaction description | Descriptive text |
| `Source_System` | Originating system | Manual Entry, API Import, SAP, Oracle, Workday |

#### Transaction Types

1. **P&L Transactions** (TXN004209-005208)
   - Revenue, expenses, COGS postings
   - Narrative: "P&L transaction - [line item]"

2. **Workforce Transactions** (TXN005209-006208)
   - Salary, overtime, benefits, contractor costs
   - Account: 5000 (Salaries and wages)
   - Narrative: "Workforce cost - [role] - [department]"
   - Vendor: "Payroll - [Employee_ID]"

3. **ESG Transactions** (TXN006209-007208)
   - Sustainability-related expenditures
   - Various accounts based on ESG category
   - Narrative: "ESG spend - [category]"

---

## Demo Prompts

### IBM BOB 1 - Group P&L Demo Prompt

**Scenario:** CFO Month-End Close Review

**Prompt:**
```
Create a CFO-ready Profit & Loss statement using March 2026 month-end data only. 
Structure columns for March Actuals, MTD, YTD if available, and variance vs plan 
where available. Include Revenue, Cost of Revenue, Gross Profit, Operating Expenses, 
Income from Operations, Other Income/Expense, Income Before Tax, Tax Provision and 
Net Income. Use only source data, reconcile totals back to the enhanced GL, flag 
unusual variances and show items requiring approval before close.
```

**Expected Analysis:**
- Structured P&L with standard financial statement format
- Revenue breakdown by type (Product, Service, Subscription)
- COGS and gross margin analysis
- Operating expense categorization
- Identification of high-variance items
- List of transactions requiring approval
- GL reconciliation confirmation
- Close-readiness assessment

---

### IBM BOB 2 - Workforce Demo Prompts

#### Prompt 1: Cost-Revenue Alignment
```
Using March financial and workforce data, correlate workforce cost with revenue 
or output by business unit and identify areas where labour cost is not aligned 
with business performance.
```

**Expected Analysis:**
- Cost per output by business unit
- Revenue/value supported vs. workforce cost
- Identification of high-cost, low-output areas
- Benchmarking across departments
- Recommendations for reallocation

#### Prompt 2: Salary Cost Anomalies
```
Using March workforce data, analyse salary costs by department, identify unusual 
changes, duplicate or high-overtime patterns, and highlight financial or compliance risks.
```

**Expected Analysis:**
- Department-level salary analysis
- Overtime pattern identification
- Contractor dependency assessment
- Compliance risk flagging
- Cost anomaly detection

#### Prompt 3: Cost-Output Efficiency
```
From March month-end data, identify areas where workforce cost is increasing 
without a corresponding improvement in output or utilisation.
```

**Expected Analysis:**
- Trend analysis of cost vs. output
- Utilization rate assessment
- Productivity metrics by role
- Inefficiency identification
- Cost optimization opportunities

#### Prompt 4: Resource Optimization
```
Analyse workforce costs across departments and recommend resource allocation 
changes to improve utilisation and margin.
```

**Expected Analysis:**
- Cross-department comparison
- Utilization gap analysis
- Margin impact calculation
- Reallocation recommendations
- Expected ROI from changes

---

### IBM BOB 3 - ESG Demo Prompts

#### Prompt 1: ESG Cost Leakage
```
From March financials, identify cost centres contributing to sustainability-related 
spend, detect ESG cost leakage or misclassification, quantify financial impact and 
recommend corrections.
```

**Expected Analysis:**
- ESG spend by cost center
- Misclassification detection
- Leakage quantification
- Reclassification recommendations
- Financial impact assessment

#### Prompt 2: Financial Impact
```
Analyse March close data to determine how ESG activities have impacted working 
capital, margins and cash flow. Provide a CFO-level view of sustainability 
investment trade-offs.
```

**Expected Analysis:**
- Working capital impact summary
- Margin impact by ESG category
- Cash flow implications
- ROI on ESG investments
- Trade-off analysis

#### Prompt 3: Disclosure Readiness
```
Based on March close outputs, assess ESG disclosure readiness. Validate completeness, 
traceability and auditability across finance, operations and supplier data.
```

**Expected Analysis:**
- Disclosure completeness score
- Evidence gap identification
- Audit readiness assessment
- Supplier data validation
- Remediation priorities

#### Prompt 4: Scenario Modeling
```
Using March close as baseline, simulate a 10-15% increase in sustainability targets 
and model impact on cost structure, margins, supplier mix and compliance risk.
```

**Expected Analysis:**
- Cost impact projection
- Margin sensitivity analysis
- Supplier mix changes
- Compliance risk assessment
- Implementation roadmap

#### Prompt 5: Board Narrative
```
Generate a board-ready ESG performance narrative for March linking sustainability 
outcomes to financial performance, risk exposure and strategic priorities.
```

**Expected Analysis:**
- Executive summary of ESG performance
- KPI achievement vs. targets
- Financial performance linkage
- Risk and opportunity assessment
- Strategic recommendations

---

## Data Quality & Validation

### Validation Checks Performed

✅ **Record Counts**
- IBM BOB 1: 1,000 P&L line items
- IBM BOB 2: 1,000 workforce records
- IBM BOB 3: 1,000 ESG records
- Enhanced GL: 3,000 transactions

✅ **Data Integrity**
- All transactions dated within March 2026
- Transaction IDs are sequential and unique
- All amounts are positive and realistic
- All required fields populated

✅ **Referential Integrity**
- All cost centers exist in master data
- All account codes valid per COA
- All entities are valid
- GL transactions link to source datasets

✅ **Business Logic**
- Revenue accounts have appropriate amounts (50K-500K)
- Expense accounts have realistic ranges
- Workforce costs align with market rates
- ESG KPIs have realistic targets and actuals

### Data Quality Metrics

| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| Completeness | 100% | 100% | ✅ |
| Accuracy | >95% | 100% | ✅ |
| Consistency | 100% | 100% | ✅ |
| Timeliness | March 2026 | March 2026 | ✅ |
| Validity | 100% | 100% | ✅ |

---

## Import Instructions

### For watsonx Orchestrate

#### Step 1: Prepare Import Mapping

Use the provided mapping file: `IBMBOB_Watsonx_Import_Mapping.csv`

#### Step 2: Import Sequence

1. **Import Enhanced GL First**
   - File: `Raw_GL_Export_With_CostCenters_Mar2026_IBMBOB_Enhanced_GENERATED.csv`
   - Table: `raw_gl_export_with_costcenters_mar2026`
   - Records: 3,000

2. **Import P&L Line Items**
   - File: `IBMBOB_Group_PL_LineItems_Mar2026_GENERATED.csv`
   - Table: `group_pl_line_items_mar2026`
   - Records: 1,000

3. **Import Workforce Data**
   - File: `IBMBOB_Workforce_Cost_Output_Mar2026_GENERATED.csv`
   - Table: `workforce_cost_output_mar2026`
   - Records: 1,000

4. **Import ESG Data**
   - File: `IBMBOB_ESG_Cost_KPI_Mar2026_GENERATED.csv`
   - Table: `esg_cost_kpi_mar2026`
   - Records: 1,000

#### Step 3: Verify Import

Run validation queries:

```sql
-- Verify record counts
SELECT 'GL' as dataset, COUNT(*) as records FROM raw_gl_export_with_costcenters_mar2026
UNION ALL
SELECT 'P&L', COUNT(*) FROM group_pl_line_items_mar2026
UNION ALL
SELECT 'Workforce', COUNT(*) FROM workforce_cost_output_mar2026
UNION ALL
SELECT 'ESG', COUNT(*) FROM esg_cost_kpi_mar2026;

-- Verify transaction linkage
SELECT COUNT(DISTINCT txn_id) as unique_transactions 
FROM raw_gl_export_with_costcenters_mar2026;
```

### For Other Systems

#### CSV Import
- All files are standard CSV format with headers
- UTF-8 encoding
- Comma-separated values
- Quoted strings where necessary

#### Database Import
- Create tables matching column structure
- Use appropriate data types (VARCHAR, DECIMAL, DATE)
- Set primary keys on ID fields
- Create indexes on frequently queried fields

---

## Technical Specifications

### File Formats
- **Format:** CSV (Comma-Separated Values)
- **Encoding:** UTF-8
- **Line Endings:** Unix (LF)
- **Header Row:** Yes (first row)
- **Delimiter:** Comma (,)
- **Text Qualifier:** Double quotes (") where needed

### Data Types

| Field Type | Format | Example |
|------------|--------|---------|
| Transaction ID | TXNnnnnnn | TXN004209 |
| Employee ID | EMPnnnn | EMP8171 |
| ESG Record ID | ESG-MAR26-nnnn | ESG-MAR26-0001 |
| Date | YYYY-MM-DD | 2026-03-15 |
| Amount | Decimal(12,2) | 127291.16 |
| Percentage | Decimal(5,1) | 85.4 |
| Text | VARCHAR | Various |

### File Sizes
- P&L Dataset: ~250 KB
- Workforce Dataset: ~350 KB
- ESG Dataset: ~400 KB
- Enhanced GL: ~750 KB
- **Total:** ~1.75 MB

---

## Support & Maintenance

### Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-04-29 | Initial dataset generation |

### Contact Information

For questions or issues with these datasets, please contact:
- **Dataset Owner:** IBM Bob Demo Team
- **Technical Support:** AI/ML Engineering Team

### Known Limitations

1. **Historical Data:** Only March 2026 data included
2. **Comparative Analysis:** No prior period data for YoY comparison
3. **Budget Data:** Budget/plan data not included in this release
4. **Multi-Currency:** Amounts in source currency, no consolidated AUD view

### Future Enhancements

- [ ] Add February 2026 comparative data
- [ ] Include budget/plan data for variance analysis
- [ ] Add YTD cumulative figures
- [ ] Include multi-currency consolidation
- [ ] Add more granular cost center breakdowns

---

## Appendix

### A. Account Code Reference

See `financeV2-main/Master_COA_Complete.csv` for complete Chart of Accounts

### B. Cost Center Reference

See `financeV2-main/Master_CostCenters_States.csv` for cost center details

### C. Vendor List

Common vendors in datasets:
- IBM Australia
- Google Ads
- QBE Insurance
- Energy Australia
- Melbourne Airport
- Deloitte
- LinkedIn
- SAP Australia
- Qantas Commercial
- Officeworks
- AWS
- Snowflake
- Microsoft
- Oracle
- Salesforce

### D. ESG Supplier List

ESG-specific suppliers:
- Energy Australia
- Origin Energy
- Climate Active Advisor
- Carbon Neutral Pty Ltd
- Sustainable Packaging Co
- Green Freight
- EcoVadis
- Bureau Veritas

---

**Document Version:** 1.0  
**Last Updated:** April 29, 2026  
**Generated By:** IBM Bob Dataset Generator v1.0

---

*This documentation is part of the IBM Bob Demo Assets for March 2026. All data is synthetic and generated for demonstration purposes only.*