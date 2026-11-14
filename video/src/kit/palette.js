import * as THREE from 'three'

// Named colours shared by every view.
export const C = {
  snow: '#eef4fa',
  asphalt: '#3a3e45',
  line: '#e6e6e6',
  metal: '#7d8590',
  pine: '#2f6b46',
  pineDark: '#24563a',
  trunk: '#6b4a32',
  wall: '#e9dfcc',
  roof: '#6d7480',
  glass: '#9fd3f0',
  glassDark: '#26323f',
  ourRed: '#e8262b',
  taxiYellow: '#f5c518',
  black: '#1d1f24',
  skin: '#f1c7a1',
  skinTan: '#d9a074',
  hoodieRed: '#d6262c',
  denim: '#3d5a8a',
  leather: '#4a2f22',
  gold: '#e8b923',
  hair: '#3a2a1e',
  mouth: '#6b2f2a',
  bear: '#f2f4f6',
}

/** The colour times k (k < 1 is darker), as a CSS hex string. */
export const shade = (hex, k) => `#${new THREE.Color(hex).multiplyScalar(k).getHexString()}`
