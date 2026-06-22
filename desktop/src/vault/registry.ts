// Vault discovery — mirrors the engine/use-llm-wiki mechanism: read the registry
// at ${XDG_CONFIG_HOME:-~/.config}/llm-wiki/vaults (one vault path per line) and
// pick the first one that exists. Not hardcoded.

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

function registryPath(): string {
  const base = process.env.XDG_CONFIG_HOME || path.join(os.homedir(), '.config');
  return path.join(base, 'llm-wiki', 'vaults');
}

export interface VaultRef {
  name: string;
  path: string;
}

export function resolveVault(): VaultRef | null {
  try {
    const lines = fs
      .readFileSync(registryPath(), 'utf8')
      .split('\n')
      .map((l) => l.trim())
      .filter(Boolean);
    for (const p of lines) {
      if (fs.existsSync(p)) return { name: path.basename(p), path: p };
    }
  } catch {
    /* no registry / unreadable */
  }
  return null;
}
