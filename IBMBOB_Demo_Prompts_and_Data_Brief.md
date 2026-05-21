# IBM Bob Demo Prompts and Dataset Creation Brief

## IBM BOB 1 - Group P&L
Dataset prompt: Create 1,000 additional March-only P&L transaction line items across revenue, cost of revenue, operating expenses, other income/expense and tax provision. Preserve source-system fields, cost centres, entities, vendors, invoice numbers and close-readiness flags. Add rows to `IBMBOB_Group_PL_LineItems_Mar2026.csv` and linked GL postings to `Raw_GL_Export_With_CostCenters_Mar2026_IBMBOB_Enhanced.csv`.

Demo prompt: Create a CFO-ready Profit & Loss statement using March 2026 month-end data only. Structure columns for March Actuals, MTD, YTD if available, and variance vs plan where available. Include Revenue, Cost of Revenue, Gross Profit, Operating Expenses, Income from Operations, Other Income/Expense, Income Before Tax, Tax Provision and Net Income. Use only source data, reconcile totals back to the enhanced GL, flag unusual variances and show items requiring approval before close.

## IBM BOB 2 - Workforce
Dataset prompt: Create 1,000 March 2026 workforce cost and output records linked to GL salary postings. Include employee, business unit, department, role, salary, overtime, benefits, contractor cost, total workforce cost, hours, utilisation, output volume, revenue/value supported, labour cost per output, risk flags and recommended actions. Store in `IBMBOB_Workforce_Cost_Output_Mar2026.csv` and append payroll-linked GL records to the enhanced GL file.

Demo prompts:
1. Using March financial and workforce data, correlate workforce cost with revenue or output by business unit and identify areas where labour cost is not aligned with business performance.
2. Using March workforce data, analyse salary costs by department, identify unusual changes, duplicate or high-overtime patterns, and highlight financial or compliance risks.
3. From March month-end data, identify areas where workforce cost is increasing without a corresponding improvement in output or utilisation.
4. Analyse workforce costs across departments and recommend resource allocation changes to improve utilisation and margin.

## IBM BOB 3 - ESG
Dataset prompt: Create 1,000 March 2026 ESG cost and KPI records linked to GL transactions. Include sustainability spend category, supplier, cost centre, account, KPI target/actual, carbon impact, renewable sourcing, supplier ESG score, working capital impact, margin impact, misclassification flags, disclosure evidence status and audit-readiness status. Store in `IBMBOB_ESG_Cost_KPI_Mar2026.csv` and append financial postings to the enhanced GL file.

Demo prompts:
1. From March financials, identify cost centres contributing to sustainability-related spend, detect ESG cost leakage or misclassification, quantify financial impact and recommend corrections.
2. Analyse March close data to determine how ESG activities have impacted working capital, margins and cash flow. Provide a CFO-level view of sustainability investment trade-offs.
3. Based on March close outputs, assess ESG disclosure readiness. Validate completeness, traceability and auditability across finance, operations and supplier data.
4. Using March close as baseline, simulate a 10-15% increase in sustainability targets and model impact on cost structure, margins, supplier mix and compliance risk.
5. Generate a board-ready ESG performance narrative for March linking sustainability outcomes to financial performance, risk exposure and strategic priorities.
