# Update all CSV files from February to March dates
Get-ChildItem -Filter '*.csv' | ForEach-Object {
    $content = Get-Content $_.FullName -Raw
    $content = $content -replace '2026-02', '2026-03'
    $content = $content -replace '2025-02', '2025-03'
    $content = $content -replace 'Feb 2026', 'Mar 2026'
    $content = $content -replace 'Feb_2025', 'Mar_2025'
    $content = $content -replace 'February', 'March'
    $content = $content -replace ',Feb,', ',Mar,'
    $content = $content -replace ' Feb ', ' Mar '
    Set-Content -Path $_.FullName -Value $content -NoNewline
    Write-Host "Updated: $($_.Name)"
}
Write-Host "All CSV files updated successfully!"

# Made with Bob
