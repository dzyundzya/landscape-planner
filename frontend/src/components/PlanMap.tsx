import { useEffect, useRef } from 'react'
import Feature from 'ol/Feature'
import Map from 'ol/Map'
import View from 'ol/View'
import GeoJSON from 'ol/format/GeoJSON'
import Modify from 'ol/interaction/Modify'
import Select from 'ol/interaction/Select'
import VectorLayer from 'ol/layer/Vector'
import Projection from 'ol/proj/Projection'
import VectorSource from 'ol/source/Vector'
import { Circle as CircleStyle, Fill, Stroke, Style } from 'ol/style'
import type { FeatureLike } from 'ol/Feature'
import type Geometry from 'ol/geom/Geometry'
import type Point from 'ol/geom/Point'

import type { GeoJsonGeometry, PlanPreview, PlantingType } from '../types'

type Props = {
  preview: PlanPreview
  selectedPlantingId: string | null
  onSelectPlanting: (plantingId: string | null) => void
  onMovePlanting: (plantingId: string, x: number, y: number) => void
}

const projection = new Projection({ code: 'GREENPLAN:LOCAL', units: 'm' })
const geoJson = new GeoJSON()

export function PlanMap({ preview, selectedPlantingId, onSelectPlanting, onMovePlanting }: Props) {
  const targetRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!targetRef.current) return

    const boundarySource = new VectorSource({ features: [geometryFeature(preview.boundary)] })
    const objectSource = new VectorSource({
      features: preview.objects.map((item) => {
        const feature = geometryFeature(item.geometry)
        feature.setProperties({ objectType: item.object_type, sourceObjectId: item.source_object_id })
        return feature
      }),
    })
    const restrictionSource = new VectorSource({
      features: preview.restrictions.map((item) => {
        const feature = geometryFeature(item.geometry)
        feature.setProperties({ plantingType: item.planting_type, ruleId: item.rule_id })
        return feature
      }),
    })
    const plantingSource = new VectorSource({
      features: preview.plantings.map((planting) => {
        const feature = geometryFeature({
          type: 'Point',
          coordinates: [Number(planting.x_m), Number(planting.y_m)],
        })
        feature.setId(planting.public_id)
        feature.setProperties({ plantingType: planting.type, species: planting.species })
        return feature
      }),
    })

    const boundaryLayer = new VectorLayer({ source: boundarySource, style: boundaryStyle })
    const restrictionLayer = new VectorLayer({ source: restrictionSource, style: restrictionStyle })
    const objectLayer = new VectorLayer({ source: objectSource, style: objectStyle })
    const plantingLayer = new VectorLayer({ source: plantingSource, style: plantingStyle })
    const map = new Map({
      target: targetRef.current,
      layers: [boundaryLayer, restrictionLayer, objectLayer, plantingLayer],
      view: new View({ projection, center: [0, 0], zoom: 2 }),
    })

    const extent = boundarySource.getExtent()
    if (extent.every(Number.isFinite)) {
      map.getView().fit(extent, { padding: [36, 36, 36, 36], maxZoom: 20 })
    }

    const select = new Select({ layers: [plantingLayer], hitTolerance: 8 })
    const modify = new Modify({ features: select.getFeatures(), pixelTolerance: 12 })
    map.addInteraction(select)
    map.addInteraction(modify)

    const initiallySelected = selectedPlantingId ? plantingSource.getFeatureById(selectedPlantingId) : null
    if (initiallySelected) select.getFeatures().push(initiallySelected)

    select.on('select', (event) => {
      const id = event.selected[0]?.getId()
      onSelectPlanting(typeof id === 'string' ? id : null)
    })
    modify.on('modifyend', (event) => {
      const feature = event.features.item(0)
      const id = feature?.getId()
      const coordinates = (feature?.getGeometry() as Point | undefined)?.getCoordinates()
      if (typeof id === 'string' && coordinates) {
        onMovePlanting(id, coordinates[0], coordinates[1])
      }
    })

    return () => map.setTarget(undefined)
  }, [preview, selectedPlantingId, onMovePlanting, onSelectPlanting])

  return (
    <div className="map-frame">
      <div className="plan-map" ref={targetRef} aria-label="Диагностическая карта плана" />
      <div className="map-legend" aria-label="Условные обозначения">
        <span><i className="legend-tree" />Деревья</span>
        <span><i className="legend-bush" />Кустарники</span>
        <span><i className="legend-object" />Объекты DXF</span>
        <span><i className="legend-zone" />Ограничения</span>
      </div>
      <p className="map-hint">Выберите посадку и перетащите её. Новая позиция сохранится только после проверки backend.</p>
    </div>
  )
}

function geometryFeature(geometry: GeoJsonGeometry): Feature<Geometry> {
  return geoJson.readFeature(
    { type: 'Feature', properties: {}, geometry },
    { dataProjection: projection, featureProjection: projection },
  ) as Feature<Geometry>
}

const boundaryStyle = new Style({
  stroke: new Stroke({ color: '#173f35', width: 2.5 }),
  fill: new Fill({ color: 'rgba(248, 247, 240, 0.7)' }),
})

const restrictionStyle = (feature: FeatureLike) => {
  const plantingType = feature.get('plantingType') as PlantingType
  return new Style({
    stroke: new Stroke({ color: plantingType === 'tree' ? '#c5825a' : '#a789bc', width: 1 }),
    fill: new Fill({ color: plantingType === 'tree' ? 'rgba(197, 130, 90, 0.14)' : 'rgba(167, 137, 188, 0.12)' }),
  })
}

const objectColors: Record<string, string> = {
  building: '#52666f',
  road: '#8a7c67',
  utility_water: '#4389b7',
  utility_sewer: '#755b49',
  utility_gas: '#d09b32',
  utility_power: '#b9584e',
  existing_tree: '#3b7554',
  existing_bush: '#71965d',
  other_obstacle: '#626b67',
}

const objectStyle = (feature: FeatureLike) => {
  const color = objectColors[String(feature.get('objectType'))] ?? '#626b67'
  return new Style({
    stroke: new Stroke({ color, width: 2 }),
    fill: new Fill({ color: `${color}24` }),
  })
}

const plantingStyle = (feature: FeatureLike) => {
  const isTree = feature.get('plantingType') === 'tree'
  return new Style({
    image: new CircleStyle({
      radius: isTree ? 7 : 5,
      fill: new Fill({ color: isTree ? '#3f7a54' : '#8aa56f' }),
      stroke: new Stroke({ color: '#fffef9', width: 2 }),
    }),
  })
}
