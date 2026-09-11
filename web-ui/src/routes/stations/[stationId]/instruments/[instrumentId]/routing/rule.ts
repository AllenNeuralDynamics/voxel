import type { FixedRoutingRule, RoutingRule, SplitRoutingRule } from '$lib/model';
import { displayName, trimFloat } from '$lib/utils';

export function cloneRule(rule: RoutingRule): RoutingRule {
  return { ...rule };
}

export function formatRuleSummary(rule: RoutingRule): string {
  if (rule.type === 'fixed') return `Fixed to ${displayName(rule.route)}`;
  const threshold = trimFloat(rule.threshold / 1000, 4);
  return `${rule.axis.toUpperCase()} split at ${threshold} mm · ${displayName(rule.lower)} → ${displayName(rule.upper)}`;
}

export function asFixedRule(rule: RoutingRule, routes: string[], resolved?: string): FixedRoutingRule {
  const route = rule.type === 'fixed' ? rule.route : resolved;
  return { type: 'fixed', route: route && routes.includes(route) ? route : (routes[0] ?? '') };
}

export function asSplitRule(rule: RoutingRule, routes: string[], threshold: number): SplitRoutingRule {
  if (rule.type === 'split') return cloneRule(rule) as SplitRoutingRule;
  const lower = routes.includes(rule.route) ? rule.route : (routes[0] ?? '');
  const upper = routes.find((route) => route !== lower) ?? '';
  return { type: 'split', axis: 'x', threshold, lower, upper };
}
