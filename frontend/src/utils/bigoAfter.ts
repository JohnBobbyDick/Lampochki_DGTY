import type { AiAnswer, AiPatch } from '../store/useStore';
import type { Defect } from '../types';
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

/**
 * Rule-based estimate without an LLM: a method's Big O after fixing every defect that sets it
 * (defect.bigO equals the method's label). Known only if each such defect has an expected bigOAfter;
 * the result is the worst of those.
 */
export const staticBigoAfter = (bigo: Record<string, string>, defects: Defect[]): Record<string, string> => {
  const out: Record<string, string> = {};
  for (const [m, label] of Object.entries(bigo)) {
    const dominant = defects.filter((d) => d.method === m && d.bigO === label);
    if (!dominant.length || dominant.some((d) => !d.bigOAfter || growth(d.bigOAfter) === null)) continue;
    out[m] = dominant.reduce((worst, d) => (growth(d.bigOAfter!)! > growth(worst)! ? d.bigOAfter! : worst), dominant[0].bigOAfter!);
  }
  return out;
};
