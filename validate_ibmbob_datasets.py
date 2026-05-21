#!/usr/bin/env python3
"""
Validate IBM BOB CSV datasets: file presence, column headers, and sample data types.

Run from the project root:
    python validate_ibmbob_datasets.py
"""

from __future__ import annotations

import csv
import os
import sys
from typing import Any, Dict, List, Tuple

IBMBOB_DATA_FILES = {
    'pl': (
        'IBMBOB_Group_PL_LineItems_Mar2026.csv',
        'IBMBOB_Group_PL_LineItems_Mar2026_GENERATED.csv',
    ),
    'workforce': (
        'IBMBOB_Workforce_Cost_Output_Mar2026.csv',
        'IBMBOB_Workforce_Cost_Output_Mar2026_GENERATED.csv',
    ),
    'esg': (
        'IBMBOB_ESG_Cost_KPI_Mar2026.csv',
        'IBMBOB_ESG_Cost_KPI_Mar2026_GENERATED.csv',
    ),
    'enhanced_gl': (
        'Raw_GL_Export_With_CostCenters_Mar2026_IBMBOB_Enhanced.csv',
        'Raw_GL_Export_With_CostCenters_Mar2026_IBMBOB_Enhanced_GENERATED.csv',
    ),
}

REQUIRED_COLUMNS = {
    'pl': [
        'Txn_ID', 'Account_Code', 'P_L_Section', 'P_L_Line_Item', 'Category',
        'Amount_AUD', 'Close_Readiness_Flag', 'Anomaly_Flag', 'Approval_Required', 'Fiscal_Period',
    ],
    'workforce': [
        'Employee_ID', 'Business_Unit', 'Department', 'Role', 'Salary_AUD', 'Overtime_AUD',
        'Benefits_AUD', 'Contractor_Cost_AUD', 'Total_Workforce_Cost_AUD', 'Hours_Worked',
        'Utilisation_Percent', 'Output_Volume', 'Revenue_or_Value_Supported_AUD',
        'Labour_Cost_Per_Output', 'Risk_Flag', 'Recommended_Action', 'Fiscal_Period',
    ],
    'esg': [
        'ESG_Record_ID', 'ESG_Category', 'Spend_AUD', 'Sustainability_KPI', 'KPI_Target',
        'KPI_Actual', 'KPI_Attainment_Percent', 'Carbon_tCO2e', 'Renewable_Source_Percent',
        'Supplier_ESG_Score', 'Working_Capital_Impact_AUD', 'Margin_Impact_Points',
        'Misclassification_Flag', 'Leakage_Flag', 'Disclosure_Evidence_Status',
        'Audit_Readiness', 'Approval_Required', 'Fiscal_Period',
    ],
    'enhanced_gl': [
        'Txn_ID', 'Posting_Date_Raw', 'Fiscal_Period', 'Entity', 'Account_Code_Raw',
        'Cost_Center', 'Vendor_Name_Raw', 'Invoice_Number', 'PO_Number', 'Currency',
        'Amount', 'Tax_Code', 'Narrative', 'Source_System',
    ],
}

NUMERIC_COLUMNS = {
    'pl': ['Amount_AUD'],
    'workforce': [
        'Salary_AUD', 'Overtime_AUD', 'Benefits_AUD', 'Contractor_Cost_AUD',
        'Total_Workforce_Cost_AUD', 'Hours_Worked', 'Utilisation_Percent', 'Output_Volume',
        'Revenue_or_Value_Supported_AUD', 'Labour_Cost_Per_Output',
    ],
    'esg': [
        'Spend_AUD', 'KPI_Target', 'KPI_Actual', 'KPI_Attainment_Percent', 'Carbon_tCO2e',
        'Renewable_Source_Percent', 'Supplier_ESG_Score', 'Working_Capital_Impact_AUD',
        'Margin_Impact_Points',
    ],
    'enhanced_gl': ['Amount'],
}

FISCAL_PERIOD_SAMPLE = '2026-03'
SAMPLE_ROWS = 25


def normalize_header(name: str) -> str:
    return name.strip().lstrip('\ufeff')


def resolve_file(dataset_key: str) -> Tuple[str, bool]:
    preferred, fallback = IBMBOB_DATA_FILES[dataset_key]
    if os.path.exists(preferred):
        return preferred, False
    if os.path.exists(fallback):
        return fallback, True
    return preferred, False


def parse_float(value: Any) -> float:
    if value is None or value == '':
        raise ValueError('empty value')
    text = str(value).strip().replace('%', '').replace(',', '')
    return float(text)


def load_rows(filename: str) -> Tuple[List[str], List[Dict[str, str]]]:
    with open(filename, 'r', encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            return [], []
        headers = [normalize_header(h) for h in reader.fieldnames]
        rows = [{normalize_header(k): v for k, v in row.items()} for row in reader]
    return headers, rows


def validate_dataset(dataset_key: str) -> List[str]:
    errors: List[str] = []
    filename, used_fallback = resolve_file(dataset_key)
    label = dataset_key.upper()

    if not os.path.exists(filename):
        preferred, fallback = IBMBOB_DATA_FILES[dataset_key]
        errors.append(f"[{label}] Missing files: {preferred} and {fallback}")
        return errors

    if used_fallback:
        print(f"[{label}] WARN: using fallback file {filename}")

    headers, rows = load_rows(filename)
    if not headers:
        errors.append(f"[{label}] {filename}: no header row")
        return errors

    header_set = set(headers)
    missing = [c for c in REQUIRED_COLUMNS[dataset_key] if c not in header_set]
    if missing:
        errors.append(f"[{label}] {filename}: missing columns {missing}")

    if not rows:
        errors.append(f"[{label}] {filename}: no data rows")
        return errors

    period_rows = [r for r in rows if r.get('Fiscal_Period') == FISCAL_PERIOD_SAMPLE]
    print(
        f"[{label}] OK file={filename} rows={len(rows)} "
        f"fiscal_period_{FISCAL_PERIOD_SAMPLE}={len(period_rows)}"
    )

    sample = rows[:SAMPLE_ROWS]
    for col in NUMERIC_COLUMNS.get(dataset_key, []):
        if col not in header_set:
            continue
        bad = []
        for row in sample:
            val = row.get(col)
            if val is None or val == '':
                continue
            try:
                parse_float(val)
            except ValueError:
                bad.append(val)
        if bad:
            errors.append(
                f"[{label}] {filename}: non-numeric values in {col} (sample): {bad[:5]}"
            )

    if dataset_key == 'workforce':
        for row in sample:
            val = row.get('Utilisation_Percent')
            if val:
                try:
                    parse_float(val)
                except ValueError:
                    errors.append(f"[{label}] invalid Utilisation_Percent: {val!r}")

    if dataset_key == 'pl' and period_rows:
        txn_ids = {r.get('Txn_ID') for r in period_rows if r.get('Txn_ID')}
        print(f"[{label}] sample Txn_ID count for {FISCAL_PERIOD_SAMPLE}: {len(txn_ids)}")

    return errors


def validate_gl_pl_link() -> List[str]:
    errors: List[str] = []
    pl_file, _ = resolve_file('pl')
    gl_file, _ = resolve_file('enhanced_gl')
    if not os.path.exists(pl_file) or not os.path.exists(gl_file):
        return errors

    _, pl_rows = load_rows(pl_file)
    _, gl_rows = load_rows(gl_file)
    pl_ids = {r['Txn_ID'] for r in pl_rows if r.get('Fiscal_Period') == FISCAL_PERIOD_SAMPLE and r.get('Txn_ID')}
    gl_ids = {r['Txn_ID'] for r in gl_rows if r.get('Fiscal_Period') == FISCAL_PERIOD_SAMPLE and r.get('Txn_ID')}
    overlap = pl_ids & gl_ids
    print(f"[LINK] P&L Txn_IDs in GL for {FISCAL_PERIOD_SAMPLE}: {len(overlap)}/{len(pl_ids)}")
    if pl_ids and len(overlap) == 0:
        errors.append(
            f"[LINK] No overlapping Txn_ID between {pl_file} and {gl_file} for {FISCAL_PERIOD_SAMPLE}"
        )
    return errors


def main() -> int:
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    print(f"Validating IBM BOB datasets in {os.getcwd()}\n")

    all_errors: List[str] = []
    for key in ('pl', 'workforce', 'esg', 'enhanced_gl'):
        all_errors.extend(validate_dataset(key))
    all_errors.extend(validate_gl_pl_link())

    print()
    if all_errors:
        print("VALIDATION FAILED:")
        for err in all_errors:
            print(f"  - {err}")
        return 1

    print("VALIDATION PASSED: all IBM BOB files, columns, and sample types look correct.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
