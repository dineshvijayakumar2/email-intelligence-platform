/**
 * Global risk/health visual pattern.
 *
 * Use these at the layout level (card borders, row backgrounds)
 * to set the emotional tone of the entire section.
 * Never define risk colors per-component — always use these.
 */

export const riskBorder = {
  'at_risk': 'border-l-4 border-l-risk bg-risk-subtle',
  'churning': 'border-l-4 border-l-risk bg-risk-subtle',
  'declining': 'border-l-4 border-l-warning bg-warning-subtle',
  'active': 'border-l-4 border-l-success bg-success-subtle',
  'healthy': 'border-l-4 border-l-success bg-success-subtle',
  'quiet': 'border-l-4 border-l-slate-300',
  'unknown': '',
} as const;

export const riskText = {
  'at_risk': 'text-risk',
  'churning': 'text-risk',
  'declining': 'text-warning',
  'active': 'text-success',
  'healthy': 'text-success',
  'quiet': 'text-slate-500',
  'unknown': 'text-slate-400',
} as const;

export type RiskLevel = keyof typeof riskBorder;

/**
 * Get the risk border class for a given engagement status.
 * Used on customer cards, thread rows, table rows.
 */
export function getRiskClass(status?: string | null): string {
  return riskBorder[(status as RiskLevel) || 'unknown'] || '';
}

export function getRiskTextClass(status?: string | null): string {
  return riskText[(status as RiskLevel) || 'unknown'] || 'text-slate-400';
}
