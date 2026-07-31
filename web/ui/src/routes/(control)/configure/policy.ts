import type { FixedOpticalRoutingPolicy, OpticalRoutingPolicy, SplitOpticalRoutingPolicy } from '$lib/model';
import { sanitizeString, trimFloat } from '$lib/utils';

export function clonePolicy(policy: OpticalRoutingPolicy): OpticalRoutingPolicy {
  return { ...policy };
}

export function formatPolicySummary(policy: OpticalRoutingPolicy): string {
  if (policy.type === 'fixed') return `Fixed to ${sanitizeString(policy.route)}`;
  const threshold = trimFloat(policy.threshold / 1000, 4);
  return `${policy.axis.toUpperCase()} split at ${threshold} mm · ${sanitizeString(policy.lower)} → ${sanitizeString(policy.upper)}`;
}

export function asFixedPolicy(
  policy: OpticalRoutingPolicy,
  routes: string[],
  target?: string
): FixedOpticalRoutingPolicy {
  const route = policy.type === 'fixed' ? policy.route : target;
  return { type: 'fixed', route: route && routes.includes(route) ? route : (routes[0] ?? '') };
}

export function asSplitPolicy(
  policy: OpticalRoutingPolicy,
  routes: string[],
  threshold: number
): SplitOpticalRoutingPolicy {
  if (policy.type === 'split') return clonePolicy(policy) as SplitOpticalRoutingPolicy;
  const lower = routes.includes(policy.route) ? policy.route : (routes[0] ?? '');
  const upper = routes.find((route) => route !== lower) ?? '';
  return { type: 'split', axis: 'x', threshold, lower, upper };
}
