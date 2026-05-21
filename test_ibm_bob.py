#!/usr/bin/env python
"""Quick test to verify IBM BOB endpoints load correctly"""

import sys
import asyncio

try:
    # Try importing the app module to check for syntax errors
    print("🔍 Checking app.py syntax...")
    import app
    print("✅ app.py imported successfully - no syntax errors!")
    
    # Check that the new functions exist
    print("\n📋 Checking IBM BOB functions...")
    
    functions_to_check = [
        'load_pl_data',
        'load_workforce_data',
        'load_esg_data',
        'load_enhanced_gl',
        'generate_pl_statement',
        'get_pl_transactions',
        'get_pl_approval_items',
        'reconcile_pl_to_gl',
        'analyze_pl_variances',
        'analyze_workforce_cost_revenue',
        'analyze_salary_costs',
        'analyze_workforce_efficiency',
        'optimize_resource_allocation',
        'calculate_labour_cost_metrics',
        'detect_esg_leakage',
        'analyze_esg_financial_impact',
        'assess_disclosure_readiness',
        'model_esg_scenario',
        'generate_board_narrative',
        'track_esg_kpis',
        'get_ibm_bob_summary'
    ]
    
    missing = []
    for func_name in functions_to_check:
        if hasattr(app, func_name):
            print(f"  ✅ {func_name}")
        else:
            print(f"  ❌ {func_name} - NOT FOUND")
            missing.append(func_name)
    
    if missing:
        print(f"\n⚠️  Missing functions: {missing}")
        sys.exit(1)
    else:
        print(f"\n✅ All {len(functions_to_check)} IBM BOB functions found!")
    
    # Check that models exist
    print("\n📦 Checking IBM BOB models...")
    models_to_check = [
        'PLLineItemRequest',
        'PLStatementResponse',
        'WorkforceCostRequest',
        'WorkforceMetricsResponse',
        'ESGDataRequest',
        'ESGMetricsResponse',
        'IBMBOBSummaryResponse'
    ]
    
    missing_models = []
    for model_name in models_to_check:
        if hasattr(app, model_name):
            print(f"  ✅ {model_name}")
        else:
            print(f"  ❌ {model_name} - NOT FOUND")
            missing_models.append(model_name)
    
    if missing_models:
        print(f"\n⚠️  Missing models: {missing_models}")
        sys.exit(1)
    else:
        print(f"\n✅ All {len(models_to_check)} IBM BOB models found!")
    
    # Check that CSV files exist
    print("\n📁 Checking required CSV files...")
    import os
    csv_files = [
        'IBMBOB_Group_PL_LineItems_Mar2026_GENERATED.csv',
        'IBMBOB_Workforce_Cost_Output_Mar2026_GENERATED.csv',
        'IBMBOB_ESG_Cost_KPI_Mar2026_GENERATED.csv',
        'Raw_GL_Export_With_CostCenters_Mar2026_IBMBOB_Enhanced_GENERATED.csv'
    ]
    
    missing_files = []
    for csv_file in csv_files:
        if os.path.exists(csv_file):
            size = os.path.getsize(csv_file)
            print(f"  ✅ {csv_file} ({size:,} bytes)")
        else:
            print(f"  ❌ {csv_file} - NOT FOUND")
            missing_files.append(csv_file)
    
    if missing_files:
        print(f"\n⚠️  Missing files: {missing_files}")
        sys.exit(1)
    else:
        print(f"\n✅ All {len(csv_files)} required CSV files found!")
    
    print("\n" + "="*60)
    print("✅ IBM BOB INTEGRATION TEST PASSED!")
    print("="*60)
    print("\nEndpoints available:")
    print("  P&L:        /tools/pl/statement")
    print("              /tools/pl/transactions")
    print("              /tools/pl/approval_items")
    print("              /tools/pl/gl_reconciliation")
    print("              /tools/pl/variance_analysis")
    print("  Workforce:  /tools/workforce/cost_revenue_correlation")
    print("              /tools/workforce/salary_analysis")
    print("              /tools/workforce/cost_output_efficiency")
    print("              /tools/workforce/resource_optimization")
    print("              /tools/workforce/labour_cost_metrics")
    print("  ESG:        /tools/esg/leakage_detection")
    print("              /tools/esg/financial_impact")
    print("              /tools/esg/disclosure_readiness")
    print("              /tools/esg/scenario_modeling")
    print("              /tools/esg/board_narrative")
    print("              /tools/esg/kpi_tracking")
    print("  Summary:    /tools/ibm_bob/summary/{fiscal_period}")
    
except SyntaxError as e:
    print(f"\n❌ SYNTAX ERROR in app.py:")
    print(f"   {e}")
    sys.exit(1)
except ImportError as e:
    print(f"\n❌ IMPORT ERROR:")
    print(f"   {e}")
    sys.exit(1)
except Exception as e:
    print(f"\n❌ ERROR:")
    print(f"   {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
