# IBM BOB Endpoints - Quick Reference & Examples

## Base URL
```
http://localhost:8000
```

## Swagger Documentation
```
http://localhost:8000/docs
```

---

## P&L Analysis Endpoints

### 1. Generate P&L Statement
```bash
# Basic call
curl "http://localhost:8000/tools/pl/statement?fiscal_period=2026-03"

# With custom period
curl "http://localhost:8000/tools/pl/statement?fiscal_period=2026-04"
```

**Example Response:**
```json
{
  "success": true,
  "message": "Generated P&L statement for 2026-03",
  "data": {
    "fiscal_period": "2026-03",
    "revenue": 5432109.45,
    "cogs": 2345678.90,
    "gross_profit": 3086430.55,
    "operating_expenses": 1123456.78,
    "operating_income": 1962973.77,
    "other_income_expense": 123456.89,
    "income_before_tax": 2086430.66,
    "tax_provision": 417286.13,
    "net_income": 1669144.53,
    "sections": {
      "Revenue": {
        "total": 5432109.45,
        "items": 342,
        "line_items": [...]
      }
    },
    "approval_summary": {
      "total_items": 1000,
      "items_requiring_approval": 247,
      "anomalies_flagged": 89,
      "close_readiness_percent": 78.5
    }
  }
}
```

---

### 2. Get P&L Transactions
```bash
# All transactions
curl "http://localhost:8000/tools/pl/transactions?fiscal_period=2026-03"

# Filter by section
curl "http://localhost:8000/tools/pl/transactions?fiscal_period=2026-03&section=Revenue"

# Filter by Operating Expenses
curl "http://localhost:8000/tools/pl/transactions?fiscal_period=2026-03&section=Operating%20expenses"
```

**Example Response:**
```json
{
  "success": true,
  "message": "Retrieved 287 P&L transactions",
  "data": {
    "fiscal_period": "2026-03",
    "transactions": [
      {
        "txn_id": "TXN004209",
        "account_code": "4100",
        "line_item": "Interest income",
        "section": "Other income / expense",
        "amount": 127291.16,
        "vendor": "Salesforce",
        "invoice_number": "BOB-PL-0001",
        "close_readiness": "Ready",
        "anomaly_flag": "None",
        "approval_required": "No"
      },
      {
        "txn_id": "TXN004210",
        "account_code": "5120",
        "line_item": "Office supplies",
        "section": "Other operating expenses",
        "amount": 81860.13,
        "vendor": "Deloitte",
        "invoice_number": "BOB-PL-0002",
        "close_readiness": "Pending review",
        "anomaly_flag": "None",
        "approval_required": "Yes"
      }
    ]
  }
}
```

---

### 3. Get P&L Approval Items
```bash
curl "http://localhost:8000/tools/pl/approval_items?fiscal_period=2026-03"
```

**Example Response:**
```json
{
  "success": true,
  "message": "Found 247 items requiring approval",
  "data": {
    "fiscal_period": "2026-03",
    "approval_items": [
      {
        "txn_id": "TXN004210",
        "description": "Office supplies",
        "amount": 81860.13,
        "reason": "Requires approval",
        "vendor": "Deloitte",
        "invoice_number": "BOB-PL-0002",
        "close_readiness": "Pending review"
      },
      {
        "txn_id": "TXN004532",
        "description": "Software licenses",
        "amount": 156734.89,
        "reason": "Anomaly: High variance",
        "vendor": "Microsoft",
        "invoice_number": "BOB-PL-0145",
        "close_readiness": "Ready"
      }
    ],
    "count": 247
  }
}
```

---

### 4. P&L to GL Reconciliation
```bash
curl "http://localhost:8000/tools/pl/gl_reconciliation?fiscal_period=2026-03"
```

**Example Response:**
```json
{
  "success": true,
  "message": "GL reconciliation complete - variance: $0.00",
  "data": {
    "fiscal_period": "2026-03",
    "pl_total": 8709430.66,
    "gl_total": 8709430.66,
    "variance": 0.00,
    "variance_percent": 0.0,
    "reconciled": true,
    "pl_record_count": 1000,
    "gl_record_count": 1000
  }
}
```

---

### 5. Analyze P&L Variances
```bash
curl "http://localhost:8000/tools/pl/variance_analysis?fiscal_period=2026-03"
```

**Example Response:**
```json
{
  "success": true,
  "message": "Identified 3 variance types",
  "data": {
    "fiscal_period": "2026-03",
    "variance_summary": {
      "High variance": {
        "count": 45,
        "total_amount": 2345678.90,
        "items": [
          {
            "txn_id": "TXN004532",
            "description": "Software licenses",
            "amount": 156734.89,
            "vendor": "Microsoft"
          }
        ]
      }
    },
    "total_variance_items": 89,
    "total_variance_amount": 4567890.12
  }
}
```

---

## Workforce Analysis Endpoints

### 1. Cost-Revenue Correlation
```bash
# All business units
curl "http://localhost:8000/tools/workforce/cost_revenue_correlation?fiscal_period=2026-03"

# Specific business unit
curl "http://localhost:8000/tools/workforce/cost_revenue_correlation?fiscal_period=2026-03&business_unit=Finance"
```

**Example Response:**
```json
{
  "success": true,
  "message": "Analyzed cost-revenue correlation for 7 business units",
  "data": {
    "fiscal_period": "2026-03",
    "by_business_unit": {
      "Finance": {
        "total_workforce_cost": 856234.56,
        "total_revenue_supported": 12345678.90,
        "total_output_volume": 342,
        "cost_per_revenue": 0.069,
        "revenue_per_employee": 1234567.89,
        "employee_count": 10
      },
      "Sales": {
        "total_workforce_cost": 1245678.90,
        "total_revenue_supported": 18765432.12,
        "total_output_volume": 567,
        "cost_per_revenue": 0.066,
        "revenue_per_employee": 1878543.21,
        "employee_count": 10
      }
    },
    "total_workforce_cost": 8765432.10,
    "total_revenue_supported": 98765432.10
  }
}
```

---

### 2. Salary Analysis
```bash
curl "http://localhost:8000/tools/workforce/salary_analysis?fiscal_period=2026-03"
```

**Example Response:**
```json
{
  "success": true,
  "message": "Analyzed salary costs for 8 departments",
  "data": {
    "fiscal_period": "2026-03",
    "by_department": {
      "Finance": {
        "total_salary": 345678.90,
        "average_salary": 34567.89,
        "total_overtime": 12345.67,
        "overtime_percent": 3.4,
        "contractor_cost": 0,
        "contractor_dependency_percent": 0,
        "headcount": 10,
        "risk_items": 2,
        "risk_percent": 20.0
      }
    },
    "total_risk_items": 23,
    "risk_items": [
      {
        "employee_id": "EMP1234",
        "department": "Finance",
        "role": "Finance Analyst",
        "risk_flag": "High overtime",
        "salary": 5000,
        "overtime": 1500,
        "recommended_action": "Review allocation / approve exception"
      }
    ]
  }
}
```

---

### 3. Cost-Output Efficiency
```bash
curl "http://localhost:8000/tools/workforce/cost_output_efficiency?fiscal_period=2026-03"
```

**Example Response:**
```json
{
  "success": true,
  "message": "Identified 156 items with efficiency concerns",
  "data": {
    "fiscal_period": "2026-03",
    "inefficient_items": [
      {
        "employee_id": "EMP8765",
        "role": "Operations Coordinator",
        "business_unit": "Operations",
        "total_cost": 18500,
        "output_volume": 15,
        "utilisation_percent": 62.3,
        "cost_per_output": 1233.33,
        "efficiency_score": 88.9
      }
    ],
    "by_business_unit": {
      "Operations": {
        "total_cost": 2345678.90,
        "total_output": 1234,
        "average_utilisation": 71.5,
        "cost_per_output": 1901.28,
        "efficiency_rating": "MEDIUM"
      }
    },
    "total_inefficient_count": 156
  }
}
```

---

### 4. Resource Optimization
```bash
curl "http://localhost:8000/tools/workforce/resource_optimization?fiscal_period=2026-03"
```

**Example Response:**
```json
{
  "success": true,
  "message": "Generated 47 optimization recommendations",
  "data": {
    "fiscal_period": "2026-03",
    "recommendations": [
      {
        "business_unit": "Operations",
        "role": "Coordinator",
        "issue": "Low Utilisation",
        "current_utilisation": 65.2,
        "target_utilisation": 85,
        "potential_margin_improvement": 45678.90,
        "action": "Reallocate to higher-demand areas or consider cross-training"
      },
      {
        "business_unit": "Finance",
        "role": "Analyst",
        "issue": "High Cost Per Output",
        "current_cost_per_output": 1250.00,
        "target_cost_per_output": 300,
        "potential_savings": 285000.00,
        "action": "Review processes and consider automation or outsourcing"
      }
    ],
    "total_potential_margin_improvement": 1234567.89,
    "total_potential_savings": 3456789.12
  }
}
```

---

### 5. Labour Cost Metrics
```bash
# All business units
curl "http://localhost:8000/tools/workforce/labour_cost_metrics?fiscal_period=2026-03"

# Specific business unit
curl "http://localhost:8000/tools/workforce/labour_cost_metrics?fiscal_period=2026-03&business_unit=Finance"
```

**Example Response:**
```json
{
  "success": true,
  "message": "Calculated labour cost metrics for 7 business units",
  "data": {
    "fiscal_period": "2026-03",
    "by_business_unit": {
      "Finance": {
        "total_workforce_cost": 856234.56,
        "total_output": 342,
        "total_revenue_supported": 12345678.90,
        "average_labour_cost_per_output": 2501.28,
        "min_labour_cost_per_output": 1234.56,
        "max_labour_cost_per_output": 3456.78,
        "employee_count": 10,
        "revenue_per_cost": 14.41
      }
    }
  }
}
```

---

## ESG Analysis Endpoints

### 1. ESG Leakage Detection
```bash
curl "http://localhost:8000/tools/esg/leakage_detection?fiscal_period=2026-03"
```

**Example Response:**
```json
{
  "success": true,
  "message": "Detected 12 misclassifications and 8 leakage items",
  "data": {
    "fiscal_period": "2026-03",
    "misclassified_items": [
      {
        "esg_record_id": "ESG-MAR26-0045",
        "category": "Energy usage",
        "spend": 45678.90,
        "account_code": "6000",
        "account_name": "Cost of Goods Sold",
        "supplier": "Carbon Neutral Pty Ltd",
        "issue": "Incorrect GL coding",
        "recommendation": "Reclassify to correct ESG cost center"
      }
    ],
    "summary": {
      "total_misclassified_count": 12,
      "total_misclassified_spend": 567890.12,
      "total_leakage_count": 8,
      "total_leakage_spend": 234567.89
    }
  }
}
```

---

### 2. ESG Financial Impact
```bash
curl "http://localhost:8000/tools/esg/financial_impact?fiscal_period=2026-03"
```

**Example Response:**
```json
{
  "success": true,
  "message": "Analyzed financial impact of ESG spending",
  "data": {
    "fiscal_period": "2026-03",
    "financial_impact": {
      "total_esg_spend": 2345678.90,
      "total_working_capital_impact": -123456.78,
      "total_margin_impact_basis_points": -12.5,
      "cash_flow_impact": 123456.78,
      "by_category": {
        "Energy usage": {
          "spend": 567890.12,
          "working_capital_impact": -34567.89,
          "margin_impact_basis_points": -3.2,
          "average_margin_impact": -0.32
        }
      }
    }
  }
}
```

---

### 3. Disclosure Readiness
```bash
curl "http://localhost:8000/tools/esg/disclosure_readiness?fiscal_period=2026-03"
```

**Example Response:**
```json
{
  "success": true,
  "message": "Assessment complete - 76.5% disclosure ready",
  "data": {
    "fiscal_period": "2026-03",
    "disclosure_readiness": {
      "complete_percent": 76.5,
      "by_status": {
        "Complete": 765,
        "Partial": 180,
        "Missing": 55
      }
    },
    "audit_readiness": {
      "ready_percent": 82.3,
      "by_status": {
        "Ready": 823,
        "Needs review": 145,
        "Partial": 32
      }
    },
    "missing_evidence_count": 235,
    "missing_evidence_items": [...]
  }
}
```

---

### 4. ESG Scenario Modeling
```bash
# 15% target increase (default)
curl "http://localhost:8000/tools/esg/scenario_modeling?fiscal_period=2026-03"

# 20% target increase
curl "http://localhost:8000/tools/esg/scenario_modeling?fiscal_period=2026-03&target_increase_percent=20"

# 10% target increase
curl "http://localhost:8000/tools/esg/scenario_modeling?fiscal_period=2026-03&target_increase_percent=10"
```

**Example Response:**
```json
{
  "success": true,
  "message": "Modeled 15% target increase scenario",
  "data": {
    "fiscal_period": "2026-03",
    "scenario": {
      "target_increase_percent": 15,
      "current_total_spend": 2345678.90,
      "scenario_total_spend": 2697530.74,
      "spend_increase": 351851.84,
      "by_category": {
        "Energy usage": {
          "current_spend": 567890.12,
          "scenario_spend": 653273.64,
          "current_avg_kpi": 95.2,
          "scenario_avg_kpi": 118.1
        }
      }
    }
  }
}
```

---

### 5. ESG Board Narrative
```bash
curl "http://localhost:8000/tools/esg/board_narrative?fiscal_period=2026-03"
```

**Example Response:**
```json
{
  "success": true,
  "message": "Generated board-ready ESG narrative",
  "data": {
    "fiscal_period": "2026-03",
    "metrics": {
      "total_esg_spend": 2345678.90,
      "average_kpi_attainment": 98.5,
      "total_carbon_reduction": 12345.67,
      "average_renewable_percent": 67.3,
      "average_supplier_score": 82.1,
      "working_capital_impact": -123456.78,
      "margin_impact_basis_points": -12.5
    },
    "narrative": "ESG Performance Summary for 2026-03\n\nFINANCIAL INVESTMENT:\n• Total ESG Investment: $2,345,678.90\n• Working Capital Impact: $-123,456.78\n• Margin Impact: -12.5 basis points\n\nSUSTAINABILITY OUTCOMES:\n• Average KPI Attainment: 98.5%\n• Total Carbon Reduction: 12,345.67 tCO2e\n• Average Renewable Sourcing: 67.3%\n• Supplier ESG Score Average: 82.1/100\n..."
  }
}
```

---

### 6. ESG KPI Tracking
```bash
# All KPIs
curl "http://localhost:8000/tools/esg/kpi_tracking?fiscal_period=2026-03"

# Specific category
curl "http://localhost:8000/tools/esg/kpi_tracking?fiscal_period=2026-03&category=Energy%20usage"
```

**Example Response:**
```json
{
  "success": true,
  "message": "Tracked 4 KPI metrics",
  "data": {
    "fiscal_period": "2026-03",
    "kpi_tracking": {
      "tCO2e avoided": {
        "count": 342,
        "total_target": 250000,
        "total_actual": 267500,
        "average_attainment": 107.0,
        "overall_attainment": 107.0
      }
    },
    "summary": {
      "total_kpi_types": 4,
      "average_attainment_percent": 98.5
    }
  }
}
```

---

## Consolidated Summary Endpoint

### Get IBM BOB Summary
```bash
curl "http://localhost:8000/tools/ibm_bob/summary/2026-03"
```

**Example Response:**
```json
{
  "success": true,
  "message": "Summary for 2026-03 - Overall readiness: 82.3%",
  "data": {
    "fiscal_period": "2026-03",
    "pl_metrics": {
      "total_items": 1000,
      "items_requiring_approval": 247,
      "anomalies_flagged": 89,
      "close_ready": 785
    },
    "workforce_metrics": {
      "total_employees": 1000,
      "total_workforce_cost": 8765432.10,
      "total_revenue_supported": 98765432.10,
      "risk_items": 156,
      "average_utilisation": 76.3
    },
    "esg_metrics": {
      "total_records": 1000,
      "total_esg_spend": 2345678.90,
      "items_requiring_approval": 345,
      "misclassified_items": 12,
      "average_kpi_attainment": 98.5
    },
    "approval_summary": {
      "total_items_requiring_approval": 592,
      "pending_approvals": 247,
      "approved": 345,
      "rejected": 0
    },
    "readiness_score": 82.3,
    "readiness_status": "READY",
    "dashboard_url": "http://localhost:8000/dashboard"
  }
}
```

---

## Testing with cURL

### PowerShell (Windows)
```powershell
# Test P&L endpoint
$response = Invoke-WebRequest -Uri "http://localhost:8000/tools/pl/statement?fiscal_period=2026-03" -Method Get
$response | ConvertFrom-Json | ConvertTo-Json -Depth 10

# Test Workforce endpoint
$response = Invoke-WebRequest -Uri "http://localhost:8000/tools/workforce/cost_revenue_correlation?fiscal_period=2026-03" -Method Get
$response.Content | ConvertFrom-Json
```

### Bash (Linux/Mac)
```bash
# Test P&L endpoint
curl -H "Content-Type: application/json" \
  "http://localhost:8000/tools/pl/statement?fiscal_period=2026-03" | jq .

# Test Workforce endpoint
curl -H "Content-Type: application/json" \
  "http://localhost:8000/tools/workforce/salary_analysis?fiscal_period=2026-03" | jq .
```

---

## Response Format

All endpoints return consistent `ToolResponse` format:

```json
{
  "success": true|false,
  "message": "Description of operation and result",
  "data": {
    "...": "Endpoint-specific data"
  },
  "timestamp": "2026-03-31T12:34:56.789012"
}
```

---

## Common Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `fiscal_period` | string | "2026-03" | Period in YYYY-MM format |
| `business_unit` | string | Optional | Filter by business unit name |
| `section` | string | Optional | Filter by P&L section |
| `category` | string | Optional | Filter by ESG category |
| `target_increase_percent` | float | 15 | Target increase for ESG scenario (5-30%) |

---

## Error Handling

All errors returned as ToolResponse:

```json
{
  "success": false,
  "message": "Error description",
  "timestamp": "2026-03-31T12:34:56.789012"
}
```

Common HTTP status codes:
- **200**: Successful
- **404**: Data not found for period
- **500**: Processing error
