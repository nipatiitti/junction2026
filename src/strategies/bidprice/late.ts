/** The late-risk table of src/params/late.json (fitted by analysis/late_risk.py on the saved level-8 weeks): the late
 * share of won orders by the slack between the win and the latest safe pickup, the drivers living near the pickup
 * and whether the win is in the evening. No request, dealer or town ids, so it carries to an unseen world. */
import { readFileSync } from 'node:fs'
import type { DeliveryOption, DriverProfile, PriceRequest } from '../../../vendor/spread-typescript/spread.ts'
import type { WorldMap } from '../../../vendor/spread-typescript/types.ts'
import { driversNear } from '../../models/quote/index.ts'
import { driveMinutes } from '../../ops/index.ts'

type Table = {
  slackEdgesHours: number[]
  nearKm: number
  fewDrivers: number
  eveningHours: [number, number]
  base: number
  cells: Record<string, number>
}

const TABLE = JSON.parse(readFileSync(new URL('../../params/late.json', import.meta.url), 'utf8')) as Table

export type LateRisk = { table: Table; near: Record<string, number> }

export function newLateRisk(roster: DriverProfile[], map: WorldMap): LateRisk {
  return { table: TABLE, near: driversNear(roster, map, TABLE.nearKm) }
}

/** The predicted late share of `option` won at `now`; the base rate for a cell the weeks never saw. */
export function lateRiskOf(
  risk: LateRisk,
  request: PriceRequest,
  option: DeliveryOption,
  now: number,
  map: WorldMap,
): number {
  const { table, near } = risk
  const slackHours = (option.deadline - driveMinutes(map, request.legs) - now) / 60
  const s = table.slackEdgesHours.filter((edge) => slackHours >= edge).length
  const pickup = request.legs[0]?.pickup.placeId ?? ''
  const few = (near[pickup] ?? 0) <= table.fewDrivers ? 'few' : 'many'
  const hour = Math.floor((now % 1440) / 60)
  const eve = hour >= table.eveningHours[0] && hour < table.eveningHours[1] ? 'eve' : 'day'
  return table.cells[`s${s}/${few}/${eve}`] ?? table.base
}
