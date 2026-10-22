# Explicit maintenance approval required. Run elevated from a Windows-local copy.
param(
    [Parameter(Mandatory=$true)][string]$Distribution,
    [Parameter(Mandatory=$true)][string]$VhdPath,
    [Parameter(Mandatory=$true)][string]$OutputDirectory,
    [switch]$Apply
)
$ErrorActionPreference = 'Stop'
$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (!$Apply -or !$admin) { throw 'Explicit -Apply and Windows elevation are required' }
if ($Distribution -ne 'Ubuntu-20.04' -or !(Test-Path -LiteralPath $VhdPath)) { throw 'Unexpected distribution or missing VHD' }
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$statusPath = Join-Path $OutputDirectory 'status.json'
$logPath = Join-Path $OutputDirectory 'maintenance.log'
$script:records = @()
$script:runningIds = @()
$script:policyChanged = $false
$script:shutdownRequested = $false
$script:problem = $null
$before = (Get-Item -LiteralPath $VhdPath).Length
function Log([string]$message) {
    ('{0:o} {1}' -f (Get-Date), $message) | Add-Content -LiteralPath $logPath
}
function Status([string]$phase) {
    [pscustomobject]@{Phase=$phase;BeforeVhdBytes=$before;AfterVhdBytes=if(Test-Path -LiteralPath $VhdPath){(Get-Item -LiteralPath $VhdPath).Length}else{$null};Error=$script:problem;RunningBefore=$script:runningIds;UpdatedAt=(Get-Date).ToString('o')} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $statusPath -Encoding UTF8
}
function Docker([string[]]$Arguments) {
    $value = & wsl.exe -d $Distribution -u root -- docker @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) { throw ('Docker command unsuccessful: '+$Arguments[0]) }
    return $value
}
function Restore-Workloads {
    if (!$script:policyChanged -and !$script:shutdownRequested) { return }
    Log 'Restoring Docker availability and exact pre-maintenance container selection'
    & wsl.exe -d $Distribution -u root -- systemctl start docker 2>&1 | Out-Null
    $ready=$false
    for($i=0;$i -lt 30;$i++) {
        & wsl.exe -d $Distribution -u root -- docker info --format '{{.ServerVersion}}' 2>&1 | Out-Null
        if($LASTEXITCODE -eq 0){$ready=$true;break}
        Start-Sleep -Seconds 2
    }
    if(!$ready){throw 'Docker did not become available; saved snapshot retained'}
    if($script:runningIds.Count){Docker -Arguments (@('start')+$script:runningIds) | Out-Null}
    foreach($row in $script:records){
        $policy=$row.Policy.Name
        if(!$policy){$policy='no'}
        if($policy -eq 'on-failure' -and $row.Policy.MaximumRetryCount -gt 0){$policy+=':'+$row.Policy.MaximumRetryCount}
        Docker -Arguments @('update',('--restart='+$policy),$row.Id) | Out-Null
    }
    $current=@(Docker -Arguments @('ps','-q','--no-trunc'))
    $extra=@($current | Where-Object {$_ -and $script:runningIds -notcontains $_})
    if($extra.Count){throw 'Unexpected newly running container detected; no unrelated process stopped automatically'}
    foreach($id in $script:runningIds){if($current -notcontains $id){throw 'Previously running container not restored'}}
    $summary=Docker -Arguments @('ps','-a','--format','{{.Names}}|{{.Status}}')
    $summary | Set-Content -LiteralPath (Join-Path $OutputDirectory 'containers-after.txt') -Encoding UTF8
    Log 'Exact running container IDs restored; original restart policies restored'
}
Status 'Starting'
try {
    $active=@(& wsl.exe --list --running --quiet | ForEach-Object {$_.Replace([string][char]0,'').Trim()} | Where-Object {$_})
    if(@($active | Where-Object {$_ -ne $Distribution}).Count){throw 'Another WSL distribution is running; shutdown scope would exceed approval'}
    $all=@(Docker -Arguments @('ps','-aq','--no-trunc') | Where-Object {$_})
    $script:runningIds=@(Docker -Arguments @('ps','-q','--no-trunc') | Where-Object {$_})
    foreach($id in $all){
        $line=Docker -Arguments @('inspect','--format','{{.Id}}|{{.Name}}|{{.State.Status}}|{{json .HostConfig.RestartPolicy}}',$id)
        $parts=([string]$line).Split('|',4)
        if($parts.Count -ne 4){throw 'Container snapshot format invalid'}
        $script:records+= [pscustomobject]@{Id=$parts[0];Name=$parts[1];State=$parts[2];Policy=($parts[3]|ConvertFrom-Json)}
    }
    [pscustomobject]@{Distribution=$Distribution;VhdPath=$VhdPath;RunningIds=$script:runningIds;Containers=$script:records} | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath (Join-Path $OutputDirectory 'containers-before.json') -Encoding UTF8
    Log ('Saved '+$all.Count+' containers; '+$script:runningIds.Count+' running')
    # Prevent previously stopped restart=always containers from being started by daemon reboot.
    $script:policyChanged=$true
    if($all.Count){Docker -Arguments (@('update','--restart=no')+$all) | Out-Null}
    Status 'GracefullyStoppingContainers'
    # Infinite grace: never turn this maintenance into a timed SIGKILL of a database/job.
    if($script:runningIds.Count){Docker -Arguments (@('stop','--timeout=-1')+$script:runningIds) | Out-Null}
    & wsl.exe -d $Distribution -u root -- sync
    if($LASTEXITCODE -ne 0){throw 'Linux sync failed; will not compact'}
    Status 'ShuttingDownWSL'
    $script:shutdownRequested=$true
    & wsl.exe --shutdown
    if($LASTEXITCODE -ne 0){throw 'WSL shutdown failed'}
    Start-Sleep -Seconds 3
    $active=@(& wsl.exe --list --running --quiet | ForEach-Object {$_.Replace([string][char]0,'').Trim()} | Where-Object {$_})
    if($active.Count){throw 'WSL relaunched before compaction; refusing a live VHD'}
    Status 'CompactingOfflineVHD'
    $dp=Join-Path $OutputDirectory 'compact.txt'
    @('select vdisk file="'+$VhdPath+'"','attach vdisk readonly','compact vdisk','detach vdisk','exit') | Set-Content -LiteralPath $dp -Encoding ASCII
    & diskpart.exe /s $dp 2>&1 | Set-Content -LiteralPath (Join-Path $OutputDirectory 'diskpart.log') -Encoding UTF8
    $dpExit=$LASTEXITCODE
    if($dpExit -ne 0){throw 'DiskPart compaction unsuccessful; inspect private log'}
    Log ('DiskPart completed; VHD bytes before='+$before+' after='+(Get-Item -LiteralPath $VhdPath).Length)
} catch {
    $script:problem=$_.Exception.Message
    Log ('ERROR '+$script:problem)
} finally {
    # Always attempt detach even if DiskPart partially failed, before restarting the distro.
    if($script:shutdownRequested){
        try {
            $detach=Join-Path $OutputDirectory 'detach.txt'
            @('select vdisk file="'+$VhdPath+'"','detach vdisk','exit') | Set-Content -LiteralPath $detach -Encoding ASCII
            & diskpart.exe /s $detach 2>&1 | Out-Null
        } catch { Log 'Detach cleanup unsuccessful; inspect DiskPart log' }
    }
    try { Restore-Workloads } catch {
        $script:problem=([string]$script:problem+'; restoration: '+$_.Exception.Message).Trim('; ')
        Log $script:problem
    }
    Status $(if($script:problem){'CompletedWithError'}else{'Completed'})
}
