import type { MixPreset, Priorities, PriorityMixEntry, PriorityPresetWeights } from "@/types";
import { PRIORITY_KEYS } from "@/types";

export const DEFAULT_CUSTOM_PRIORITIES: Priorities = {
  safetyWeight: 0.5,
  scienceWeight: 0.5,
  distanceWeight: 0.5,
  walkingDifficultyWeight: 0.5,
  returnWeight: 0.5,
  environmentWeight: 0.5,
  roverPathWeight: 0.5,
};

/** CUSTOM submissions are blocked when every weight is zero. */
export const allPrioritiesZero = (p: Priorities) => PRIORITY_KEYS.every((k) => p[k] === 0);

/** Share of the total for display only (the API normalises the same way); the submitted values are unchanged. */
export function shareOf(p: Priorities, k: keyof Priorities): number | null {
  const total = PRIORITY_KEYS.reduce((s, x) => s + p[x], 0);
  return total > 0 ? p[k] / total : null;
}

export const mixTotal = (mix: Partial<Record<MixPreset, number>>) =>
  Object.values(mix).reduce<number>((s, v) => s + (v ?? 0), 0);

/** RedGrid API Contract: weights = Σ (percent ÷ 100 × preset weights). Shown live; the backend repeats it on save. */
export function mixWeights(
  mix: Partial<Record<MixPreset, number>>,
  presets: PriorityPresetWeights[],
): Priorities | null {
  const entries = Object.entries(mix).filter(([, v]) => (v ?? 0) > 0) as [MixPreset, number][];
  if (!entries.length) return null;
  const acc = Object.fromEntries(PRIORITY_KEYS.map((k) => [k, 0])) as unknown as Priorities;
  for (const [key, pct] of entries) {
    const w = presets.find((p) => p.key === key)?.weights;
    if (!w) return null;
    PRIORITY_KEYS.forEach((k) => (acc[k] += (pct / 100) * w[k]));
  }
  PRIORITY_KEYS.forEach((k) => (acc[k] = Math.round(acc[k] * 1e6) / 1e6));
  return acc;
}

export function mixEntries(mix: Partial<Record<MixPreset, number>>): PriorityMixEntry[] {
  return (Object.entries(mix) as [MixPreset, number][])
    .filter(([, v]) => v > 0)
    .map(([presetKey, percent]) => ({ presetKey, percent }));
}
