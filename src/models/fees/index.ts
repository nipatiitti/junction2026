/** The fee and capacity models (src/BRIEF.md, Design 2-4): pure functions over plain data. README.md
 * says what each does, its prior, how it learns, and the flags. */
export { type Features, featuresOf, feeExtra } from './extras.ts'
export { acceptHazard } from './hazard.ts'
export { type FeeEvent, learn, replay } from './learn.ts'
export { type Feature, type FeeFlags, type FeeParams, type FeePriors, feeParams } from './params.ts'
export { costOf, type FeeCost, type FeeGig, type FeePlan, lambdaOf, muOf, planFees } from './plan.ts'
export { type FeeState, newFeeState } from './state.ts'
export { fewDriversNear, supply } from './supply.ts'
