import type { BnPackage } from './types'

export interface PackageGroup {
  name: string
  color: string
}

// Built-in nodes and templates ship with Blacknode itself and carry no package.
export const CORE_GROUP: PackageGroup = { name: 'Core', color: '#6366f1' }

// 'blacknode-hardware-drivers' → 'Hardware Drivers'.
export function packageDisplayName(pkg: string): string {
  return titleCase(pkg.replace(/^blacknode-/, ''))
}

// Component slugs that do not title-case into something readable.
const WORDS: Record<string, string> = {
  can: 'CAN',
  cuda: 'CUDA',
  hdf5: 'HDF5',
  imu: 'IMU',
  nav2: 'Nav2',
  ros2: 'ROS 2',
  slam: 'SLAM',
  stm32: 'STM32',
  tf: 'TF',
  usb: 'USB',
  vlm: 'VLM',
}

// 'command-arbitration' → 'Command Arbitration'; 'vlm' → 'VLM'.
export function componentDisplayName(component: string): string {
  return titleCase(component)
}

function titleCase(slug: string): string {
  return slug
    .split('-')
    .map(word => WORDS[word] ?? word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

// Mirrors _template_sources() in editor-server/server.py: a package presents
// itself under the first category its manifest declares, so the Nodes tab, the
// Templates tab, and node headers all name and color a package the same way.
// Packages that declare no categories fall back to their prettified name.
export function packageGroup(pkg: BnPackage): PackageGroup {
  const [name, color] = Object.entries(pkg.categories ?? {})[0] ?? []
  return name
    ? { name, color: color || CORE_GROUP.color }
    : { name: packageDisplayName(pkg.name), color: CORE_GROUP.color }
}

export function packageGroupIndex(packages: BnPackage[]): Record<string, PackageGroup> {
  const index: Record<string, PackageGroup> = {}
  for (const pkg of packages) index[pkg.name] = packageGroup(pkg)
  return index
}

// The group a node type belongs to — its package, or Core when it is built in.
// `packageName` is '' for built-ins; an unknown package still gets a readable
// name so a node never lands in an untitled bucket.
export function groupForPackage(
  packageName: string,
  index: Record<string, PackageGroup>,
): PackageGroup {
  if (!packageName) return CORE_GROUP
  return index[packageName] ?? { name: packageDisplayName(packageName), color: CORE_GROUP.color }
}
