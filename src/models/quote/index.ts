/** The quote side: win probability, level learning and expected-profit pricing. README.md next to this file. */
export type { Belief, Term } from './belief.ts'
export type { Option, QuoteFlags, QuoteOptions, QuoteParams, QuotePriors } from './params.ts'
export { OPTIONS, quoteParams, readPriors } from './params.ts'
export type { QuoteDecision } from './price.ts'
export { bestQuote, trustBonus, winProb } from './price.ts'
export type { Pending, QuoteState } from './state.ts'
export { createQuoteState, dealerWeight, inWar, observe, recordQuote, requestsLeft, trustOf } from './state.ts'
export { driversNear } from './supply.ts'
