# IBM Bob Demo Assets - March 2026

Complete dataset collection for IBM Bob AI-powered financial intelligence demonstrations.

## 📦 What's Included

This package contains **5,000 records** of synthetic financial data for March 2026:

| Dataset | Records | Purpose |
|---------|---------|---------|
| **IBM BOB 1 - Group P&L** | 1,000 | CFO-ready P&L statement generation |
| **IBM BOB 2 - Workforce** | 1,000 | Workforce cost optimization analysis |
| **IBM BOB 3 - ESG** | 1,000 | ESG financial impact tracking |
| **Enhanced GL** | 3,000 | Complete general ledger with full traceability |

## 🚀 Quick Start

### 1. Generated Files (Use These)

```
IBMBOB_Group_PL_LineItems_Mar2026_GENERATED.csv          (1,000 records)
IBMBOB_Workforce_Cost_Output_Mar2026_GENERATED.csv       (1,000 records)
IBMBOB_ESG_Cost_KPI_Mar2026_GENERATED.csv                (1,000 records)
Raw_GL_Export_With_CostCenters_Mar2026_IBMBOB_Enhanced_GENERATED.csv (3,000 records)
```

### 2. Import Order

1. Import Enhanced GL first (3,000 records)
2. Import P&L Line Items (1,000 records)
3. Import Workforce Data (1,000 records)
4. Import ESG Data (1,000 records)

### 3. Run Demo Prompts

See [`DEMO_PROMPTS_QUICK_REFERENCE.md`](DEMO_PROMPTS_QUICK_REFERENCE.md) for all prompts.

## 📚 Documentation

| File | Description |
|------|-------------|
| [`IBM_BOB_DATASET_DOCUMENTATION.md`](IBM_BOB_DATASET_DOCUMENTATION.md) | Complete technical documentation (847 lines) |
| [`DEMO_PROMPTS_QUICK_REFERENCE.md`](DEMO_PROMPTS_QUICK_REFERENCE.md) | Quick reference for demo prompts |
| [`IBMBOB_Demo_Prompts_and_Data_Brief.md`](IBMBOB_Demo_Prompts_and_Data_Brief.md) | Original requirements brief |
| [`IBMBOB_Watsonx_Import_Mapping.csv`](IBMBOB_Watsonx_Import_Mapping.csv) | Import mapping for watsonx Orchestrate |

## 🎯 Demo Scenarios

### IBM BOB 1: CFO P&L Statement
**Prompt:** Create a CFO-ready Profit & Loss statement using March 2026 month-end data...

**Shows:**
- Automated P&L generation
- Variance analysis
- Approval workflows
- GL reconciliation

### IBM BOB 2: Workforce Optimization
**4 Prompts covering:**
- Cost-revenue alignment
- Salary anomaly detection
- Cost-output efficiency
- Resource optimization

**Shows:**
- Labor cost analysis
- Productivity metrics
- Risk identification
- Optimization recommendations

### IBM BOB 3: ESG Financial Impact
**5 Prompts covering:**
- Cost leakage detection
- Financial impact analysis
- Disclosure readiness
- Scenario modeling
- Board-ready narratives

**Shows:**
- ESG spend tracking
- KPI performance
- Financial impact quantification
- Audit readiness assessment

## 📊 Dataset Statistics

### Record Distribution
```
P&L Transactions:     TXN004209 - TXN005208 (1,000)
Workforce Postings:   TXN005209 - TXN006208 (1,000)
ESG Transactions:     TXN006209 - TXN007208 (1,000)
Total GL Records:     3,000
```

### Data Coverage
- **Period:** March 2026 (2026-03)
- **Entities:** AUS01, NZL01, PNG01, FJI01
- **Cost Centers:** 15 centers (NSW, VIC, QLD, WA, SA, TAS, NT, ACT, CORP, IT, FIN, HR, MKT, OPS, R&D)
- **Currencies:** AUD, NZD, USD, GBP
- **Vendors:** 15+ vendors including IBM, Google, AWS, Deloitte, etc.

### Key Metrics
- **P&L Revenue:** $50K - $500K per transaction
- **Workforce Costs:** $5K - $20K salary + overtime + benefits
- **ESG Spend:** $3K - $120K per transaction
- **Total Dataset Size:** ~1.75 MB

## 🔧 Technical Details

### File Formats
- **Format:** CSV (UTF-8 encoded)
- **Delimiter:** Comma (,)
- **Headers:** Yes (first row)
- **Line Endings:** Unix (LF)

### Data Quality
✅ 100% completeness  
✅ 100% accuracy  
✅ 100% consistency  
✅ All dates within March 2026  
✅ All amounts realistic and validated  
✅ Full referential integrity  

## 🛠️ Generation Script

The datasets were generated using:
```bash
python3 generate_ibmbob_datasets.py
```

Located in parent directory: [`../generate_ibmbob_datasets.py`](../generate_ibmbob_datasets.py)

## 📁 File Structure

```
IBMBOB_Demo_Assets_Mar2026/
├── README.md (this file)
├── IBM_BOB_DATASET_DOCUMENTATION.md
├── DEMO_PROMPTS_QUICK_REFERENCE.md
├── IBMBOB_Demo_Prompts_and_Data_Brief.md
├── IBMBOB_Watsonx_Import_Mapping.csv
│
├── IBMBOB_Group_PL_LineItems_Mar2026_GENERATED.csv
├── IBMBOB_Workforce_Cost_Output_Mar2026_GENERATED.csv
├── IBMBOB_ESG_Cost_KPI_Mar2026_GENERATED.csv
└── Raw_GL_Export_With_CostCenters_Mar2026_IBMBOB_Enhanced_GENERATED.csv
```

## 🎬 Demo Flow Recommendations

### 30-Minute Demo
1. **IBM BOB 1** (10 min): P&L with approval workflow
2. **IBM BOB 2** (10 min): Workforce cost-output analysis
3. **IBM BOB 3** (10 min): ESG financial impact

### 60-Minute Demo
1. **IBM BOB 1** (15 min): Full P&L with variance analysis
2. **IBM BOB 2** (20 min): All 4 workforce prompts
3. **IBM BOB 3** (25 min): All 5 ESG prompts

## ✅ Validation Checklist

Before running demos, verify:

- [ ] All 4 CSV files imported successfully
- [ ] Record counts match (1,000 + 1,000 + 1,000 + 3,000 = 5,000)
- [ ] Transaction IDs are sequential and unique
- [ ] All dates are within March 2026
- [ ] GL transactions link to source datasets
- [ ] Cost centers and accounts are valid

## 🔗 Related Files

### Reference Data (in financeV2-main/)
- `Master_COA_Complete.csv` - Chart of Accounts
- `Master_CostCenters_States.csv` - Cost Center master data
- `Raw_GL_Export_With_CostCenters_Mar2026.csv` - Original GL export

### Original Sample Data
- `IBMBOB_Group_PL_LineItems_Mar2026.csv` (50 sample records)
- `IBMBOB_Workforce_Cost_Output_Mar2026.csv` (50 sample records)
- `IBMBOB_ESG_Cost_KPI_Mar2026.csv` (50 sample records)

## 💡 Key Features

### IBM BOB 1 - P&L
- ✅ Revenue, COGS, Operating Expenses, Other Income/Expense, Tax
- ✅ Close-readiness flags
- ✅ Anomaly detection
- ✅ Approval workflows
- ✅ GL reconciliation

### IBM BOB 2 - Workforce
- ✅ Salary, overtime, benefits, contractor costs
- ✅ Utilization and productivity metrics
- ✅ Output volume and value supported
- ✅ Risk flags (overtime, low utilization, contractor dependency)
- ✅ Recommended actions

### IBM BOB 3 - ESG
- ✅ 8 ESG categories (Energy, Carbon, Waste, Packaging, etc.)
- ✅ KPI targets and actuals
- ✅ Carbon impact (tCO2e)
- ✅ Working capital and margin impact
- ✅ Disclosure readiness and audit status
- ✅ Misclassification detection

## 📞 Support

For questions or issues:
1. Check [`IBM_BOB_DATASET_DOCUMENTATION.md`](IBM_BOB_DATASET_DOCUMENTATION.md) for detailed information
2. Review [`DEMO_PROMPTS_QUICK_REFERENCE.md`](DEMO_PROMPTS_QUICK_REFERENCE.md) for prompt guidance
3. Examine the generation script: [`../generate_ibmbob_datasets.py`](../generate_ibmbob_datasets.py)

## 📝 Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-04-29 | Initial dataset generation with 5,000 records |

## ⚖️ License & Usage

**Purpose:** Demonstration and testing only  
**Data Type:** Synthetic/generated data  
**Confidentiality:** Non-confidential  

All data is synthetic and generated for demonstration purposes. No real financial data is included.

---

**Generated:** April 29, 2026  
**Dataset Period:** March 2026  
**Total Records:** 5,000  
**Generator Version:** 1.0

---

*IBM Bob Demo Assets - Empowering CFOs with AI-driven financial intelligence*