# Update all CSV files from March to April dates
Get-ChildItem -Filter '*.csv' | ForEach-Object {
    $content = Get-Content $_.FullName -Raw
    $content = $content -replace '2026-03', '2026-04'
    $content = $content -replace '2025-03', '2025-04'
    $content = $content -replace 'Mar 2026', 'Apr 2026'
    $content = $content -replace 'Mar_2025', 'Apr_2025'
    $content = $content -replace 'March', 'April'
    $content = $content -replace ',Mar,', ',Apr,'
    $content = $content -replace ' Mar ', ' Apr '
    Set-Content -Path $_.FullName -Value $content -NoNewline
    Write-Host "Updated: $($_.Name)"
}
Write-Host "All CSV files updated successfully!"

# Made with Bob
