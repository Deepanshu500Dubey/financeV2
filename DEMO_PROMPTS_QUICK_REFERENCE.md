# IBM Bob Demo Prompts - Quick Reference Guide

**Dataset Period:** March 2026  
**Total Records:** 5,000 (1,000 each for P&L, Workforce, ESG + 3,000 GL records)

---

## 🎯 IBM BOB 1 - Group P&L

### Dataset
- **File:** `IBMBOB_Group_PL_LineItems_Mar2026_GENERATED.csv`
- **Records:** 1,000 P&L line items
- **GL File:** `Raw_GL_Export_With_CostCenters_Mar2026_IBMBOB_Enhanced_GENERATED.csv`

### Demo Prompt

```
Create a CFO-ready Profit & Loss statement using March 2026 month-end data only. 
Structure columns for March Actuals, MTD, YTD if available, and variance vs plan 
where available. Include Revenue, Cost of Revenue, Gross Profit, Operating Expenses, 
Income from Operations, Other Income/Expense, Income Before Tax, Tax Provision and 
Net Income. Use only source data, reconcile totals back to the enhanced GL, flag 
unusual variances and show items requiring approval before close.
```

### Expected Outputs
✅ Structured P&L with standard sections  
✅ Revenue breakdown (Product, Service, Subscription)  
✅ COGS and gross margin analysis  
✅ Operating expense categorization  
✅ High-variance items flagged  
✅ Transactions requiring approval listed  
✅ GL reconciliation confirmed  
✅ Close-readiness assessment  

---

## 👥 IBM BOB 2 - Workforce

### Dataset
- **File:** `IBMBOB_Workforce_Cost_Output_Mar2026_GENERATED.csv`
- **Records:** 1,000 employee/contractor records
- **GL File:** `Raw_GL_Export_With_CostCenters_Mar2026_IBMBOB_Enhanced_GENERATED.csv`

### Demo Prompt 1: Cost-Revenue Alignment

```
Using March financial and workforce data, correlate workforce cost with revenue 
or output by business unit and identify areas where labour cost is not aligned 
with business performance.
```

**Expected Outputs:**
- Cost per output by business unit
- Revenue/value supported vs. workforce cost
- High-cost, low-output areas identified
- Cross-department benchmarking
- Reallocation recommendations

### Demo Prompt 2: Salary Cost Anomalies

```
Using March workforce data, analyse salary costs by department, identify unusual 
changes, duplicate or high-overtime patterns, and highlight financial or compliance risks.
```

**Expected Outputs:**
- Department-level salary analysis
- Overtime pattern identification
- Contractor dependency assessment
- Compliance risk flagging
- Cost anomaly detection

### Demo Prompt 3: Cost-Output Efficiency

```
From March month-end data, identify areas where workforce cost is increasing 
without a corresponding improvement in output or utilisation.
```

**Expected Outputs:**
- Cost vs. output trend analysis
- Utilization rate assessment
- Productivity metrics by role
- Inefficiency identification
- Cost optimization opportunities

### Demo Prompt 4: Resource Optimization

```
Analyse workforce costs across departments and recommend resource allocation 
changes to improve utilisation and margin.
```

**Expected Outputs:**
- Cross-department comparison
- Utilization gap analysis
- Margin impact calculation
- Reallocation recommendations
- Expected ROI from changes

---

## 🌱 IBM BOB 3 - ESG

### Dataset
- **File:** `IBMBOB_ESG_Cost_KPI_Mar2026_GENERATED.csv`
- **Records:** 1,000 ESG transactions
- **GL File:** `Raw_GL_Export_With_CostCenters_Mar2026_IBMBOB_Enhanced_GENERATED.csv`

### Demo Prompt 1: ESG Cost Leakage Detection

```
From March financials, identify cost centres contributing to sustainability-related 
spend, detect ESG cost leakage or misclassification, quantify financial impact and 
recommend corrections.
```

**Expected Outputs:**
- ESG spend by cost center
- Misclassification detection
- Leakage quantification
- Reclassification recommendations
- Financial impact assessment

### Demo Prompt 2: Financial Impact Analysis

```
Analyse March close data to determine how ESG activities have impacted working 
capital, margins and cash flow. Provide a CFO-level view of sustainability 
investment trade-offs.
```

**Expected Outputs:**
- Working capital impact summary
- Margin impact by ESG category
- Cash flow implications
- ROI on ESG investments
- Trade-off analysis

### Demo Prompt 3: Disclosure Readiness Assessment

```
Based on March close outputs, assess ESG disclosure readiness. Validate completeness, 
traceability and auditability across finance, operations and supplier data.
```

**Expected Outputs:**
- Disclosure completeness score
- Evidence gap identification
- Audit readiness assessment
- Supplier data validation
- Remediation priorities

### Demo Prompt 4: Scenario Modeling

```
Using March close as baseline, simulate a 10-15% increase in sustainability targets 
and model impact on cost structure, margins, supplier mix and compliance risk.
```

**Expected Outputs:**
- Cost impact projection
- Margin sensitivity analysis
- Supplier mix changes
- Compliance risk assessment
- Implementation roadmap

### Demo Prompt 5: Board-Ready Narrative

```
Generate a board-ready ESG performance narrative for March linking sustainability 
outcomes to financial performance, risk exposure and strategic priorities.
```

**Expected Outputs:**
- Executive summary of ESG performance
- KPI achievement vs. targets
- Financial performance linkage
- Risk and opportunity assessment
- Strategic recommendations

---

## 📊 Key Metrics by Dataset

### IBM BOB 1 - P&L Metrics
- **Revenue Range:** $50K - $500K per transaction
- **Expense Range:** $3K - $200K per transaction
- **COGS Range:** $20K - $150K per transaction
- **Approval Required:** ~25% of transactions
- **Close Ready:** ~75% of transactions

### IBM BOB 2 - Workforce Metrics
- **Salary Range:** $5K - $20K per month
- **Overtime:** $0 - $2.5K per month
- **Utilization:** 55% - 98%
- **Output Volume:** 40 - 300 units
- **Risk Flags:** ~40% of records

### IBM BOB 3 - ESG Metrics
- **Spend Range:** $3K - $120K per transaction
- **KPI Attainment:** 65% - 125%
- **Carbon Impact:** 20 - 550 tCO2e
- **Renewable %:** 1% - 99%
- **Approval Required:** ~40% of transactions

---

## 🔗 Data Linkage

All datasets link to the Enhanced GL:

```
P&L Transactions:     TXN004209 - TXN005208 (1,000 records)
Workforce Postings:   TXN005209 - TXN006208 (1,000 records)
ESG Transactions:     TXN006209 - TXN007208 (1,000 records)
```

**Total GL Records:** 3,000

---

## 📁 File Locations

All files are in: `IBMBOB_Demo_Assets_Mar2026/`

### Generated Files (Use These for Demos)
- `IBMBOB_Group_PL_LineItems_Mar2026_GENERATED.csv`
- `IBMBOB_Workforce_Cost_Output_Mar2026_GENERATED.csv`
- `IBMBOB_ESG_Cost_KPI_Mar2026_GENERATED.csv`
- `Raw_GL_Export_With_CostCenters_Mar2026_IBMBOB_Enhanced_GENERATED.csv`

### Reference Files
- `Master_COA_Complete.csv` (in financeV2-main/)
- `Master_CostCenters_States.csv` (in financeV2-main/)

### Documentation
- `IBM_BOB_DATASET_DOCUMENTATION.md` (Complete documentation)
- `DEMO_PROMPTS_QUICK_REFERENCE.md` (This file)
- `IBMBOB_Demo_Prompts_and_Data_Brief.md` (Original brief)

---

## 🚀 Quick Start

### 1. Import Data
Import files in this order:
1. Enhanced GL (3,000 records)
2. P&L Line Items (1,000 records)
3. Workforce Data (1,000 records)
4. ESG Data (1,000 records)

### 2. Verify Import
Check record counts match expected values

### 3. Run Demo Prompts
Start with IBM BOB 1, then proceed to 2 and 3

### 4. Validate Results
Ensure outputs include all expected analysis components

---

## 💡 Demo Tips

### For IBM BOB 1 (P&L)
- Emphasize CFO-ready formatting
- Highlight variance analysis
- Show approval workflow integration
- Demonstrate GL reconciliation

### For IBM BOB 2 (Workforce)
- Focus on cost-output correlation
- Highlight risk flags and anomalies
- Show cross-department comparisons
- Emphasize optimization recommendations

### For IBM BOB 3 (ESG)
- Demonstrate financial impact quantification
- Show disclosure readiness assessment
- Highlight misclassification detection
- Emphasize board-level narrative generation

---

## 🎬 Demo Flow Suggestion

**30-Minute Demo:**
1. **IBM BOB 1** (10 min): CFO P&L statement with approval workflow
2. **IBM BOB 2** (10 min): Workforce cost-output analysis with risk flags
3. **IBM BOB 3** (10 min): ESG financial impact and disclosure readiness

**60-Minute Demo:**
1. **IBM BOB 1** (15 min): Full P&L analysis with variance deep-dive
2. **IBM BOB 2** (20 min): All 4 workforce prompts
3. **IBM BOB 3** (25 min): All 5 ESG prompts including scenario modeling

---

## 📞 Support

For questions or issues:
- See full documentation: `IBM_BOB_DATASET_DOCUMENTATION.md`
- Dataset generator: `generate_ibmbob_datasets.py`
- Original brief: `IBMBOB_Demo_Prompts_and_Data_Brief.md`

---

**Last Updated:** April 29, 2026  
**Version:** 1.0  
**Dataset Period:** March 2026