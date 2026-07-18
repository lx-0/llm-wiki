import { describe, it, expect } from 'vitest';
import { stripQueryBanner } from './query';

describe('stripQueryBanner', () => {
  it('strips the leading "wiki query" banner line', () => {
    expect(stripQueryBanner('wiki query\nThe answer is 42.')).toBe('The answer is 42.');
  });
  it('tolerates surrounding whitespace on the banner line', () => {
    expect(stripQueryBanner('  wiki query  \n\nbody text\n')).toBe('body text');
  });
  it('leaves a bannerless answer untouched (just trimmed)', () => {
    expect(stripQueryBanner('  just an answer  ')).toBe('just an answer');
  });
});
