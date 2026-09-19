import type { CoordinateUnit, SemanticObjectType, TerritoryType } from './types'

export const coordinateUnitOptions: { value: CoordinateUnit; label: string; scale: number }[] = [
  { value: 'millimeter', label: 'Миллиметры', scale: 0.001 },
  { value: 'centimeter', label: 'Сантиметры', scale: 0.01 },
  { value: 'meter', label: 'Метры', scale: 1 },
  { value: 'kilometer', label: 'Километры', scale: 1000 },
  { value: 'inch', label: 'Дюймы', scale: 0.0254 },
  { value: 'foot', label: 'Футы', scale: 0.3048 },
  { value: 'yard', label: 'Ярды', scale: 0.9144 },
]

export const territoryOptions: { value: TerritoryType; label: string }[] = [
  { value: 'courtyard', label: 'Дворовая территория' },
  { value: 'preschool', label: 'Дошкольное учреждение' },
  { value: 'education_and_sport', label: 'Образование и спорт' },
  { value: 'healthcare', label: 'Здравоохранение' },
  { value: 'roads', label: 'Улицы и дороги' },
  { value: 'public_and_commercial', label: 'Общественно-деловая территория' },
  { value: 'parks_and_public_green', label: 'Парки и общественное озеленение' },
  { value: 'industrial_and_protection', label: 'Промышленная и защитная территория' },
]

export const objectTypeOptions: { value: SemanticObjectType; label: string }[] = [
  { value: 'ignore', label: 'Не учитывать' },
  { value: 'building', label: 'Здание' },
  { value: 'road', label: 'Дорога' },
  { value: 'utility_water', label: 'Водопровод' },
  { value: 'utility_sewer', label: 'Канализация' },
  { value: 'utility_gas', label: 'Газопровод' },
  { value: 'utility_power', label: 'Электросеть' },
  { value: 'existing_tree', label: 'Существующее дерево' },
  { value: 'existing_bush', label: 'Существующий кустарник' },
  { value: 'other_obstacle', label: 'Другое препятствие' },
]

export function guessCoordinateUnit(drawingUnit: string | null): CoordinateUnit {
  const units: Record<string, CoordinateUnit> = {
    mm: 'millimeter',
    cm: 'centimeter',
    m: 'meter',
    km: 'kilometer',
    in: 'inch',
    ft: 'foot',
    yd: 'yard',
  }
  return drawingUnit ? (units[drawingUnit.toLowerCase()] ?? 'meter') : 'meter'
}
