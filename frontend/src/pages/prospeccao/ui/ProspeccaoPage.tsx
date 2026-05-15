import { ProspectingLegacy } from '../legacy/ProspectingLegacy'

/**
 * Wraps the legacy Prospecting screen until it gets rebuilt on top of the new
 * design system. New shell handles navigation/topbar; the legacy view owns its
 * own filter panel and results layout.
 */
export function ProspeccaoPage() {
  return <ProspectingLegacy />
}
