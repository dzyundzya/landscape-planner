import { useState } from 'react'

import { objectTypeOptions } from '../constants'
import type { AnalysisLayerGroup, SemanticObjectType } from '../types'

type Props = {
  groups: AnalysisLayerGroup[]
  unresolvedLayerCount: number
  onApply: (group: AnalysisLayerGroup, objectType: SemanticObjectType, geometryRole: 'line' | 'area') => void
  onClose: () => void
  onPreview: (layerName: string) => void
}

export function LayerAssistant({ groups, unresolvedLayerCount, onApply, onClose, onPreview }: Props) {
  const suggestedCount = groups.filter((group) => group.kind === 'suggested').length
  const familyCount = groups.filter((group) => group.kind === 'family').length

  return (
    <section className="layer-assistant" aria-labelledby="layer-assistant-title">
      <div className="layer-assistant-heading">
        <div>
          <span>Помощник по слоям</span>
          <h3 id="layer-assistant-title">Проверьте группы вместо сотен строк</h3>
        </div>
        <button className="text-button" type="button" onClick={onClose}>Закрыть</button>
      </div>
      <p className="layer-assistant-intro">
        Помощник группирует слои по одинаковой рекомендации или похожему имени. Он ничего не подтверждает сам:
        выбранное назначение применяется только после нажатия кнопки.
      </p>
      <div className="layer-assistant-summary">
        <div><strong>{suggestedCount}</strong><span>групп с рекомендацией</span></div>
        <div><strong>{familyCount}</strong><span>неизвестных семейств</span></div>
        <div><strong>{unresolvedLayerCount}</strong><span>слоёв без уверенного решения</span></div>
      </div>
      {groups.length > 0 ? (
        <div className="layer-assistant-groups">
          {groups.map((group) => (
            <LayerAssistantGroup group={group} key={group.id} onApply={onApply} onPreview={onPreview} />
          ))}
        </div>
      ) : (
        <p className="layer-assistant-empty">Подходящих групп не найдено. Проверяйте активные слои по одному через preview.</p>
      )}
    </section>
  )
}

function LayerAssistantGroup({
  group,
  onApply,
  onPreview,
}: {
  group: AnalysisLayerGroup
  onApply: Props['onApply']
  onPreview: Props['onPreview']
}) {
  const [objectType, setObjectType] = useState<SemanticObjectType>(group.suggestion?.object_type ?? 'ignore')
  const [geometryRole, setGeometryRole] = useState<'line' | 'area'>(group.suggestion?.geometry_role ?? 'line')
  const title = group.suggestion
    ? `${objectTypeLabel(group.suggestion.object_type)} · ${group.suggestion.confidence === 'high' ? 'высокая уверенность' : 'нужно проверить'}`
    : group.label

  return (
    <article className="layer-assistant-group">
      <div className="layer-assistant-group-heading">
        <div>
          <strong>{title}</strong>
          <small>{group.layer_names.length} {pluralizeLayers(group.layer_names.length)}</small>
        </div>
        <span className={group.suggestion ? `layer-suggestion suggestion-${group.suggestion.confidence}` : 'layer-suggestion suggestion-unknown'}>
          {group.suggestion ? 'Есть рекомендация' : 'Назначение неизвестно'}
        </span>
      </div>
      <p>{group.reason}</p>
      <div className="layer-assistant-names">
        {group.layer_names.slice(0, 8).map((name) => (
          <button type="button" key={name} title={name} onClick={() => onPreview(name)}>{shortLayerName(name)}</button>
        ))}
        {group.layer_names.length > 8 && <span>ещё {group.layer_names.length - 8}</span>}
      </div>
      <div className="layer-assistant-actions">
        <label>
          <span>Назначение группы</span>
          <select value={objectType} onChange={(event) => setObjectType(event.target.value as SemanticObjectType)}>
            {objectTypeOptions.map((option) => <option value={option.value} key={option.value}>{option.label}</option>)}
          </select>
        </label>
        <label>
          <span>Геометрия</span>
          <select value={geometryRole} disabled={objectType === 'ignore'} onChange={(event) => setGeometryRole(event.target.value as 'line' | 'area')}>
            <option value="line">Линия</option>
            <option value="area">Площадной объект</option>
          </select>
        </label>
        <button
          className="button button-secondary"
          type="button"
          disabled={objectType === 'ignore'}
          onClick={() => onApply(group, objectType, geometryRole)}
        >
          Применить к группе
        </button>
      </div>
    </article>
  )
}

function shortLayerName(name: string) {
  const parts = name.split('$0$')
  return parts[parts.length - 1] ?? name
}

function objectTypeLabel(value: SemanticObjectType) {
  return objectTypeOptions.find((option) => option.value === value)?.label ?? value
}

function pluralizeLayers(count: number) {
  const mod100 = count % 100
  const mod10 = count % 10
  if (mod100 >= 11 && mod100 <= 14) return 'слоёв'
  if (mod10 === 1) return 'слой'
  if (mod10 >= 2 && mod10 <= 4) return 'слоя'
  return 'слоёв'
}
