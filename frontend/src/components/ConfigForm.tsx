import { FormEvent, useMemo, useState } from 'react'

import { coordinateUnitOptions, guessCoordinateUnit, objectTypeOptions, territoryOptions } from '../constants'
import type {
  Analysis,
  AnalysisBoundaryCandidate,
  AnalysisLayer,
  AnalysisLayerGroup,
  ConfigPayload,
  ConfigSnapshot,
  CoordinateUnit,
  LayerMapping,
  SemanticObjectType,
  TerritoryType,
} from '../types'
import { BoundaryPicker } from './BoundaryPicker'
import { LayerPreview } from './LayerPreview'
import { LayerAssistant } from './LayerAssistant'

type Props = {
  analysis: Analysis
  isSaving: boolean
  savedConfig: ConfigSnapshot | null
  onSave: (payload: ConfigPayload) => void
}

type Bounds = { minX: number; minY: number; maxX: number; maxY: number }
type Generation = ConfigPayload['generation']
type LayerView = 'active' | 'all' | 'suggested' | 'uncertain' | 'configured' | 'ignored' | 'unused'

const defaultGeneration: Generation = {
  max_trees: 50,
  max_bushes: 100,
  tree_tree_distance_m: 5,
  bush_bush_distance_m: 1.5,
  tree_bush_distance_m: 2.5,
  grid_spacing_m: 1,
}

export function ConfigForm({ analysis, isSaving, savedConfig, onSave }: Props) {
  const restoredConfig = savedConfig?.analysis_id === analysis.id ? savedConfig : null
  const initialUnit = restoredConfig?.coordinate_unit ?? guessCoordinateUnit(analysis.result.drawing_units)
  const initialBoundary = restoredConfig?.boundary.coordinates[0] ?? null
  const initialBounds = initialBoundary ? boundsFromRing(initialBoundary) : scaledBounds(analysis, initialUnit)
  const savedMappings = new Map(
    restoredConfig?.layer_mappings.map((mapping) => [mapping.layer.toLocaleLowerCase('ru-RU'), mapping]),
  )
  const [coordinateUnit, setCoordinateUnit] = useState<CoordinateUnit>(initialUnit)
  const [territoryType, setTerritoryType] = useState<TerritoryType>(restoredConfig?.territory_type ?? 'courtyard')
  const [bounds, setBounds] = useState<Bounds>(initialBounds)
  const [boundaryCoordinates, setBoundaryCoordinates] = useState<[number, number][]>(() => initialBoundary ?? rectangleRing(initialBounds))
  const [selectedBoundaryId, setSelectedBoundaryId] = useState<string | null>(null)
  const [layerMappings, setLayerMappings] = useState<LayerMapping[]>(() =>
    analysis.result.layers.map((layer) => savedMappings.get(layer.name.toLocaleLowerCase('ru-RU')) ?? ({
        layer: layer.name,
        object_type: 'ignore',
        attributes: { geometry_role: 'line' },
      })),
  )
  const [generation, setGeneration] = useState<Generation>(restoredConfig?.generation ?? defaultGeneration)
  const [layerSearch, setLayerSearch] = useState('')
  const [layerView, setLayerView] = useState<LayerView>('active')
  const [bulkObjectType, setBulkObjectType] = useState<SemanticObjectType>('ignore')
  const [previewLayerName, setPreviewLayerName] = useState<string | null>(null)
  const [assistantIsOpen, setAssistantIsOpen] = useState(false)

  const boundaryIsValid = bounds.maxX > bounds.minX && bounds.maxY > bounds.minY
  const includedLayers = useMemo(
    () => layerMappings.filter((mapping) => mapping.object_type !== 'ignore').length,
    [layerMappings],
  )
  const hasUtilityLayers = layerMappings.some((mapping) => mapping.object_type.startsWith('utility_'))
  const scale = coordinateUnitOptions.find((option) => option.value === coordinateUnit)?.scale ?? 1
  const boundaryCandidates = useMemo(
    () => analysis.result.boundary_candidates.map((candidate) => scaleBoundaryCandidate(candidate, scale)),
    [analysis.result.boundary_candidates, scale],
  )
  const visibleLayers = useMemo(() => {
    const query = layerSearch.trim().toLocaleLowerCase('ru-RU')
    return analysis.result.layers.map((layer, index) => ({ layer, index })).filter(({ layer, index }) => {
      if (query && !layer.name.toLocaleLowerCase('ru-RU').includes(query)) return false
      const mapping = layerMappings[index]
      if (layerView === 'active') return !layer.is_unused
      if (layerView === 'suggested') return layer.suggestion !== null && layer.suggestion.object_type !== 'ignore'
      if (layerView === 'uncertain') return layer.suggestion === null || layer.suggestion.confidence === 'medium'
      if (layerView === 'configured') return mapping.object_type !== 'ignore'
      if (layerView === 'ignored') return mapping.object_type === 'ignore'
      if (layerView === 'unused') return layer.is_unused
      return true
    })
  }, [analysis.result.layers, layerMappings, layerSearch, layerView])
  const confidentSuggestionCount = analysis.result.layers.filter(
    (layer) => layer.suggestion?.confidence === 'high' && layer.suggestion.object_type !== 'ignore',
  ).length
  const previewLayer = analysis.result.layers.find((layer) => layer.name === previewLayerName) ?? null
  const unresolvedLayerCount = analysis.result.layers.filter(
    (layer) => !layer.is_unused && layer.suggestion?.confidence !== 'high',
  ).length

  function changeUnit(value: CoordinateUnit) {
    setCoordinateUnit(value)
    const nextScale = coordinateUnitOptions.find((option) => option.value === value)?.scale ?? 1
    const selectedCandidate = analysis.result.boundary_candidates.find((candidate) => candidate.id === selectedBoundaryId)
    if (selectedCandidate) {
      const coordinates = selectedCandidate.coordinates.map(([x, y]) => [round(x * nextScale), round(y * nextScale)] as [number, number])
      setBoundaryCoordinates(coordinates)
      setBounds(boundsFromRing(coordinates))
      return
    }
    const nextBounds = scaledBounds(analysis, value)
    setBounds(nextBounds)
    setBoundaryCoordinates(rectangleRing(nextBounds))
  }

  function changeBounds(nextBounds: Bounds) {
    setBounds(nextBounds)
    setBoundaryCoordinates(rectangleRing(nextBounds))
    setSelectedBoundaryId(null)
  }

  function selectBoundary(candidate: AnalysisBoundaryCandidate) {
    setSelectedBoundaryId(candidate.id)
    setBoundaryCoordinates(candidate.coordinates)
    setBounds(boundsFromRing(candidate.coordinates))
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

  function applySuggestions(onlyVisible: boolean) {
    const visibleIndexes = new Set(visibleLayers.map(({ index }) => index))
    setLayerMappings((current) => current.map((mapping, index) => {
      if (onlyVisible && !visibleIndexes.has(index)) return mapping
      const suggestion = analysis.result.layers[index].suggestion
      if (!suggestion || suggestion.object_type === 'ignore') return mapping
      return {
        ...mapping,
        object_type: suggestion.object_type,
        attributes: defaultAttributes(suggestion.object_type, suggestion.geometry_role),
      }
    }))
  }

  function applyConfidentSuggestions() {
    setLayerMappings((current) => current.map((mapping, index) => {
      const suggestion = analysis.result.layers[index].suggestion
      if (!suggestion || suggestion.confidence !== 'high' || suggestion.object_type === 'ignore') return mapping
      return {
        ...mapping,
        object_type: suggestion.object_type,
        attributes: defaultAttributes(suggestion.object_type, suggestion.geometry_role),
      }
    }))
  }

  function applyAssistantGroup(
    group: AnalysisLayerGroup,
    objectType: SemanticObjectType,
    geometryRole: 'line' | 'area',
  ) {
    const names = new Set(group.layer_names.map((name) => name.toLocaleLowerCase('ru-RU')))
    setLayerMappings((current) => current.map((mapping) => (
      names.has(mapping.layer.toLocaleLowerCase('ru-RU'))
        ? {
            ...mapping,
            object_type: objectType,
            attributes: defaultAttributes(objectType, geometryRole),
          }
        : mapping
    )))
  }

  function applyBulkType() {
    const visibleIndexes = new Set(visibleLayers.map(({ index }) => index))
    setLayerMappings((current) => current.map((mapping, index) => (
      visibleIndexes.has(index)
        ? {
            ...mapping,
            object_type: bulkObjectType,
            attributes: defaultAttributes(bulkObjectType, mapping.attributes.geometry_role),
          }
        : mapping
    )))
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
        coordinates: [boundaryCoordinates],
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
            Проверьте единицы и границу. Назначьте только подтверждённые препятствия; остальные слои останутся исключёнными.
          </p>
        </div>
        <span className="counter-badge">Учитывается слоёв: {includedLayers} из {layerMappings.length}</span>
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
          <p className="field-hint">
            Выберите подходящий замкнутый контур на схеме. Если нужного контура нет, задайте прямоугольник координатами.
          </p>
          {boundaryCandidates.length > 0 && (
            <div className="boundary-selection">
              <BoundaryPicker
                candidates={boundaryCandidates}
                selectedId={selectedBoundaryId}
                onSelect={selectBoundary}
              />
              <div className="boundary-candidate-list">
                <strong>Крупные замкнутые контуры</strong>
                <p>{selectedBoundaryId ? 'Выбранный контур подсвечен.' : 'Нажмите на контур или выберите его из списка.'}</p>
                {boundaryCandidates.slice(0, 8).map((candidate, index) => (
                  <button
                    className={candidate.id === selectedBoundaryId ? 'boundary-candidate selected' : 'boundary-candidate'}
                    key={candidate.id}
                    type="button"
                    onClick={() => selectBoundary(candidate)}
                  >
                    <span>Контур {index + 1}</span>
                    <small>{candidate.layer} · {formatArea(candidate.area_source_units)} м²</small>
                  </button>
                ))}
              </div>
            </div>
          )}
          <div className="boundary-grid">
            <NumberField label="min X" value={bounds.minX} onChange={(value) => changeBounds({ ...bounds, minX: value })} />
            <NumberField label="min Y" value={bounds.minY} onChange={(value) => changeBounds({ ...bounds, minY: value })} />
            <NumberField label="max X" value={bounds.maxX} onChange={(value) => changeBounds({ ...bounds, maxX: value })} />
            <NumberField label="max Y" value={bounds.maxY} onChange={(value) => changeBounds({ ...bounds, maxY: value })} />
          </div>
          {!boundaryIsValid && <p className="field-error">Максимальные координаты должны быть больше минимальных.</p>}
        </fieldset>

        <fieldset className="form-section">
          <legend>Сопоставление слоёв</legend>
          <p className="field-hint">
            Система предлагает назначение по названию и составу слоя. Проверьте предложения перед сохранением.
          </p>
          <div className="suggestion-summary">
            <div>
              <strong>{confidentSuggestionCount}</strong>
              <span>уверенных предложений</span>
            </div>
            <div className="suggestion-actions">
              <button className="button button-secondary" type="button" onClick={() => setAssistantIsOpen((current) => !current)}>
                {assistantIsOpen ? 'Скрыть помощника' : 'Помочь настроить слои'}
              </button>
              <button className="button button-secondary" type="button" onClick={applyConfidentSuggestions}>
                Применить уверенные
              </button>
            </div>
          </div>
          {assistantIsOpen && (
            <LayerAssistant
              groups={analysis.result.layer_groups}
              unresolvedLayerCount={unresolvedLayerCount}
              onApply={applyAssistantGroup}
              onClose={() => setAssistantIsOpen(false)}
              onPreview={setPreviewLayerName}
            />
          )}
          <div className="layer-tools">
            <label>
              <span>Поиск слоя</span>
              <input
                type="search"
                placeholder="Например: дорога, газ, дерево"
                value={layerSearch}
                onChange={(event) => setLayerSearch(event.target.value)}
              />
            </label>
            <label>
              <span>Показать</span>
              <select value={layerView} onChange={(event) => setLayerView(event.target.value as LayerView)}>
                <option value="active">Только используемые</option>
                <option value="all">Все слои</option>
                <option value="suggested">С предложением</option>
                <option value="uncertain">Требуют решения</option>
                <option value="configured">Учитываемые</option>
                <option value="ignored">Не учитываемые</option>
                <option value="unused">Пустые</option>
              </select>
            </label>
            <label>
              <span>Назначить показанным</span>
              <select
                value={bulkObjectType}
                onChange={(event) => setBulkObjectType(event.target.value as SemanticObjectType)}
              >
                {objectTypeOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
            </label>
            <button className="button button-secondary" type="button" onClick={applyBulkType} disabled={visibleLayers.length === 0}>
              Применить к показанным
            </button>
          </div>
          <div className="layer-tool-summary">
            <span>Показано {visibleLayers.length} из {analysis.result.layers.length}</span>
            <button className="text-button" type="button" onClick={() => applySuggestions(true)} disabled={visibleLayers.length === 0}>
              Применить предложения к показанным
            </button>
          </div>
          {includedLayers === 0 && (
            <article className="notice notice-warning mapping-notice">
              <span className="notice-marker" />
              <div>
                <strong>Все слои исключены из расчёта</strong>
                <p>План будет построен только внутри заданной границы, без учёта зданий, дорог и инженерных сетей.</p>
              </div>
            </article>
          )}
          {previewLayer && (
            <LayerPreview
              boundary={boundaryCoordinates}
              layer={previewLayer}
              scale={scale}
              onClose={() => setPreviewLayerName(null)}
            />
          )}
          <div className="layer-table" role="table" aria-label="Сопоставление слоёв DXF">
            <div className="layer-row layer-header" role="row">
              <span>Слой и состав</span><span>Назначение</span><span>Геометрия</span><span>Просмотр</span>
            </div>
            {visibleLayers.map(({ layer, index }) => {
              const mapping = layerMappings[index]
              return (
                <div className="layer-row" role="row" key={layer.name}>
                  <div>
                    <strong>{layer.name}</strong>
                    <small>{formatLayerCounts(layer)}</small>
                    {layer.suggestion && (
                      <span className={`layer-suggestion suggestion-${layer.suggestion.confidence}`} title={layer.suggestion.reason}>
                        {layer.suggestion.confidence === 'high' ? 'Уверенно' : 'Проверьте'}: {objectTypeLabel(layer.suggestion.object_type)}
                      </span>
                    )}
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
                  <button
                    className={previewLayerName === layer.name ? 'button button-secondary layer-preview-button selected' : 'button button-secondary layer-preview-button'}
                    type="button"
                    onClick={() => setPreviewLayerName(layer.name)}
                  >
                    Показать
                  </button>
                </div>
              )
            })}
            {visibleLayers.length === 0 && <p className="empty-layer-result">По заданному фильтру слои не найдены.</p>}
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

function rectangleRing(bounds: Bounds): [number, number][] {
  return [
    [bounds.minX, bounds.minY],
    [bounds.maxX, bounds.minY],
    [bounds.maxX, bounds.maxY],
    [bounds.minX, bounds.maxY],
    [bounds.minX, bounds.minY],
  ]
}

function boundsFromRing(coordinates: [number, number][]): Bounds {
  const xs = coordinates.map(([x]) => x)
  const ys = coordinates.map(([, y]) => y)
  return {
    minX: Math.min(...xs),
    minY: Math.min(...ys),
    maxX: Math.max(...xs),
    maxY: Math.max(...ys),
  }
}

function scaleBoundaryCandidate(candidate: AnalysisBoundaryCandidate, scale: number): AnalysisBoundaryCandidate {
  return {
    ...candidate,
    area_source_units: candidate.area_source_units * scale * scale,
    coordinates: candidate.coordinates.map(([x, y]) => [round(x * scale), round(y * scale)]),
  }
}

function formatArea(value: number) {
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 1 }).format(value)
}

function formatEntityCounts(counts: Record<string, number>) {
  return Object.entries(counts).map(([type, count]) => `${type}: ${count}`).join(', ') || 'пустой слой'
}

function formatLayerCounts(layer: AnalysisLayer) {
  if (layer.is_unused) return 'Слой объявлен, но объекты не найдены'
  const direct = layer.entity_count > 0
    ? `${layer.entity_count} на листах · ${formatEntityCounts(layer.entity_counts)}`
    : 'нет объектов на листах'
  const blocks = layer.block_entity_count > 0
    ? ` · ${layer.block_entity_count} в используемых блоках${formatBlockNames(layer.block_names)}`
    : ''
  return `${direct}${blocks}`
}

function formatBlockNames(names: string[]) {
  if (names.length === 0) return ''
  const shown = names.slice(0, 2).join(', ')
  return ` (${shown}${names.length > 2 ? ` и ещё ${names.length - 2}` : ''})`
}

function objectTypeLabel(value: SemanticObjectType) {
  return objectTypeOptions.find((option) => option.value === value)?.label ?? value
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
