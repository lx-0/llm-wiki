import { describe, it, expect } from 'vitest';
import { appBundlePath, buildPlist, AUTOSTART_LABEL } from './autostart';

describe('appBundlePath (pure)', () => {
  it('derives the .app bundle from the executable path', () => {
    expect(appBundlePath('/Applications/llm-wiki.app/Contents/MacOS/llm-wiki')).toBe(
      '/Applications/llm-wiki.app',
    );
  });
  it('returns the input if not inside a .app (dev)', () => {
    expect(appBundlePath('/some/dev/electron')).toBe('/some/dev/electron');
  });
});

describe('buildPlist (pure)', () => {
  const plist = buildPlist('/Applications/llm-wiki.app');
  it('is valid-looking plist with the label + open + bundle + RunAtLoad', () => {
    expect(plist).toContain(`<string>${AUTOSTART_LABEL}</string>`);
    expect(plist).toContain('<string>/usr/bin/open</string>');
    expect(plist).toContain('<string>/Applications/llm-wiki.app</string>');
    expect(plist).toContain('<key>RunAtLoad</key>');
    expect(plist).toContain('<true/>');
    expect(plist).not.toContain('KeepAlive'); // autostart only, no respawn
  });
});
