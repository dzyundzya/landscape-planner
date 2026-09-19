export type Project = {
  id: number
  name: string
  description: string | null
  created_at: string
  updated_at: string | null
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
  attributes: { geometry_role: 'line' | 'area' }
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
