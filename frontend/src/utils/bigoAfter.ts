import type { AiAnswer, AiPatch } from '../store/useStore';
import { fragmentPresent } from './fragment';
import { growth } from './speedup';

/** Valid, still-applicable patches from all answers (answer.patch and items[].patch), deduplicated. */
export const applicablePatches = (code: string, answers: (AiAnswer | null)[]): AiPatch[] => {
  const seen = new Set<string>();
  const out: AiPatch[] = [];
  for (const a of answers) {
    if (!a) continue;
    const all = [a.patch, ...(a.items ?? []).map((it) => it.patch)];
    for (const p of all) {
      if (!p || !p.valid || !fragmentPresent(code, p.oldCode)) continue;
      const key = `${p.oldCode}\u0000${p.newCode}`;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(p);
    }
  }
  return out;
};

/** Per method, the best (lowest growth) bigoAfter among patches; unknown labels lose to known ones. */
export const bestSingle = (patches: AiPatch[]): Record<string, string> => {
  const out: Record<string, string> = {};
  for (const p of patches) {
    for (const [m, label] of Object.entries(p.bigoAfter ?? {})) {
      const cur = out[m];
      if (cur === undefined) { out[m] = label; continue; }
      const g = growth(label);
      const gc = growth(cur);
      if (g !== null && (gc === null || g < gc)) out[m] = label;
    }
  }
  return out;
};

export const bigoAfter = (
  patches: AiPatch[],
  combined: Record<string, string> | null,
): Record<string, string> => {
  if (patches.length === 0) return {};
  if (patches.length === 1) return patches[0].bigoAfter ?? {};
  return combined ?? bestSingle(patches);
};
