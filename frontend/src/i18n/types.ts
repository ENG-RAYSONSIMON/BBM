import type { en } from './en'

/** Same keys as `en`, any string values: the shape every language must match. */
type DeepStringRecord<T> = { [K in keyof T]: T[K] extends string ? string : DeepStringRecord<T[K]> }

export type Dictionary = DeepStringRecord<typeof en>
