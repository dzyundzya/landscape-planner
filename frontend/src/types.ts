export type Project = {
  id: number
  name: string
  description: string | null
  created_at: string
  updated_at: string | null
}

export type ProjectPage = {
  total: number
  page: number
  limit: number
  pages: number
  items: Project[]
}

export type ProjectFile = {
  id: number
  project_id: number
  version: number
  format: 'dxf' | 'dwf'
  status: 'ready' | 'conversion_required'
  original_name: string
  content_type: string | null
  size_bytes: number
  sha256: string
  created_at: string
}

export type JobStatus = 'queued' | 'running' | 'succeeded' | 'failed'

export type Job = {
  id: number
  project_id: number
  project_file_id: number | null
  type: string
  status: JobStatus
  stage: string | null
  result: Record<string, unknown> | null
  error: string | null
  created_at: string
  started_at: string | null
  finished_at: string | null
}

export type AnalysisBounds = {
  min_x: number
  min_y: number
  max_x: number
  max_y: number
}

export type AnalysisLayer = {
  name: string
  entity_count: number
  entity_counts: Record<string, number>
  block_entity_count: number
  block_entity_counts: Record<string, number>
  block_names: string[]
  is_unused: boolean
  suggestion: {
    object_type: SemanticObjectType
    geometry_role: 'line' | 'area'
    confidence: 'high' | 'medium'
    reason: string
  } | null
  preview: Array<{
    entity_type: string
    closed: boolean
    coordinates: [number, number][]
  }>
  preview_truncated: boolean
}

export type AnalysisBoundaryCandidate = {
  id: string
  layer: string
  entity_type: string
  area_source_units: number
  coordinates: [number, number][]
}

export type AnalysisWarning = {
  code: string
  message: string
  severity: 'info' | 'warning' | 'blocking'
}

export type Analysis = {
  id: number
  project_id: number
  project_file_id: number
  job_id: number
  schema_version: number
  result: {
    dxf_version: string | null
    drawing_units: string | null
    entity_counts: Record<string, number>
    layers: AnalysisLayer[]
    boundary_candidates: AnalysisBoundaryCandidate[]
    blocks: Record<string, number>
    labels_count: number
    external_references: string[]
    unsupported_entities: Record<string, number>
    bounds: AnalysisBounds | null
    warnings: AnalysisWarning[]
    requires_user_confirmation: boolean
  }
  created_at: string
}

export type CoordinateUnit =
  | 'millimeter'
  | 'centimeter'
  | 'meter'
  | 'kilometer'
  | 'inch'
  | 'foot'
  | 'yard'

export type TerritoryType =
  | 'courtyard'
  | 'preschool'
  | 'education_and_sport'
  | 'healthcare'
  | 'roads'
  | 'public_and_commercial'
  | 'parks_and_public_green'
  | 'industrial_and_protection'

export type SemanticObjectType =
  | 'building'
  | 'road'
  | 'utility_water'
  | 'utility_sewer'
  | 'utility_gas'
  | 'utility_power'
  | 'existing_tree'
  | 'existing_bush'
  | 'other_obstacle'
  | 'ignore'

export type LayerMapping = {
  layer: string
  object_type: SemanticObjectType
  attributes: {
    geometry_role: 'line' | 'area'
    measurement_reference?: string
    network_kind?: string
    building_use?: string
  }
}

export type ConfigPayload = {
  coordinate_unit: CoordinateUnit
  territory_type: TerritoryType
  boundary: {
    type: 'Polygon'
    coordinate_space: 'local_meters'
    coordinates: [number, number][][]
  }
  layer_mappings: LayerMapping[]
  generation: {
    max_trees: number
    max_bushes: number
    tree_tree_distance_m: number
    bush_bush_distance_m: number
    tree_bush_distance_m: number
    grid_spacing_m: number
  }
}

export type ConfigSnapshot = ConfigPayload & {
  id: number
  project_id: number
  analysis_id: number
  version: number
  schema_version: number
  unit_scale_to_meters: string
  rules_status: 'needs_verification' | 'verified'
  rules_version: string | null
  rules_sha256: string | null
  plant_catalog_status: 'needs_verification' | 'verified' | null
  plant_catalog_version: string | null
  plant_catalog_sha256: string | null
  content_sha256: string
  created_at: string
}

export type PlantingType = 'tree' | 'bush'
export type PlanStatus = 'needs_verification' | 'verified' | 'invalid'
export type ValidationStatus = 'passed' | 'failed' | 'needs_verification'

export type Planting = {
  public_id: string
  plan_id: number
  type: PlantingType
  source: 'generated' | 'manual'
  x_m: string
  y_m: string
  species: string | null
}

export type Plan = {
  id: number
  project_id: number
  project_file_id: number
  analysis_id: number
  config_snapshot_id: number
  job_id: number
  revision: number
  status: PlanStatus
  generator_version: string
  generation_summary: {
    candidate_count: number
    tree_count: number
    bush_count: number
    rejected_candidate_count: number
    strategy: string
    selected_offset_index: number
    offset_x_m: number
    offset_y_m: number
    grid_spacing_m: number | null
    warnings: string[]
  }
  plantings: Planting[]
  created_at: string
  updated_at: string | null
}

export type GeoJsonGeometry = {
  type: string
  coordinates?: unknown
  geometries?: GeoJsonGeometry[]
}

export type PlanPreview = {
  schema_version: number
  coordinate_space: 'local_meters'
  plan_id: number
  plan_revision: number
  boundary: GeoJsonGeometry
  objects: Array<{
    source_object_id: string
    object_type: SemanticObjectType
    geometry: GeoJsonGeometry
  }>
  restrictions: Array<{
    source_object_id: string
    object_type: SemanticObjectType
    planting_type: PlantingType
    rule_id: string
    rule_version: string
    min_distance_m: number
    document: string
    clause: string
    geometry: GeoJsonGeometry
  }>
  zones: {
    tree_available: GeoJsonGeometry
    bush_available: GeoJsonGeometry
    tree_exclusion: GeoJsonGeometry
    bush_exclusion: GeoJsonGeometry
  }
  issues: Array<{
    code: string
    message: string
    source_object_id: string | null
    planting_type: PlantingType | null
    rule_id: string | null
  }>
  summary: {
    object_count: number
    displayed_object_count: number
    restriction_count: number
    displayed_restriction_count: number
    source_coordinate_count: number
    displayed_coordinate_count: number
    simplified: boolean
  } | null
  plantings: Planting[]
}

export type ValidationCheck = {
  check_type: string
  status: ValidationStatus
  planting_id: string | null
  actual: string | null
  required: string | null
  unit: string | null
  rule_id: string | null
  rule_version: string | null
  source_object_id: string | null
  document: string | null
  clause: string | null
  reason: string
}

export type PlanValidation = {
  id: number
  plan_id: number
  plan_revision: number
  status: ValidationStatus
  validator_version: string
  checks: ValidationCheck[]
  summary: {
    total: number
    passed: number
    failed: number
    needs_verification: number
  }
  rules_status: 'needs_verification' | 'verified'
  rules_version: string | null
  rules_sha256: string | null
  plant_catalog_status: 'needs_verification' | 'verified' | null
  plant_catalog_version: string | null
  plant_catalog_sha256: string | null
  created_at: string
}

export type FileArtifact = {
  id: number
  project_id: number
  project_file_id: number | null
  job_id: number
  export_id: number | null
  kind: 'canonical_dxf' | 'result_dxf' | 'plan_json' | 'report_json' | 'report_markdown'
  format: 'dxf' | 'json' | 'markdown'
  download_name: string
  content_type: string
  size_bytes: number
  sha256: string
  created_at: string
}

export type PlanExport = {
  id: number
  project_id: number
  plan_id: number
  plan_revision: number
  validation_id: number
  job_id: number
  export_version: string
  manifest: Array<{
    artifact_id: number
    kind: FileArtifact['kind']
    format: FileArtifact['format']
    download_name: string
    size_bytes: number
    sha256: string
  }>
  artifacts: FileArtifact[]
  created_at: string
}
