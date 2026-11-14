# atlas

Price by place. The competitor is cheap where drivers are many (capital-region deliveries accept about 1.13-1.19 x
list) and dear elsewhere (1.32-1.42). atlas keeps a price level (within_3_days, trust 0, x list) per delivery town
and a pooled one per region (capital by name, the rest by latitude band). A town's level gets weight n / (n +
`townPool`) over its region's. The prior is `priorCapital` in the capital region, elsewhere `priorOther` minus up to
`nearDrop` as the drivers near the delivery reach `nearFull`. Each outcome moves both levels by
x exp(eta x (won - `target`)), a stochastic-approximation step whose rest point is the `target` win rate; eta falls
from `eta0` to `etaMin`. A region that wins more than `outageRate` of at least `outageMin` quotes today (the
competitor is out) is priced x `outageBoost`. Options cost x `nextDay` / x `sameDay`, and x (1 + `trustStep` x trust).

Params: `priorCapital`, `priorOther`, `nearDrop`, `nearFull`, `nextDay`, `sameDay`, `target`, `eta0`, `etaMin`,
`etaDecay`, `townPool`, `minLevel`, `maxLevel`, `outageRate`, `outageMin`, `outageBoost`, `trustStep`, plus the base's.
