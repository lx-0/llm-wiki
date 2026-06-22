import { describe, it, expect } from 'vitest';
import { guiDomain, guiDomainTarget } from './lifecycle';

describe('launchd domain helpers (pure)', () => {
  it('guiDomain', () => {
    expect(guiDomain(501)).toBe('gui/501');
  });
  it('guiDomainTarget', () => {
    expect(guiDomainTarget(501, 'com.alex.screenpipe')).toBe('gui/501/com.alex.screenpipe');
  });
});
