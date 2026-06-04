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
$script:Url  = "http://127.0.0.1:$($script:Port)"

function Test-Listening {
    try {
        $c = New-Object System.Net.Sockets.TcpClient
        $c.Connect('127.0.0.1', $script:Port); $c.Close(); return $true
    } catch { return $false }
}

# Already running? Just reopen it in the browser - never start a second copy.
if (Test-Listening) { Start-Process $script:Url; return }

$Xaml = @'
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
            -ArgumentList '--port', '5099', '--alias', '127.0.0.1' `
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
