$ErrorActionPreference = 'SilentlyContinue'
$l = 'Microsoft-Windows-Storage-Storport/Operational'
function D($e) { $h = @{}; ([xml]$e.ToXml()).Event.EventData.Data | ForEach-Object { $h[$_.Name] = $_.'#text' }; $h }
function N($v) { if ($v -match '^\d+$') { [int64]$v } else { 0 } }

$all = Get-WinEvent -FilterHashtable @{LogName = $l; Id = 504, 524, 549, 557 } | ForEach-Object { $d = D $_; $d['_t'] = $_.TimeCreated; $d['_id'] = $_.Id; $d }

# карта ClassDeviceGuid/AdapterGuid -> диск по событиям, где есть серийник
$map = @{}
foreach ($d in $all) {
    $disk = if ($d.SerialNumber -like '6479*') { 'C' } elseif ($d.SerialNumber -like '0000*') { 'D' } elseif ($d.SerialNumber -match 'WD-') { 'HDD' } else { $null }
    if ($disk) { if ($d.ClassDeviceGuid) { $map[$d.ClassDeviceGuid] = $disk }; if ($d.AdapterGuid) { $map['A' + $d.AdapterGuid] = $disk } }
}
"Карта GUID -> диск:"; $map.GetEnumerator() | ForEach-Object { "  $($_.Key) = $($_.Value)" }

$rows = foreach ($d in $all) {
    $disk = if ($d.SerialNumber -like '6479*') { 'C' } elseif ($d.SerialNumber -like '0000*') { 'D' } elseif ($d.SerialNumber -match 'WD-') { 'HDD' }
            elseif ($map[$d.ClassDeviceGuid]) { $map[$d.ClassDeviceGuid] } elseif ($map['A' + $d.AdapterGuid]) { $map['A' + $d.AdapterGuid] } else { '?' }
    $cat = $null
    switch ($d._id) {
        504 { if ((N $d.HierarchicalResetSuccessCount) -gt 0 -or (N $d.TimeoutsInMiniport) -gt 0) { $cat = 'reset' } }
        524 { if ($d.MiniportEventDescription -match 'Timeout') { $cat = 'admin_timeout' }
              elseif ($d.MiniportEventDescription -notmatch 'Admin Command Error') { $cat = 'miniport_other:' + $d.MiniportEventDescription } }
        549 { $sk = N $d.SenseKey; $srb = N $d.SrbStatus
              if ($sk -in 3, 4) { $cat = 'media_hw_error' }
              elseif ($srb -eq 14) { $cat = 'io_aborted_by_reset' } }
        557 { $rd = N $d.RequestDuration_ms; if ($rd -ge 30000) { $cat = 'slow_io'; $d['_rd'] = $rd } }
    }
    if ($cat) { [pscustomobject]@{ M = $d._t.ToString('yyyy-MM'); T = $d._t; Disk = $disk; Cat = $cat; RD = $d._rd } }
}

"`nРаспределение длительности slow_io (RequestDuration):"
$rows | Where-Object Cat -eq 'slow_io' | ForEach-Object {
    $b = if ($_.RD -lt 60000) { '30-60 с' } elseif ($_.RD -lt 300000) { '1-5 мин' } elseif ($_.RD -lt 3600000) { '5-60 мин' } else { '> 1 ч (сон)' }
    "$($_.Disk) $b" } | Group-Object | Sort-Object Name | ForEach-Object { "  {0,5}x {1}" -f $_.Count, $_.Name }

"`nАппаратные ошибки и сбросы (по датам):"
$rows | Where-Object Cat -in 'media_hw_error', 'reset', 'io_aborted_by_reset' | Sort-Object T | ForEach-Object { "  {0:yyyy-MM-dd HH:mm} {1} {2}" -f $_.T, $_.Disk, $_.Cat }

"`nПо месяцам:"
$rows | Group-Object M, Disk, Cat | Sort-Object Name | ForEach-Object { "  {0,5}x {1}" -f $_.Count, $_.Name }

$rows | Select-Object M, Disk, Cat, @{n = 'T'; e = { $_.T.ToString('s') } }, RD | ConvertTo-Json -Depth 3 | Set-Content -Encoding utf8 "$PSScriptRoot\nvme_events.json"
