import { useMemo } from 'react'
import { useStore } from './store'
import { groupForPackage, packageGroupIndex } from './packageGroups'

// Header subtitle for a node: `Origin/Type`, e.g. `Perception/Camera`, so the
// node says where it ships from without opening the palette. The origin is the
// node's package group — the same name the Nodes and Templates tabs use — so a
// header, a palette group, and a template group always agree.
//
// Built-in nodes carry no package, so they fall back to their category
// (`Values/Text`, `Flow/Branch`) rather than the uninformative constant `Core`.
// Falls back to the bare type when /node-defs has not loaded yet.
export function useQualifiedTypeLabel(type: string): string {
  const packages = useStore(s => s.packages)
  const def = useStore(s => s.nodeDefs[type])
  const index = useMemo(() => packageGroupIndex(packages), [packages])

  if (!def) return type
  const origin = def.package ? groupForPackage(def.package, index).name : def.category
  return origin ? `${origin}/${type}` : type
}
