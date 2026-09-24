# launcher-frozen.ps1 - EasyOKAPI splash launcher for the no-source (PyInstaller) build.
#
# Shows a small "Starting EasyOKAPI" window with a progress bar while the bundled
# EasyOKAPI.exe starts up, then closes once the app is ready (the app opens your
# web browser itself). If EasyOKAPI is already running, this just reopens it in
# your browser instead of starting a second copy.
#
# The Desktop / Start Menu shortcuts run this hidden via:
#   powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File launcher-frozen.ps1

Add-Type -AssemblyName PresentationFramework
Add-Type -AssemblyName PresentationCore
Add-Type -AssemblyName WindowsBase

$script:ScriptDir = if ($PSScriptRoot) { $PSScriptRoot } else {
    Split-Path -Parent $MyInvocation.MyCommand.Path
}
$script:Exe  = Join-Path $script:ScriptDir 'EasyOKAPI.exe'
$script:Port = 5099
# The installer adds a hosts entry (127.0.0.1 -> easyokapi.com) so the app can be
# opened at this friendly address. The server still binds to 127.0.0.1.
$script:Url  = "http://easyokapi.com:$($script:Port)"

function Test-Listening {
    try {
        $c = New-Object System.Net.Sockets.TcpClient
        $c.Connect('127.0.0.1', $script:Port); $c.Close(); return $true
    } catch { return $false }
}

# Already running? Just reopen it in the browser - never start a second copy.
if (Test-Listening) { Start-Process $script:Url; return }

# ── Which splash to show ─────────────────────────────────────────────────────
# The app can wear either of two interface styles (the `ui_style` setting), and
# the splash is the first thing the user sees, so it has to agree with the window
# that opens behind it. Read the setting the same way the app resolves it, and
# fall back to the instrument style on any problem — a splash must never be the
# reason a launch fails.
#
# user_settings.json lives INSIDE the data root, which the user can relocate
# (Rule.md 2.19): the pointer file `.easyokapi_dataroot` sits beside the default
# folder and holds one absolute path when they have moved it.
function Get-UiStyle {
    try {
        $docs = [Environment]::GetFolderPath('MyDocuments')
        if (-not $docs) { return 'instrument' }

        $root    = Join-Path $docs 'EasyOKAPI'
        $pointer = Join-Path $docs '.easyokapi_dataroot'
        if (Test-Path $pointer) {
            # ReadAllText honours the BOM (UTF-16LE from the installer/app) and
            # defaults to UTF-8; Get-Content would read a BOM-less file as ANSI.
            $moved = [System.IO.File]::ReadAllText($pointer).Trim()
            if ($moved -and [System.IO.Path]::IsPathRooted($moved)) { $root = $moved }
        }

        $settings = Join-Path $root 'user_settings.json'
        if (-not (Test-Path $settings)) { return 'instrument' }

        $style = (Get-Content -LiteralPath $settings -Raw -ErrorAction Stop |
                  ConvertFrom-Json).ui_style
        if ($style -eq 'classic') { return 'classic' }
        return 'instrument'
    } catch { return 'instrument' }
}

# Classic: the pre-1.4.0 splash, unchanged — indigo card, gradient progress fill.
$XamlClassic = @'
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        Title="EasyOKAPI" Height="190" Width="480"
        WindowStartupLocation="CenterScreen"
        ResizeMode="NoResize" WindowStyle="None"
        AllowsTransparency="True" Background="Transparent">
  <Border CornerRadius="10" Background="#1E1B4B" ClipToBounds="True" Padding="36,28">
    <StackPanel VerticalAlignment="Center">
      <TextBlock Text="EasyOKAPI"
                 FontSize="22" FontWeight="SemiBold" FontFamily="Segoe UI"
                 Foreground="#E2E8F0" HorizontalAlignment="Center"/>
      <TextBlock Text="Starting up, please wait..."
                 FontSize="11" FontFamily="Segoe UI" Foreground="#A5B4FC"
                 HorizontalAlignment="Center" Margin="0,4,0,0"/>
      <Border Height="20"/>
      <Border Name="ProgressTrack" Height="6" CornerRadius="3"
              Background="#312E81" ClipToBounds="True">
        <Border Name="ProgressFill" HorizontalAlignment="Left" Width="0">
          <Border.Background>
            <LinearGradientBrush StartPoint="0,0" EndPoint="1,0">
              <GradientStop Color="#818CF8" Offset="0"/>
              <GradientStop Color="#C4B5FD" Offset="1"/>
            </LinearGradientBrush>
          </Border.Background>
        </Border>
      </Border>
      <Grid Margin="0,8,0,0">
        <TextBlock Name="StatusLabel"
                   FontSize="10" FontFamily="Segoe UI" Foreground="#A6ADC8"/>
        <TextBlock Name="PctLabel" Text="0%"
                   FontSize="10" FontFamily="Segoe UI" Foreground="#6366F1"
                   HorizontalAlignment="Right"/>
      </Grid>
    </StackPanel>
  </Border>
</Window>
'@

# Instrument: the same tokens as the app (style.css) — graphite card on a hairline
# border, bromophenol-blue accent, 4px radius, a flat progress fill rather than a
# gradient, and the percentage in a mono face because it is a number that counts up.
$XamlInstrument = @'
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        Title="EasyOKAPI" Height="190" Width="480"
        WindowStartupLocation="CenterScreen"
        ResizeMode="NoResize" WindowStyle="None"
        AllowsTransparency="True" Background="Transparent">
  <Border CornerRadius="4" Background="#0E1113" BorderBrush="#262C31" BorderThickness="1"
          ClipToBounds="True" Padding="36,28">
    <StackPanel VerticalAlignment="Center">
      <TextBlock FontSize="22" FontWeight="SemiBold" FontFamily="Segoe UI"
                 HorizontalAlignment="Center">
        <Run Text="Easy" Foreground="#2E8FC4"/><Run Text="OKAPI" Foreground="#E6EAEC"/>
      </TextBlock>
      <TextBlock Text="STARTING UP"
                 FontSize="10" FontFamily="Segoe UI Semibold" Foreground="#8A959B"
                 HorizontalAlignment="Center" Margin="0,6,0,0"/>
      <Border Height="20"/>
      <Border Name="ProgressTrack" Height="4" CornerRadius="0"
              Background="#262C31" ClipToBounds="True">
        <Border Name="ProgressFill" HorizontalAlignment="Left" Width="0"
                Background="#2E8FC4"/>
      </Border>
      <Grid Margin="0,8,0,0">
        <TextBlock Name="StatusLabel"
                   FontSize="10" FontFamily="Segoe UI" Foreground="#5D666B"/>
        <TextBlock Name="PctLabel" Text="0%"
                   FontSize="10" FontFamily="Cascadia Mono, Consolas, Courier New"
                   Foreground="#2E8FC4" HorizontalAlignment="Right"/>
      </Grid>
    </StackPanel>
  </Border>
</Window>
'@

$Xaml = if ((Get-UiStyle) -eq 'classic') { $XamlClassic } else { $XamlInstrument }

$Reader = [System.Xml.XmlReader]::Create([System.IO.StringReader]$Xaml)
$Window = [Windows.Markup.XamlReader]::Load($Reader)
$Track  = $Window.FindName('ProgressTrack')
$Fill   = $Window.FindName('ProgressFill')
$Status = $Window.FindName('StatusLabel')
$PctTxt = $Window.FindName('PctLabel')

# Window icon (bundled inside _internal\static\ht.ico); ignored if missing.
$ico = Join-Path $script:ScriptDir '_internal\static\ht.ico'
if (Test-Path $ico) {
    try {
        $Window.Icon = [System.Windows.Media.Imaging.BitmapFrame]::Create(
            [uri][System.IO.Path]::GetFullPath($ico))
    } catch {}
}

# Let the user drag the borderless window.
$Window.Add_MouseLeftButtonDown({ $Window.DragMove() })

$script:Pct   = 0
$script:Ticks = 0
$script:Done  = $false

function Close-Soon($ms) {
    $script:Done = $true
    $ct = New-Object System.Windows.Threading.DispatcherTimer
    $ct.Interval = [TimeSpan]::FromMilliseconds($ms)
    $ct.Add_Tick({ $ct.Stop(); $Window.Close() })
    $ct.Start()
}

$Timer = New-Object System.Windows.Threading.DispatcherTimer
$Timer.Interval = [TimeSpan]::FromMilliseconds(60)

$Timer.Add_Tick({
    if ($script:Done) { return }
    $script:Ticks++

    # Fill quickly to 90%, then wait there until the app answers on its port.
    if ($script:Pct -lt 90) {
        $script:Pct += 3
    } elseif (Test-Listening) {
        $script:Pct = [Math]::Min($script:Pct + 5, 100)
    }
    $p = $script:Pct

    $Status.Text = switch ($true) {
        ($p -le 45) { 'Starting EasyOKAPI...' }
        ($p -lt 100) { 'Preparing your workspace...' }
        default     { 'Opening EasyOKAPI in your browser...' }
    }
    if ($Track.ActualWidth -gt 0) {
        $Fill.Width = $Track.ActualWidth * [Math]::Min($p, 100) / 100
    }
    $PctTxt.Text = "$([Math]::Min($p, 100))%"

    if ($p -ge 100) {
        $Timer.Stop(); Close-Soon 500
    } elseif ($script:Ticks -ge 1000) {
        # ~60s and the app still has not answered - close the splash and let the
        # user check on it rather than spinning forever.
        $Timer.Stop(); Close-Soon 200
    }
})

# Start the bundled app (hidden); it opens the browser itself once ready.
$Window.Add_Loaded({
    try {
        Start-Process -FilePath $script:Exe `
            -ArgumentList '--port', '5099', '--alias', 'easyokapi.com' `
            -WorkingDirectory $script:ScriptDir `
            -WindowStyle Hidden -ErrorAction Stop
        $Timer.Start()
    } catch {
        $Status.Text = 'Could not start EasyOKAPI. Please reinstall it.'
        $Fill.Background = [System.Windows.Media.Brushes]::IndianRed
        Close-Soon 5000
    }
})

$Window.ShowDialog() | Out-Null
