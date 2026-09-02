# Unify all HTML files to use only conversapay-ui.css
# This script processes all HTML files in the project

param()

$ErrorActionPreference = 'Stop'
$basePath = 'c:\Users\buxat\Talk2Pay Project'
$cssPath = Join-Path $basePath 'frontend\css\main.css'
$htmlFiles = Get-ChildItem -Path $basePath -Recurse -Filter *.html | Select-Object -ExpandProperty FullName

Write-Host "=== HTML Unification Script ===" -ForegroundColor Cyan
Write-Host "Found $($htmlFiles.Count) HTML files`n"

# Read current main.css
$mainCss = Get-Content -Path $cssPath -Raw

# Track all new classes we need to add
$newClasses = @()

function Add-Class-To-MainCss {
    param(
        [string]$ClassName,
        [string]$Styles
    )
    
    if ($mainCss -notmatch "\.$ClassName\s*\{") {
        $newClasses += $ClassName
        Write-Host "  [ADD TO main.css] .$ClassName" -ForegroundColor Yellow
    }
}

# Process each HTML file
foreach ($file in $htmlFiles) {
    $relativePath = $file.Substring($basePath.Length + 1)
    Write-Host "Processing: $relativePath" -ForegroundColor Green
    
    $content = Get-Content -Path $file -Raw
    $originalContent = $content
    $changes = @()
    
    # 1. Ensure conversapay-ui.css link exists
    if ($content -notmatch 'conversapay-ui\.css') {
        # Add it after the charset/viewport meta tags
        if ($content -match '(<meta[^>]*viewport[^>]*>)') {
            $content = $content -replace '(<meta[^>]*viewport[^>]*>)', "`$1`n  <link rel=`"stylesheet`" href=`"/frontend/html/conversapay-ui.css`">"
            $changes += "Added conversapay-ui.css link"
        }
    }
    
    # 2. Remove old CSS links (keep only conversapay-ui.css and third-party libs)
    if ($content -match '<link[^>]*rel="stylesheet"[^>]*>') {
        $oldLinks = [regex]::Matches($content, '<link[^>]*rel="stylesheet"[^>]*>')
        foreach ($link in $oldLinks) {
            $linkText = $link.Value
            if ($linkText -notmatch 'conversapay-ui\.css|fonts\.googleapis|fonts\.gstatic|cdn\.jsdelivr|saas-overrides') {
                $content = $content -replace [regex]::Escape($linkText), ''
                $changes += "Removed old CSS link: $linkText"
            }
        }
    }
    
    # 3. Remove all <style> blocks
    $styleBlockCount = ([regex]::Matches($content, '<style[^>]*>.*?</style>', 'Singleline')).Count
    if ($styleBlockCount -gt 0) {
        $content = [regex]::Replace($content, '<style[^>]*>.*?</style>', '', 'Singleline')
        $changes += "Removed $styleBlockCount style block(s)"
    }
    
    # 4. Remove all inline style attributes
    $inlineStyleCount = ([regex]::Matches($content, 'style="[^"]*"')).Count
    if ($inlineStyleCount -gt 0) {
        $content = [regex]::Replace($content, 'style="[^"]*"', '', 'Singleline')
        $changes += "Removed $inlineStyleCount inline style attribute(s)"
    }
    
    # 5. Clean up extra whitespace
    $content = $content -replace '\n\s*\n\s*\n', "`n`n"
    
    # Save if changed
    if ($content -ne $originalContent) {
        Set-Content -Path $file -Value $content -Encoding UTF8
        Write-Host "  Changes:" -ForegroundColor Cyan
        foreach ($change in $changes) {
            Write-Host "    - $change"
        }
    } else {
        Write-Host "  No changes needed" -ForegroundColor Gray
    }
}

Write-Host "`n=== Summary ===" -ForegroundColor Cyan
Write-Host "Files processed: $($htmlFiles.Count)"
if ($newClasses.Count -gt 0) {
    Write-Host "`nNew classes to add to main.css:" -ForegroundColor Yellow
    $newClasses | ForEach-Object { Write-Host "  - .$_" }
} else {
    Write-Host "No new classes needed"
}
