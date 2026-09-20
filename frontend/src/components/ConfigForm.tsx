import { FormEvent, useMemo, useState } from 'react'

import { coordinateUnitOptions, guessCoordinateUnit, objectTypeOptions, territoryOptions } from '../constants'
import type {
  Analysis,
  ConfigPayload,
  ConfigSnapshot,
  CoordinateUnit,
  LayerMapping,
  SemanticObjectType,
  TerritoryType,
} from '../types'

type Props = {
  analysis: Analysis
  isSaving: boolean
  savedConfig: ConfigSnapshot | null
  onSave: (payload: ConfigPayload) => void
}

type Bounds = { minX: number; minY: number; maxX: number; maxY: number }
type Generation = ConfigPayload['generation']

const defaultGeneration: Generation = {
  max_trees: 50,
  max_bushes: 100,
  tree_tree_distance_m: 5,
  bush_bush_distance_m: 1.5,
  tree_bush_distance_m: 2.5,
  grid_spacing_m: 1,
}

export function ConfigForm({ analysis, isSaving, savedConfig, onSave }: Props) {
  const initialUnit = guessCoordinateUnit(analysis.result.drawing_units)
  const [coordinateUnit, setCoordinateUnit] = useState<CoordinateUnit>(initialUnit)
  const [territoryType, setTerritoryType] = useState<TerritoryType>('courtyard')
  const [bounds, setBounds] = useState<Bounds>(() => scaledBounds(analysis, initialUnit))
  const [layerMappings, setLayerMappings] = useState<LayerMapping[]>(() =>
    analysis.result.layers.map((layer) => ({
      layer: layer.name,
      object_type: 'ignore',
      attributes: { geometry_role: 'line' },
    })),
  )
  const [generation, setGeneration] = useState<Generation>(defaultGeneration)

  const boundaryIsValid = bounds.maxX > bounds.minX && bounds.maxY > bounds.minY
  const configuredLayers = useMemo(
    () => layerMappings.filter((mapping) => mapping.object_type !== 'ignore').length,
    [layerMappings],
  )
  const hasUtilityLayers = layerMappings.some((mapping) => mapping.object_type.startsWith('utility_'))

  function changeUnit(value: CoordinateUnit) {
    setCoordinateUnit(value)
    if (analysis.result.bounds) {
      setBounds(scaledBounds(analysis, value))
    }
  }

  function updateMapping(index: number, patch: Partial<LayerMapping> | { geometryRole: 'line' | 'area' }) {
    setLayerMappings((current) =>
      current.map((mapping, mappingIndex) => {
        if (mappingIndex !== index) return mapping
        if ('geometryRole' in patch) {
          return { ...mapping, attributes: { geometry_role: patch.geometryRole } }
        }
        if (patch.object_type) {
          return {
            ...mapping,
            ...patch,
            attributes: defaultAttributes(patch.object_type, mapping.attributes.geometry_role),
          }
        }
        return { ...mapping, ...patch }
      }),
    )
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    if (!boundaryIsValid) return
    onSave({
      coordinate_unit: coordinateUnit,
      territory_type: territoryType,
      boundary: {
        type: 'Polygon',
        coordinate_space: 'local_meters',
        coordinates: [[
          [bounds.minX, bounds.minY],
          [bounds.maxX, bounds.minY],
          [bounds.maxX, bounds.maxY],
          [bounds.minX, bounds.maxY],
          [bounds.minX, bounds.minY],
        ]],
      },
      layer_mappings: layerMappings.map((mapping) => ({
        ...mapping,
        attributes: mapping.object_type === 'building'
          ? {
              ...mapping.attributes,
              building_use: ['preschool', 'education_and_sport'].includes(territoryType)
                ? 'school_or_kindergarten'
                : 'other',
            }
          : mapping.attributes,
      })),
      generation,
    })
  }

  return (
    <section className="panel config-panel" aria-labelledby="config-title">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Шаг 4</p>
          <h2 id="config-title">Подтверждение настроек</h2>
          <p className="section-description">
            Проверьте единицы, границу и назначение каждого слоя. Эти данные станут неизменяемым снимком расчёта.
          </p>
        </div>
        <span className="counter-badge">Настроено слоёв: {configuredLayers}/{layerMappings.length}</span>
      </div>

      <form onSubmit={submit}>
        <div className="form-section two-column-form">
          <label>
            <span>Единицы координат</span>
            <select value={coordinateUnit} onChange={(event) => changeUnit(event.target.value as CoordinateUnit)}>
              {coordinateUnitOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
            <small>При смене единиц bbox пересчитывается в метры.</small>
          </label>
          <label>
            <span>Тип территории</span>
            <select value={territoryType} onChange={(event) => setTerritoryType(event.target.value as TerritoryType)}>
              {territoryOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
            <small>Используется для подбора ассортимента растений.</small>
          </label>
        </div>

        <fieldset className="form-section">
          <legend>Граница участка в локальных метрах</legend>
          <p className="field-hint">Сейчас используется прямоугольник bbox. Позже его можно будет заменить выбранным контуром.</p>
          <div className="boundary-grid">
            <NumberField label="min X" value={bounds.minX} onChange={(value) => setBounds({ ...bounds, minX: value })} />
            <NumberField label="min Y" value={bounds.minY} onChange={(value) => setBounds({ ...bounds, minY: value })} />
            <NumberField label="max X" value={bounds.maxX} onChange={(value) => setBounds({ ...bounds, maxX: value })} />
            <NumberField label="max Y" value={bounds.maxY} onChange={(value) => setBounds({ ...bounds, maxY: value })} />
          </div>
          {!boundaryIsValid && <p className="field-error">Максимальные координаты должны быть больше минимальных.</p>}
        </fieldset>

        <fieldset className="form-section">
          <legend>Сопоставление слоёв</legend>
          <p className="field-hint">Каждый слой нужно классифицировать или явно исключить из расчёта.</p>
          <div className="layer-table" role="table" aria-label="Сопоставление слоёв DXF">
            <div className="layer-row layer-header" role="row">
              <span>Слой и состав</span><span>Назначение</span><span>Геометрия</span>
            </div>
            {analysis.result.layers.map((layer, index) => {
              const mapping = layerMappings[index]
              return (
                <div className="layer-row" role="row" key={layer.name}>
                  <div>
                    <strong>{layer.name}</strong>
                    <small>{layer.entity_count} объектов · {formatEntityCounts(layer.entity_counts)}</small>
                  </div>
                  <select
                    aria-label={`Назначение слоя ${layer.name}`}
                    value={mapping.object_type}
                    onChange={(event) => updateMapping(index, { object_type: event.target.value as SemanticObjectType })}
                  >
                    {objectTypeOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                  </select>
                  <select
                    aria-label={`Тип геометрии слоя ${layer.name}`}
                    value={mapping.attributes.geometry_role}
                    disabled={mapping.object_type === 'ignore'}
                    onChange={(event) => updateMapping(index, { geometryRole: event.target.value as 'line' | 'area' })}
                  >
                    <option value="line">Линия</option>
                    <option value="area">Площадной объект</option>
                  </select>
                </div>
              )
            })}
          </div>
          {hasUtilityLayers && (
            <article className="notice notice-warning mapping-notice">
              <span className="notice-marker" />
              <div>
                <strong>Проверьте геометрию инженерных сетей</strong>
                <p>Расстояние считается от показанной линии как от наружной поверхности сети. Если в чертеже указана ось, сначала нужны диаметр и преобразование геометрии.</p>
              </div>
            </article>
          )}
        </fieldset>

        <fieldset className="form-section">
          <legend>Параметры генерации</legend>
          <div className="generation-grid">
            <NumberField label="Максимум деревьев" value={generation.max_trees} min={0} step={1} onChange={(value) => setGeneration({ ...generation, max_trees: value })} />
            <NumberField label="Максимум кустарников" value={generation.max_bushes} min={0} step={1} onChange={(value) => setGeneration({ ...generation, max_bushes: value })} />
            <NumberField label="Дерево — дерево, м" value={generation.tree_tree_distance_m} min={0.01} onChange={(value) => setGeneration({ ...generation, tree_tree_distance_m: value })} />
            <NumberField label="Куст — куст, м" value={generation.bush_bush_distance_m} min={0.01} onChange={(value) => setGeneration({ ...generation, bush_bush_distance_m: value })} />
            <NumberField label="Дерево — куст, м" value={generation.tree_bush_distance_m} min={0.01} onChange={(value) => setGeneration({ ...generation, tree_bush_distance_m: value })} />
            <NumberField label="Шаг сетки, м" value={generation.grid_spacing_m} min={0.01} onChange={(value) => setGeneration({ ...generation, grid_spacing_m: value })} />
          </div>
        </fieldset>

        <div className="form-actions">
          <div>
            {savedConfig ? (
              <p className="save-result"><strong>Конфигурация сохранена.</strong> Версия {savedConfig.version}, статус норм: {savedConfig.rules_status === 'verified' ? 'проверены' : 'требуют проверки'}.</p>
            ) : (
              <p className="muted">Сохранение не запускает генерацию плана.</p>
            )}
          </div>
          <button className="button button-primary" type="submit" disabled={isSaving || !boundaryIsValid}>
            {isSaving ? 'Сохраняем…' : 'Сохранить конфигурацию'}
          </button>
        </div>
      </form>
    </section>
  )
}

function NumberField({ label, value, onChange, min, step = 0.01 }: { label: string; value: number; onChange: (value: number) => void; min?: number; step?: number }) {
  return (
    <label>
      <span>{label}</span>
      <input
        type="number"
        value={value}
        min={min}
        step={step}
        required
        onChange={(event) => {
          if (Number.isFinite(event.target.valueAsNumber)) onChange(event.target.valueAsNumber)
        }}
      />
    </label>
  )
}

function scaledBounds(analysis: Analysis, unit: CoordinateUnit): Bounds {
  const bounds = analysis.result.bounds
  if (!bounds) return { minX: 0, minY: 0, maxX: 0, maxY: 0 }
  const scale = coordinateUnitOptions.find((option) => option.value === unit)?.scale ?? 1
  return {
    minX: round(bounds.min_x * scale),
    minY: round(bounds.min_y * scale),
    maxX: round(bounds.max_x * scale),
    maxY: round(bounds.max_y * scale),
  }
}

function round(value: number) {
  return Math.round(value * 1_000_000) / 1_000_000
}

function formatEntityCounts(counts: Record<string, number>) {
  return Object.entries(counts).map(([type, count]) => `${type}: ${count}`).join(', ') || 'пустой слой'
}

function defaultAttributes(objectType: SemanticObjectType, geometryRole: 'line' | 'area'): LayerMapping['attributes'] {
  const measurementReferences: Partial<Record<SemanticObjectType, string>> = {
    building: 'exterior_wall',
    road: 'roadway_edge',
    utility_water: 'utility_outer_surface',
    utility_sewer: 'utility_outer_surface',
    utility_gas: 'utility_outer_surface',
    utility_power: 'utility_outer_surface',
  }
  return {
    geometry_role: geometryRole,
    ...(measurementReferences[objectType] ? { measurement_reference: measurementReferences[objectType] } : {}),
    ...(objectType === 'utility_power' ? { network_kind: 'underground_power_cable' } : {}),
  }
}
