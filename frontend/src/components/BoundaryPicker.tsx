import { useEffect, useRef } from 'react'

import Feature from 'ol/Feature'
import Map from 'ol/Map'
import View from 'ol/View'
import Polygon from 'ol/geom/Polygon'
import VectorLayer from 'ol/layer/Vector'
import VectorSource from 'ol/source/Vector'
import Fill from 'ol/style/Fill'
import Stroke from 'ol/style/Stroke'
import Style from 'ol/style/Style'

import type { AnalysisBoundaryCandidate } from '../types'

type Props = {
  candidates: AnalysisBoundaryCandidate[]
  selectedId: string | null
  onSelect: (candidate: AnalysisBoundaryCandidate) => void
}

export function BoundaryPicker({ candidates, selectedId, onSelect }: Props) {
  const targetRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!targetRef.current || candidates.length === 0) return

    const features = candidates.map((candidate) => {
      const feature = new Feature({ geometry: new Polygon([candidate.coordinates]), candidate })
      feature.setId(candidate.id)
      return feature
    })
    const source = new VectorSource({ features })
    const layer = new VectorLayer({
      source,
      style: (feature) => feature.getId() === selectedId ? selectedStyle : candidateStyle,
    })
    const map = new Map({
      target: targetRef.current,
      layers: [layer],
      view: new View({ center: [0, 0], zoom: 1 }),
      controls: [],
    })
    const extent = source.getExtent()
    if (extent.every(Number.isFinite)) map.getView().fit(extent, { padding: [24, 24, 24, 24], maxZoom: 18 })
    map.on('singleclick', (event) => {
      const feature = map.forEachFeatureAtPixel(event.pixel, (item) => item, { hitTolerance: 5 })
      const candidate = feature?.get('candidate') as AnalysisBoundaryCandidate | undefined
      if (candidate) onSelect(candidate)
    })

    return () => map.setTarget(undefined)
  }, [candidates, onSelect, selectedId])

  return <div className="boundary-picker" ref={targetRef} aria-label="Выбор границы участка на схеме" />
}

const candidateStyle = new Style({
  fill: new Fill({ color: 'rgba(131, 166, 108, 0.08)' }),
  stroke: new Stroke({ color: 'rgba(82, 102, 111, 0.75)', width: 1.2 }),
})

const selectedStyle = new Style({
  fill: new Fill({ color: 'rgba(131, 166, 108, 0.28)' }),
  stroke: new Stroke({ color: '#173f35', width: 3 }),
})
