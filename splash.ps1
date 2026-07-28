# splash.ps1 - Helix Core first-launch splash screen
# Shown by the NSIS launcher during first-time extraction.
# Polls for a signal file and closes when it appears (or after timeout).

param(
    [string]$IconPath = "",
    [string]$DoneFile = (Join-Path $env:TEMP "helix_splash_done")
)

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

# --- Borderless dark window ---
$form = New-Object System.Windows.Forms.Form
$form.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::None
$form.StartPosition   = [System.Windows.Forms.FormStartPosition]::CenterScreen
$form.Size            = New-Object System.Drawing.Size(440, 240)
$form.BackColor       = [System.Drawing.ColorTranslator]::FromHtml('#0f1724')
$form.TopMost         = $true
$form.ShowInTaskbar   = $false

# --- App icon (48x48, centered) ---
if ($IconPath -and (Test-Path $IconPath)) {
    $img = [System.Drawing.Image]::FromFile($IconPath)
    $pic = New-Object System.Windows.Forms.PictureBox
    $pic.Image    = $img
    $pic.SizeMode = [System.Windows.Forms.PictureBoxSizeMode]::Zoom
    $pic.Size     = New-Object System.Drawing.Size(48, 48)
    $pic.Location = New-Object System.Drawing.Point(196, 28)
    $pic.BackColor = [System.Drawing.Color]::Transparent
    $form.Controls.Add($pic)
}

# --- Title ---
$title = New-Object System.Windows.Forms.Label
$title.Text      = "Preparing Helix Core..."
$title.ForeColor = [System.Drawing.Color]::White
$title.Font      = New-Object System.Drawing.Font("Segoe UI", 16)
$title.AutoSize  = $false
$title.Size      = New-Object System.Drawing.Size(440, 32)
$title.TextAlign = [System.Drawing.ContentAlignment]::MiddleCenter
$title.Location  = New-Object System.Drawing.Point(0, 92)
$form.Controls.Add($title)

# --- Subtitle ---
$sub = New-Object System.Windows.Forms.Label
$sub.Text      = "First-time setup - extracting application files..."
$sub.ForeColor = [System.Drawing.ColorTranslator]::FromHtml('#6b7d93')
$sub.Font      = New-Object System.Drawing.Font("Segoe UI", 10)
$sub.AutoSize  = $false
$sub.Size      = New-Object System.Drawing.Size(440, 24)
$sub.TextAlign = [System.Drawing.ContentAlignment]::MiddleCenter
$sub.Location  = New-Object System.Drawing.Point(0, 132)
$form.Controls.Add($sub)

# --- Spinning arc (custom drawn) ---
$spinner = New-Object System.Windows.Forms.PictureBox
$spinner.Size     = New-Object System.Drawing.Size(40, 40)
$spinner.Location = New-Object System.Drawing.Point(200, 170)
$spinner.BackColor = [System.Drawing.Color]::Transparent
$form.Controls.Add($spinner)

$script:angle = 0
$spinTimer = New-Object System.Windows.Forms.Timer
$spinTimer.Interval = 30
$spinTimer.Add_Tick({
    $script:angle = ($script:angle + 8) % 360
    $bmp = New-Object System.Drawing.Bitmap(40, 40)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $pen = New-Object System.Drawing.Pen([System.Drawing.ColorTranslator]::FromHtml('#3b82f6'), 3)
    $pen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
    $pen.EndCap   = [System.Drawing.Drawing2D.LineCap]::Round
    $g.DrawArc($pen, 4, 4, 32, 32, $script:angle, 90)
    $g.Dispose(); $pen.Dispose()
    $old = $spinner.Image
    $spinner.Image = $bmp
    if ($old) { $old.Dispose() }
})
$spinTimer.Start()

# --- Poll timer: close when signal file appears or timeout ---
$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 400
$script:t0 = [DateTime]::Now
$timer.Add_Tick({
    if (Test-Path $DoneFile) {
        $timer.Stop()
        $form.Close()
    }
    if (([DateTime]::Now - $script:t0).TotalSeconds -gt 300) {
        $timer.Stop()
        $form.Close()
    }
})
$timer.Start()

# --- Run event loop (blocks until form closes) ---
[System.Windows.Forms.Application]::Run($form)

# --- Cleanup ---
Remove-Item $DoneFile -ErrorAction SilentlyContinue
