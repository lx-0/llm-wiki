import { describe, expect, it } from 'vitest';
import { layoutFailures, restHeightFailure } from './gates.cjs';

const STRICT = new Set(['index']);

describe('restHeightFailure', () => {
  const surface = { page: 'index', restHeight: { state: 'fresh', max: 640 } };

  it('fails when the resting state asks for more than the clamp', () => {
    expect(restHeightFailure(surface, 'light', 'fresh', 641)).toBe(
      'index-light-fresh requests 641 px at rest (max 640)',
    );
  });

  it('passes at the clamp, in other states, and for surfaces without a budget', () => {
    expect(restHeightFailure(surface, 'dark', 'fresh', 640)).toBeNull();
    expect(restHeightFailure(surface, 'light', 'asked', 900)).toBeNull();
    expect(restHeightFailure({ page: 'browse' }, 'light', 'fresh', 900)).toBeNull();
    expect(restHeightFailure(surface, 'light', 'fresh', null)).toBeNull();
  });
});

describe('layoutFailures', () => {
  it('fails strict pages on any finding and only reports the rest', () => {
    const layout = { overlaps: ['a <> b'], offscreen: [], clipped: ['c'] };
    expect(layoutFailures(STRICT, 'index', layout)).toEqual(['a <> b', 'c']);
    expect(layoutFailures(STRICT, 'legacy', layout)).toEqual([]);
  });
});
