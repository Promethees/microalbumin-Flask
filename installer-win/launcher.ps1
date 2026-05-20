# launcher.ps1 — EasyOKAPI WPF splash-screen launcher
# Replaces the cmd.exe text progress bar with a native WPF window.
Add-Type -AssemblyName PresentationFramework
Add-Type -AssemblyName PresentationCore
Add-Type -AssemblyName WindowsBase

$Xaml = @'
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        Title="EasyOKAPI" Height="190" Width="480"
        WindowStartupLocation="CenterScreen"
        ResizeMode="NoResize" WindowStyle="None"
        AllowsTransparency="True" Background="Transparent">
  <Border CornerRadius="10" Background="#1E1E2E" ClipToBounds="True" Padding="36,28">
    <StackPanel VerticalAlignment="Center">

      <TextBlock Text="EasyOKAPI"
                 FontSize="22" FontWeight="SemiBold" FontFamily="Segoe UI"
                 Foreground="#CDD6F4" HorizontalAlignment="Center"/>

      <TextBlock Text="Launching, please wait..."
                 FontSize="11" FontFamily="Segoe UI" Foreground="#585B70"
                 HorizontalAlignment="Center" Margin="0,4,0,0"/>

      <Border Height="20"/>

      <!-- Progress track; ClipToBounds rounds the fill at the ends -->
      <Border Name="ProgressTrack" Height="6" CornerRadius="3"
              Background="#313244" ClipToBounds="True">
        <Border Name="ProgressFill" HorizontalAlignment="Left" Width="0">
          <Border.Background>
            <LinearGradientBrush StartPoint="0,0" EndPoint="1,0">
              <GradientStop Color="#89B4FA" Offset="0"/>
              <GradientStop Color="#CBA6F7" Offset="1"/>
            </LinearGradientBrush>
          </Border.Background>
        </Border>
      </Border>

      <Grid Margin="0,8,0,0">
        <TextBlock Name="StatusLabel"
                   FontSize="10" FontFamily="Segoe UI" Foreground="#A6ADC8"/>
        <TextBlock Name="PctLabel" Text="0%"
                   FontSize="10" FontFamily="Segoe UI" Foreground="#45475A"
                   HorizontalAlignment="Right"/>
      </Grid>

    </StackPanel>
  </Border>
</Window>
'@

$Reader  = [System.Xml.XmlReader]::Create([System.IO.StringReader]$Xaml)
$Window  = [Windows.Markup.XamlReader]::Load($Reader)
$Track   = $Window.FindName('ProgressTrack')
$Fill    = $Window.FindName('ProgressFill')
$Status  = $Window.FindName('StatusLabel')
$PctTxt  = $Window.FindName('PctLabel')

$ScriptDir = $PSScriptRoot

# Set window icon
if (Test-Path "$ScriptDir\ht.ico") {
    try {
        $Window.Icon = [System.Windows.Media.Imaging.BitmapFrame]::Create(
            [uri][System.IO.Path]::GetFullPath("$ScriptDir\ht.ico"))
    } catch {}
}

# Allow dragging the borderless window
$Window.Add_MouseLeftButtonDown({ $Window.DragMove() })

$script:Pct  = 0
$script:Done = $false

$Timer = New-Object System.Windows.Threading.DispatcherTimer
$Timer.Interval = [TimeSpan]::FromMilliseconds(18)   # ~55 fps

$Timer.Add_Tick({
    if ($script:Done) { return }
    $script:Pct++
    $p = $script:Pct

    # Stage label
    $Status.Text = switch ($true) {
        ($p -le 30) { 'Initialising environment...' }
        ($p -le 60) { 'Activating virtual environment...' }
        ($p -le 80) { 'Running preflight checks...' }
        default     { 'Launching application...' }
    }

    # Real work at stage transitions
    if ($p -eq 61) {
        if (-not (Test-Path "$ScriptDir\code\main.py")) {
            $Status.Text = 'ERROR: main.py not found in .\code\'
            $Fill.Background = [System.Windows.Media.Brushes]::IndianRed
            $Timer.Stop()
            $ct = New-Object System.Windows.Threading.DispatcherTimer
            $ct.Interval = [TimeSpan]::FromSeconds(3)
            $ct.Add_Tick({ $ct.Stop(); $Window.Close() })
            $ct.Start()
            return
        }
    } elseif ($p -eq 81) {
        $py  = "$ScriptDir\code\venv\Scripts\python.exe"
        $app = "$ScriptDir\code\main.py"
        Start-Process -FilePath $py -ArgumentList "`"$app`"" `
            -WorkingDirectory "$ScriptDir\code" -WindowStyle Hidden
    }

    # Update fill width and percentage label
    if ($Track.ActualWidth -gt 0) {
        $Fill.Width = $Track.ActualWidth * [Math]::Min($p, 100) / 100
    }
    $PctTxt.Text = "$([Math]::Min($p, 100))%"

    if ($p -ge 100) {
        $script:Done = $true
        $Timer.Stop()
        $ct = New-Object System.Windows.Threading.DispatcherTimer
        $ct.Interval = [TimeSpan]::FromMilliseconds(600)
        $ct.Add_Tick({ $ct.Stop(); $Window.Close() })
        $ct.Start()
    }
})

$Window.Add_Loaded({ $Timer.Start() })
$Window.ShowDialog() | Out-Null
