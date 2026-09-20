import { useEffect, useRef } from 'react'

import Feature from 'ol/Feature'
import Map from 'ol/Map'
import View from 'ol/View'
import LineString from 'ol/geom/LineString'
import Polygon from 'ol/geom/Polygon'
import VectorLayer from 'ol/layer/Vector'
import VectorSource from 'ol/source/Vector'
import Fill from 'ol/style/Fill'
import Stroke from 'ol/style/Stroke'
import Style from 'ol/style/Style'

import type { AnalysisLayer } from '../types'

type Props = {
  boundary: [number, number][]
  layer: AnalysisLayer
  scale: number
  onClose: () => void
}

export function LayerPreview({ boundary, layer, scale, onClose }: Props) {
  const targetRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!targetRef.current || layer.preview.length === 0) return

    const geometryFeatures = layer.preview.map((item) => {
      const coordinates = item.coordinates.map(([x, y]) => [x * scale, y * scale])
      const geometry = item.closed && coordinates.length >= 4
        ? new Polygon([closeRing(coordinates)])
        : new LineString(coordinates)
      return new Feature({ geometry })
    })
    const geometrySource = new VectorSource({ features: geometryFeatures })
    const layers: VectorLayer<VectorSource>[] = []
    if (boundary.length >= 4) {
      layers.push(new VectorLayer({
        source: new VectorSource({ features: [new Feature({ geometry: new Polygon([closeRing(boundary)]) })] }),
        style: boundaryStyle,
      }))
    }
    layers.push(new VectorLayer({ source: geometrySource, style: layerStyle }))

    const map = new Map({
      target: targetRef.current,
      layers,
      view: new View({ center: [0, 0], zoom: 1 }),
      controls: [],
    })
    const extent = geometrySource.getExtent()
    if (extent.every(Number.isFinite)) map.getView().fit(extent, { padding: [28, 28, 28, 28], maxZoom: 19 })

    return () => map.setTarget(undefined)
  }, [boundary, layer, scale])

  return (
    <article className="layer-preview-panel">
      <div className="layer-preview-heading">
        <div>
          <span>Предпросмотр слоя</span>
          <strong title={layer.name}>{layer.name}</strong>
        </div>
        <button className="text-button" type="button" onClick={onClose}>Закрыть</button>
      </div>
      {layer.preview.length > 0 ? (
        <>
          <div className="layer-preview-map" ref={targetRef} aria-label={`Геометрия слоя ${layer.name}`} />
          <p>
            Показано объектов: {layer.preview.length}.
            {layer.preview_truncated ? ' Это ограниченный диагностический фрагмент слоя.' : ' Все поддерживаемые объекты слоя помещены в preview.'}
          </p>
        </>
      ) : (
        <div className="layer-preview-empty">
          Поддерживаемой линейной геометрии для просмотра нет. Тексты, размеры, штриховки и proxy-объекты здесь не отображаются.
        </div>
      )}
    </article>
  )
}

function closeRing(coordinates: number[][]): number[][] {
  const first = coordinates[0]
  const last = coordinates[coordinates.length - 1]
  if (first[0] === last[0] && first[1] === last[1]) return coordinates
  return [...coordinates, first]
}

const layerStyle = new Style({
  fill: new Fill({ color: 'rgba(63, 122, 84, 0.22)' }),
  stroke: new Stroke({ color: '#173f35', width: 2.2 }),
})

const boundaryStyle = new Style({
  fill: new Fill({ color: 'rgba(82, 102, 111, 0.04)' }),
  stroke: new Stroke({ color: 'rgba(82, 102, 111, 0.55)', width: 1.2, lineDash: [6, 5] }),
})
