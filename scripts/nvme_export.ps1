$ErrorActionPreference = 'SilentlyContinue'
$out = Join-Path $PSScriptRoot 'dash'
New-Item -ItemType Directory -Force $out | Out-Null
$l = 'Microsoft-Windows-Storage-Storport/Operational'
function D($e) { $h = @{}; ([xml]$e.ToXml()).Event.EventData.Data | ForEach-Object { $h[$_.Name] = $_.'#text' }; $h }
function N($v) { if ($v -match '^\d+$') { [int64]$v } else { 0 } }
# диски по AdapterGuid (стабилен у обоих NVMe), с подстраховкой по серийнику
function Disk($d) {
    if ($d.MiniportName -ne 'stornvme') { return $null }
    switch ($d.AdapterGuid) { '{1ac9d5c6-fe14-11ee-94ea-806e6f6e6963}' { return 'C' } '{1ac9d5c7-fe14-11ee-94ea-806e6f6e6963}' { return 'D' } }
    if ($d.SerialNumber -like '6479*') { return 'C' }; if ($d.SerialNumber -like '0000*') { return 'D' }; $null
}

$inc = foreach ($e in Get-WinEvent -FilterHashtable @{LogName = $l; Id = 524, 549, 557 }) {
    $d = D $e; $disk = Disk $d; if (-not $disk) { continue }
    $type = $null; $detail = ''
    switch ($e.Id) {
        524 { if ($d.MiniportEventDescription -match 'Timeout') { $type = 'admin_timeout' } }
        549 { $sk = N $d.SenseKey; $srb = N $d.SrbStatus; $cmd = '0x{0:X2}' -f (N $d.Command)
              if ($sk -in 3, 4) { $type = 'write_error'; $detail = "SenseKey $sk, ASC 0x{0:X2}, команда $cmd" -f (N $d.AddSense) }
              elseif ($srb -eq 14) { $type = 'reset'; $detail = "запрос $cmd ждал $([math]::Round((N $d.RequestDuration_ms)/1000)) с, затем сброс" } }
        557 { $rd = N $d.RequestDuration_ms; if ($rd -ge 30000 -and $rd -lt 300000) { $type = 'stall'; $detail = "запрос выполнялся $([math]::Round($rd/1000)) с" } }
    }
    if ($type) { [pscustomobject]@{ t = $e.TimeCreated; disk = $disk; type = $type; detail = $detail } }
}

# зависание, после которого в течение 2 минут последовал сброс, — это то же происшествие
$resets = $inc | Where-Object type -eq 'reset'
$inc = $inc | Where-Object { $s = $_; $s.type -ne 'stall' -or -not ($resets | Where-Object { $_.disk -eq $s.disk -and [math]::Abs(($_.t - $s.t).TotalMinutes) -le 2 }) }

$months = @(); $m = Get-Date '2025-07-01'; while ($m -le (Get-Date)) { $months += $m.ToString('yyyy-MM'); $m = $m.AddMonths(1) }
$monthly = foreach ($mo in $months) { foreach ($dk in 'C', 'D') {
    $r = $inc | Where-Object { $_.disk -eq $dk -and $_.t.ToString('yyyy-MM') -eq $mo }
    [pscustomobject]@{ month = $mo; disk = $dk
        resets = @($r | Where-Object type -eq 'reset').Count
        write_errors = @($r | Where-Object type -eq 'write_error').Count
        stalls = @($r | Where-Object type -eq 'stall').Count
        admin_timeouts = @($r | Where-Object type -eq 'admin_timeout').Count } } }
$monthly | Export-Csv -NoTypeInformation -Encoding utf8 (Join-Path $out 'nvme_monthly.csv')

$inc | Where-Object type -ne 'admin_timeout' | Sort-Object t | ForEach-Object {
    [pscustomobject]@{ time = $_.t.ToString('yyyy-MM-dd HH:mm'); disk = $_.disk; type = $_.type; detail = $_.detail } } |
    Export-Csv -NoTypeInformation -Encoding utf8 (Join-Path $out 'nvme_incidents.csv')

"monthly rows: $(@($monthly).Count)"
$monthly | Format-Table -AutoSize | Out-String -Width 200
Import-Csv (Join-Path $out 'nvme_incidents.csv') | Format-Table -AutoSize | Out-String -Width 200
