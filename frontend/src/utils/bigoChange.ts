import { growth } from './speedup';

/** A change before → after is worth showing only when both labels are known and differ. */
export const isBigoChange = (before?: string, after?: string): boolean =>
  !!before && !!after && before.trim() !== after.trim() && growth(before) !== null && growth(after) !== null;

/** Methods of `before` whose label in `after` is known and different, in the order of `before`. */
export const changedMethods = (
  before: Record<string, string>, after: Record<string, string>,
): [string, string, string][] =>
  Object.entries(before)
    .filter(([m, b]) => isBigoChange(b, after[m]))
    .map(([m, b]) => [m, b, after[m]]);
