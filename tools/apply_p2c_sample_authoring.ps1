[CmdletBinding()]
param(
    [string]$BaseUrl = "http://127.0.0.1:8765",
    [ValidateRange(1, 120)]
    [int]$RequestTimeoutSec = 15,
    [switch]$Apply
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$CandidateArtifact = "96a97f35819de7be88b9de5e39a70410e5faf994cc53f5e307c548f5c0e65bc2"

function Invoke-WorkbenchRequest(
    [ValidateSet("Get", "Put")]
    [string]$Method,
    [string]$Uri,
    [byte[]]$Body
) {
    $arguments = @{
        Method = $Method
        Uri = $Uri
        TimeoutSec = $RequestTimeoutSec
        ErrorAction = "Stop"
    }
    if ($null -ne $Body) {
        $arguments.ContentType = "application/json; charset=utf-8"
        $arguments.Body = $Body
    }
    try {
        Invoke-RestMethod @arguments
    }
    catch {
        $retryGuidance = if ($Method -eq "Put") {
            " If this was a timeout, restart the workbench and re-read both revisions before retrying; the server-side outcome may be unknown."
        } else {
            ""
        }
        throw "$Method $Uri failed (timeout budget: ${RequestTimeoutSec}s): $($_.Exception.Message)$retryGuidance"
    }
}

function Get-Project([string]$ProjectId) {
    Invoke-WorkbenchRequest -Method Get -Uri "$BaseUrl/api/projects/$ProjectId"
}

function ConvertTo-AuthoringBody($Payload) {
    $json = ConvertTo-Json -InputObject $Payload -Depth 16 -Compress
    $bytes = [Text.UTF8Encoding]::new($false).GetBytes($json)
    $hasher = [Security.Cryptography.SHA256]::Create()
    try {
        $digest = [BitConverter]::ToString($hasher.ComputeHash($bytes)).Replace("-", "").ToLowerInvariant()
    }
    finally {
        $hasher.Dispose()
    }
    [pscustomobject]@{
        Bytes = $bytes
        Sha256 = $digest
    }
}

function Copy-Map($Value, [string[]]$Fields) {
    $result = [ordered]@{}
    if ($null -eq $Value) { return $result }
    foreach ($field in $Fields) {
        $property = $Value.PSObject.Properties[$field]
        if ($null -ne $property) { $result[$field] = $property.Value }
    }
    return $result
}

function Copy-JointOverrides($Overrides) {
    $result = [ordered]@{}
    foreach ($property in $Overrides.PSObject.Properties) {
        $result[$property.Name] = Copy-Map $property.Value @("x", "y", "confidence", "reason")
    }
    return $result
}

function Copy-JointDecisions($Decisions) {
    $result = [ordered]@{}
    foreach ($property in $Decisions.PSObject.Properties) {
        $result[$property.Name] = Copy-Map $property.Value @(
            "action", "candidate_artifact_sha256", "candidate_id", "final_xy", "reason"
        )
    }
    return $result
}

function Get-JointPoint($Overrides, [string]$JointId) {
    if (-not $Overrides.Contains($JointId)) { throw "Missing reviewed joint $JointId" }
    return @([double]$Overrides[$JointId].x, [double]$Overrides[$JointId].y)
}

function New-JointAnchor([string]$JointId) {
    [ordered]@{ kind = "joint"; joint_id = $JointId }
}

function New-Proxy(
    [string]$Side,
    [string]$JointId,
    [double[]]$Point,
    [string]$Reason
) {
    [ordered]@{
        kind = "manual_proxy"
        proxy_id = "shoe-opening.$Side"
        proxy_for_joint_id = $JointId
        xy = @($Point[0], $Point[1])
        label = "$Side visible shoe opening"
        reason = $Reason
    }
}

function New-JointSplitSpec([string]$PivotJoint, [string]$BoneStem) {
    $parts = [ordered]@{}
    foreach ($side in @("left", "right")) {
        $parts[$side] = [ordered]@{
            guide = @(
                New-JointAnchor "hip.$side"
                New-JointAnchor "knee.$side"
                New-JointAnchor "ankle.$side"
            )
            pivot = New-JointAnchor "$PivotJoint.$side"
            candidate_bone = "$BoneStem.$side"
        }
    }
    return [ordered]@{ parts = $parts }
}

function New-ProxyFootwearSpec {
    $left = New-Proxy "left" "ankle.left" @(701, 1435) `
        "ankle.left is hidden by the skirt and shoe"
    $right = New-Proxy "right" "ankle.right" @(624, 1512) `
        "use the reviewed garment opening instead of hidden anatomy"
    return [ordered]@{
        parts = [ordered]@{
            left = [ordered]@{
                guide = @(
                    New-JointAnchor "hip.left"
                    New-JointAnchor "knee.left"
                    $left
                )
                pivot = $left
                candidate_bone = "calf.left"
            }
            right = [ordered]@{
                guide = @(
                    New-JointAnchor "hip.right"
                    New-JointAnchor "knee.right"
                    $right
                )
                pivot = $right
                candidate_bone = "calf.right"
            }
        }
    }
}

function New-LayerReviews(
    $Project,
    $JointOverrides,
    [hashtable]$BoneByLayer,
    [hashtable]$SideByLayer,
    [hashtable]$SplitSpecs,
    [string[]]$ExcludedLayerIds
) {
    $bonePivotJoint = @{
        "root-pelvis" = "root"
        "pelvis-spine" = "pelvis"
        "spine-chest" = "chest"
        "chest-neck" = "neck"
        "neck-head" = "head"
        "forearm.left" = "wrist.left"
        "forearm.right" = "wrist.right"
    }
    $excluded = [Collections.Generic.HashSet[string]]::new($ExcludedLayerIds)
    $result = [ordered]@{}
    foreach ($layer in $Project.layers) {
        $id = [string]$layer.id
        $side = if ($SideByLayer.ContainsKey($id)) { $SideByLayer[$id] } else { $layer.side }
        if ($SplitSpecs.ContainsKey($id)) {
            $result[$id] = [ordered]@{
                canonical_role = $layer.canonical_role
                side = "bilateral"
                disposition = "split_left_right"
                visible = $true
                split_spec = $SplitSpecs[$id]
            }
            continue
        }
        if ($excluded.Contains($id)) {
            $result[$id] = [ordered]@{
                canonical_role = $layer.canonical_role
                side = $side
                disposition = "exclude"
                visible = $false
            }
            continue
        }
        if (-not $BoneByLayer.ContainsKey($id)) { throw "Missing bone mapping for $id" }
        $bone = $BoneByLayer[$id]
        if (-not $bonePivotJoint.ContainsKey($bone)) { throw "Missing pivot rule for $bone" }
        $result[$id] = [ordered]@{
            canonical_role = $layer.canonical_role
            side = $side
            disposition = "keep"
            visible = $true
            pivot_xy = Get-JointPoint $JointOverrides $bonePivotJoint[$bone]
            candidate_bone = $bone
        }
    }
    return $result
}

function New-PayloadA($Project) {
    $joints = Copy-JointOverrides $Project.overrides.joint_overrides
    $bones = @{
        "layer-000-back-hair" = "neck-head"; "layer-001-objects" = "root-pelvis"
        "layer-003-handwear-r" = "forearm.right"; "layer-005-bottomwear" = "pelvis-spine"
        "layer-006-topwear" = "spine-chest"; "layer-007-handwear-l" = "forearm.left"
        "layer-008-neck" = "chest-neck"
    }
    foreach ($index in 9..22) { $bones[("layer-{0:D3}-" -f $index) + @(
        "eyebrow-r", "eyebrow-l", "face", "nose", "mouth", "ears-r", "ears-l",
        "eyelash-r", "eyewhite-r", "eyewhite-l", "irides-r", "eyelash-l", "irides-l", "front-hair"
    )[$index - 9]] = "neck-head" }
    $splits = @{
        "layer-002-footwear" = New-JointSplitSpec "ankle" "calf"
        "layer-004-legwear" = New-JointSplitSpec "hip" "thigh"
    }
    return [ordered]@{
        schema_version = "autospine-workbench.override/v3"
        base_revision = [int]$Project.overrides.revision
        joint_overrides = $joints
        joint_decisions = Copy-JointDecisions $Project.overrides.joint_decisions
        split_decisions = [ordered]@{}
        layer_overrides = New-LayerReviews $Project $joints $bones @{} $splits @()
        notes = "P2c complete region authoring; bilateral footwear and legwear await preview review."
    }
}

function New-PayloadB($Project) {
    $joints = Copy-JointOverrides $Project.overrides.joint_overrides
    $joints["shoulder.left"] = [ordered]@{ x = 785.32; y = 590.74; reason = "character-left shoulder on screen right" }
    $joints["elbow.left"] = [ordered]@{ x = 798.0; y = 782.1; reason = "correct character-side mapping" }
    $joints["wrist.left"] = [ordered]@{ x = 851.4; y = 1035.1; reason = "correct character-side mapping" }
    $joints["shoulder.right"] = [ordered]@{ x = 560.4; y = 596.2; reason = "character-right shoulder on screen left" }
    $joints["elbow.right"] = [ordered]@{ x = 477.7; y = 826.9; reason = "correct character-side mapping" }
    $joints["wrist.right"] = [ordered]@{ x = 365.8; y = 945.6; reason = "correct character-side mapping" }
    $decisions = Copy-JointDecisions $Project.overrides.joint_decisions
    $decisions["ankle.left"] = [ordered]@{
        action = "unobservable"
        candidate_artifact_sha256 = $CandidateArtifact
        reason = "ankle anatomy is fully hidden; split pivot uses a reviewed shoe-opening proxy"
    }
    $bones = @{
        "layer-000-back-hair" = "neck-head"; "layer-003-bottomwear" = "pelvis-spine"
        "layer-004-neck" = "chest-neck"; "layer-005-topwear" = "spine-chest"
        "layer-006-objects" = "root-pelvis"; "layer-007-head-obj" = "neck-head"
        "layer-008-hand-r" = "forearm.left"; "layer-009-hand-l" = "forearm.right"
    }
    foreach ($index in 10..19) { $bones[("layer-{0:D3}-" -f $index) + @(
        "eyebrow", "headwear", "ears", "face", "nose", "mouth", "eyelash",
        "eyewhite", "irides", "front-hair"
    )[$index - 10]] = "neck-head" }
    $sides = @{ "layer-008-hand-r" = "left"; "layer-009-hand-l" = "right" }
    $splits = @{ "layer-001-footwear" = New-ProxyFootwearSpec }
    return [ordered]@{
        schema_version = "autospine-workbench.override/v3"
        base_revision = [int]$Project.overrides.revision
        joint_overrides = $joints
        joint_decisions = $decisions
        split_decisions = [ordered]@{}
        layer_overrides = New-LayerReviews $Project $joints $bones $sides $splits @("layer-002-handwear")
        notes = "P2c complete region authoring; character-side arms corrected; ankle.left is unobservable."
    }
}

$projectA = Get-Project "seethrough_output"
$projectB = Get-Project "seethrough_output_5"
if (@($projectA.overrides.split_decisions.PSObject.Properties).Count -or
    @($projectB.overrides.split_decisions.PSObject.Properties).Count) {
    throw "Sample split decisions already exist; do not silently reuse them during reauthoring"
}
$candidateIndex = Invoke-WorkbenchRequest -Method Get `
    -Uri "$BaseUrl/api/projects/seethrough_output_5/candidate-artifacts"
if ($CandidateArtifact -notin @($candidateIndex.items.artifact_sha256)) {
    throw "Pinned ankle.left unobservable evidence is unavailable"
}
$requests = @(
    [pscustomobject]@{ id = "seethrough_output"; payload = New-PayloadA $projectA },
    [pscustomobject]@{ id = "seethrough_output_5"; payload = New-PayloadB $projectB }
)

foreach ($request in $requests) {
    $target = "$BaseUrl/api/projects/$($request.id)/overrides"
    $serialized = ConvertTo-AuthoringBody $request.payload
    if (-not $Apply) {
        [pscustomobject]@{
            project_id = $request.id
            mode = "dry-run"
            base_revision = $request.payload.base_revision
            layer_review_count = $request.payload.layer_overrides.Count
            joint_decision_count = $request.payload.joint_decisions.Count
            payload_utf8_bytes = $serialized.Bytes.Length
            payload_sha256 = $serialized.Sha256
            target_url = $target
        }
        continue
    }
    Write-Information (
        "PUT {0} ({1} UTF-8 bytes, sha256 {2}, timeout {3}s)" -f `
        $target, $serialized.Bytes.Length, $serialized.Sha256, $RequestTimeoutSec
    ) -InformationAction Continue
    $saved = Invoke-WorkbenchRequest -Method Put -Uri $target -Body $serialized.Bytes
    [pscustomobject]@{
        project_id = $request.id
        mode = "applied"
        revision = $saved.revision
        layer_review_count = @($saved.layer_overrides.PSObject.Properties).Count
        joint_decision_count = @($saved.joint_decisions.PSObject.Properties).Count
    }
}
