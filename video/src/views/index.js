import card from './card.js'
import end from './end-bear.js'
import scene1 from './scene1-speed.js'
import scene2 from './scene2-money.js'
import scene3 from './scene3-taxi.js'
import scene4 from './scene4-decline.js'

/**
 * Every kind of view, by the name that timeline.js uses. A view exports { build(segment) }, which returns
 * { scene, camera, update(t), overlay(g, t) }: update sets the 3D picture for the local time t, overlay draws on top.
 */
export const VIEWS = { card, scene1, scene2, scene3, scene4, end }
