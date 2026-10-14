import { describe, expect, it } from 'vitest';
import { captureLabel, fileAccessLabel } from './labels';

describe('captureLabel', () => {
  it('reads the listener state as one word', () => {
    expect(captureLabel({ running: true, zombieSuspected: false })).toBe('Recording');
    expect(captureLabel({ running: true, zombieSuspected: true })).toBe('Check');
    expect(captureLabel({ running: false, zombieSuspected: false })).toBe('Paused');
  });

  it('says so when no capture process exists', () => {
    expect(captureLabel(null)).toBe('Not configured');
  });
});

describe('fileAccessLabel', () => {
  it('reports the grant state, and the absence of a library', () => {
    expect(fileAccessLabel({ accessible: true })).toBe('Granted');
    expect(fileAccessLabel({ accessible: false })).toBe('Not granted');
    expect(fileAccessLabel(null)).toBe('No library');
  });
});
