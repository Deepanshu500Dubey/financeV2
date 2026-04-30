# Script to update remaining February date references in CSV files

$csvFiles = Get-ChildItem -Path "." -Filter "*_Mar2026.csv"

foreach ($file in $csvFiles) {
    Write-Host "Processing: $($file.Name)"
    
    $content = Get-Content $file.FullName -Raw
    
    # Update various date formats from February to March
    # Format: DD-MM-YYYY or DD/MM/YYYY
    $content = $content -replace '(\d{1,2})[-/]02[-/](2026)', '$1-03-$2'
    
    # Format: MM/DD/YYYY (American format) - February to March
    $content = $content -replace '02/(\d{1,2})/(2026)', '03/$1/$2'
    
    # Format: YYYY-MM-DD
    $content = $content -replace '(2026)-02-(\d{1,2})', '$1-03-$2'
    
    # Update February 2025 comparative dates to March 2025
    $content = $content -replace '(\d{1,2})[-/]02[-/](2025)', '$1-03-$2'
    $content = $content -replace '02/(\d{1,2})/(2025)', '03/$1/$2'
    $content = $content -replace '(2025)-02-(\d{1,2})', '$1-03-$2'
    
    # Update text references
    $content = $content -replace '\bFeb\b', 'Mar'
    $content = $content -replace '\bFebruary\b', 'March'
    $content = $content -replace '\bFeb_2025\b', 'Mar_2025'
    $content = $content -replace '\bFeb_2026\b', 'Mar_2026'
    
    # Update column headers if they exist
    $content = $content -replace 'Feb_2025_Actual', 'Mar_2025_Actual'
    $content = $content -replace 'Feb_2026_Actual', 'Mar_2026_Actual'
    
    # Save the updated content
    Set-Content -Path $file.FullName -Value $content -NoNewline
    
    Write-Host "Updated: $($file.Name)"
}

Write-Host "`nAll remaining February dates updated to March!"

# Made with Bob
