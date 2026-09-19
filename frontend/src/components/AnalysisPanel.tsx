import type { Analysis } from '../types'

type Props = {
  analysis: Analysis
}

const severityLabels = {
  info: 'Информация',
  warning: 'Предупреждение',
  blocking: 'Блокирует проверку',
}

export function AnalysisPanel({ analysis }: Props) {
  const { result } = analysis
  const entities = Object.entries(result.entity_counts).sort(([left], [right]) => left.localeCompare(right))

  return (
    <section className="panel analysis-panel" aria-labelledby="analysis-title">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Шаг 3</p>
          <h2 id="analysis-title">Результат анализа</h2>
        </div>
        <span className="status-pill status-success">Анализ завершён</span>
      </div>

      <div className="metric-grid">
        <Metric label="Версия DXF" value={result.dxf_version ?? 'Не определена'} />
        <Metric label="Единицы чертежа" value={result.drawing_units ?? 'Не заданы'} attention={!result.drawing_units} />
        <Metric label="Слоёв" value={String(result.layers.length)} />
        <Metric label="Сущностей" value={String(Object.values(result.entity_counts).reduce((sum, value) => sum + value, 0))} />
        <Metric label="Блоков" value={String(Object.keys(result.blocks).length)} />
        <Metric label="Подписей" value={String(result.labels_count)} />
      </div>

      {result.warnings.length > 0 && (
        <div className="warning-stack" aria-label="Предупреждения анализа">
          {result.warnings.map((warning) => (
            <article className={`notice notice-${warning.severity}`} key={warning.code}>
              <span className="notice-marker" aria-hidden="true" />
              <div>
                <strong>{severityLabels[warning.severity]}</strong>
                <p>{warning.message}</p>
              </div>
            </article>
          ))}
        </div>
      )}

      <div className="analysis-columns">
        <div>
          <h3>Состав чертежа</h3>
          <div className="chip-list">
            {entities.map(([name, count]) => (
              <span className="data-chip" key={name}>
                {name} <b>{count}</b>
              </span>
            ))}
          </div>
        </div>
        <div>
          <h3>Границы modelspace</h3>
          {result.bounds ? (
            <dl className="bounds-list">
              <div><dt>min X</dt><dd>{formatCoordinate(result.bounds.min_x)}</dd></div>
              <div><dt>min Y</dt><dd>{formatCoordinate(result.bounds.min_y)}</dd></div>
              <div><dt>max X</dt><dd>{formatCoordinate(result.bounds.max_x)}</dd></div>
              <div><dt>max Y</dt><dd>{formatCoordinate(result.bounds.max_y)}</dd></div>
            </dl>
          ) : (
            <p className="muted">Границы не определены. Их нужно ввести вручную ниже.</p>
          )}
        </div>
      </div>
    </section>
  )
}

function Metric({ label, value, attention = false }: { label: string; value: string; attention?: boolean }) {
  return (
    <div className={`metric ${attention ? 'metric-attention' : ''}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}

function formatCoordinate(value: number) {
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 3 }).format(value)
}
