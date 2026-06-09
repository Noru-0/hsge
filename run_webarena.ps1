# =============================================================================
# HSGE WebArena — helper script to run with different providers
# =============================================================================
# Usage:
#   .\run_webarena.ps1                  # dùng provider trong .env (mặc định: deepseek)
#   .\run_webarena.ps1 -Provider openai # dùng OpenAI
#   .\run_webarena.ps1 -Provider deepseek -ExplorerModel deepseek-chat -SolverModel deepseek-reasoner
#   .\run_webarena.ps1 -DryRun          # dry-run test
# =============================================================================

param(
    [ValidateSet("deepseek", "openai", "custom")]
    [string]$Provider = $null,

    [string]$ExplorerModel = $null,
    [string]$SolverModel = $null,
    [string]$Model = $null,

    [string]$RootUrl = $null,
    [string]$OutDir = "outputs/wa_run",
    [int]$MaxNodes = 15,
    [int]$MaxDepth = 6,
    [int]$MaxSteps = 15,

    [switch]$DryRun = $false
)

$python = "C:/Users/Admin/AppData/Local/Programs/Python/Python313/python.exe"
$script = "run_webarena.py"

$args = @($script)

if ($DryRun) {
    $args += "--dry-run"
    $args += "--out", "outputs/wa_dry_test"
} else {
    if ($Provider)     { $args += "--provider", $Provider }
    if ($Model)        { $args += "--model", $Model }
    if ($ExplorerModel){ $args += "--explorer-model", $ExplorerModel }
    if ($SolverModel)  { $args += "--solver-model", $SolverModel }
    if ($RootUrl)      { $args += "--root-url", $RootUrl }
    $args += "--out", $OutDir
    $args += "--max-nodes", $MaxNodes
    $args += "--max-depth", $MaxDepth
    $args += "--max-steps", $MaxSteps
}

Write-Host ">>> Running: $python $($args -join ' ')" -ForegroundColor Cyan
& $python $args
