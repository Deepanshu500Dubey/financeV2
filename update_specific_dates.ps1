# Update specific date patterns for March (31 days vs February's 28/29)
Get-ChildItem -Filter '*Mar2026*.csv' | ForEach-Object {
    $content = Get-Content $_.FullName -Raw
    
    # Update month-end dates from Feb 29 to Mar 31
    $content = $content -replace '2026-03-29', '2026-03-31'
    $content = $content -replace '2026-03-28', '2026-03-31'
    
    # Update due dates that were in March (now should be in April)
    # Pattern: dates like 2026-03-01 through 2026-03-31 in due date contexts
    # We need to shift March due dates to April
    $content = $content -replace '2026-03-01,', '2026-04-01,'
    $content = $content -replace '2026-03-02,', '2026-04-02,'
    $content = $content -replace '2026-03-03,', '2026-04-03,'
    $content = $content -replace '2026-03-04,', '2026-04-04,'
    $content = $content -replace '2026-03-05,', '2026-04-05,'
    $content = $content -replace '2026-03-06,', '2026-04-06,'
    $content = $content -replace '2026-03-07,', '2026-04-07,'
    $content = $content -replace '2026-03-08,', '2026-04-08,'
    $content = $content -replace '2026-03-09,', '2026-04-09,'
    $content = $content -replace '2026-03-10,', '2026-04-10,'
    $content = $content -replace '2026-03-11,', '2026-04-11,'
    $content = $content -replace '2026-03-12,', '2026-04-12,'
    $content = $content -replace '2026-03-13,', '2026-04-13,'
    $content = $content -replace '2026-03-14,', '2026-04-14,'
    $content = $content -replace '2026-03-15,', '2026-04-15,'
    $content = $content -replace '2026-03-16,', '2026-04-16,'
    $content = $content -replace '2026-03-17,', '2026-04-17,'
    $content = $content -replace '2026-03-18,', '2026-04-18,'
    $content = $content -replace '2026-03-19,', '2026-04-19,'
    $content = $content -replace '2026-03-20,', '2026-04-20,'
    $content = $content -replace '2026-03-21,', '2026-04-21,'
    $content = $content -replace '2026-03-22,', '2026-04-22,'
    $content = $content -replace '2026-03-23,', '2026-04-23,'
    $content = $content -replace '2026-03-24,', '2026-04-24,'
    $content = $content -replace '2026-03-25,', '2026-04-25,'
    $content = $content -replace '2026-03-26,', '2026-04-26,'
    $content = $content -replace '2026-03-27,', '2026-04-27,'
    $content = $content -replace '2026-03-28,', '2026-04-28,'
    
    # Update descriptions mentioning "Mar 2026" to be consistent
    $content = $content -replace 'Mar 2026', 'Mar 2026'
    $content = $content -replace '- Mar 2026', '- Mar 2026'
    
    Set-Content -Path $_.FullName -Value $content -NoNewline
    Write-Host "Updated specific dates in: $($_.Name)"
}
Write-Host "Specific date updates completed!"

# Made with Bob
