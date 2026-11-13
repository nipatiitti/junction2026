/** What dispatch.py knows about serving an order, as pure functions of plain data: see README.md next to this file. */
export { DAY, HOUR, type Hours } from './calendar.ts'
export { type Features, features, NO_FEATURES } from './features.ts'
export {
  FIRST_TRY,
  type GigShape,
  gigShape,
  postAt,
  type Retry,
  retryAfter,
  type Setback,
  undelivered,
  withoutWindows,
} from './gig.ts'
export { type Context, driveMinutes, minutes } from './map.ts'
export { earliestPickup, NO_FACTS, type NoteFacts, readNote } from './note.ts'
export { canServe, pickOption, type Service } from './serve.ts'
export { pickupWindow, type Snowfall } from './windows.ts'
