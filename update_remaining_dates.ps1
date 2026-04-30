# Script to update remaining March date references in CSV files

$csvFiles = Get-ChildItem -Path "." -Filter "*_Apr2026.csv"

foreach ($file in $csvFiles) {
    Write-Host "Processing: $($file.Name)"
    
    $content = Get-Content $file.FullName -Raw
    
    # Update various date formats from March to April
    # Format: DD-MM-YYYY or DD/MM/YYYY
    $content = $content -replace '(\d{1,2})[-/]03[-/](2026)', '$1-04-$2'
    
    # Format: MM/DD/YYYY (American format) - March to April
    $content = $content -replace '03/(\d{1,2})/(2026)', '04/$1/$2'
    
    # Format: YYYY-MM-DD
    $content = $content -replace '(2026)-03-(\d{1,2})', '$1-04-$2'
    
    # Update March 2025 comparative dates to April 2025
    $content = $content -replace '(\d{1,2})[-/]03[-/](2025)', '$1-04-$2'
    $content = $content -replace '03/(\d{1,2})/(2025)', '04/$1/$2'
    $content = $content -replace '(2025)-03-(\d{1,2})', '$1-04-$2'
    
    # Update text references
    $content = $content -replace '\bMar\b', 'Apr'
    $content = $content -replace '\bMarch\b', 'April'
    $content = $content -replace '\bMar_2025\b', 'Apr_2025'
    $content = $content -replace '\bMar_2026\b', 'Apr_2026'
    
    # Update column headers if they exist
    $content = $content -replace 'Mar_2025_Actual', 'Apr_2025_Actual'
    $content = $content -replace 'Mar_2026_Actual', 'Apr_2026_Actual'
    
    # Save the updated content
    Set-Content -Path $file.FullName -Value $content -NoNewline
    
    Write-Host "Updated: $($file.Name)"
}

Write-Host "`nAll remaining March dates updated to April!"

# Made with Bob