// Vault IPC contract — shared by main + preload (per-domain, like listeners/ipc.ts).

import type { VaultStatus } from './status';
import type { CompileResult, CompileStart } from './compile';

export const VAULT_STATUS_CHANNEL = 'vault:status';
export const VAULT_COMPILE_CHANNEL = 'vault:compile';
export const VAULT_COMPILE_STATUS_CHANNEL = 'vault:compile-status';
export const VAULT_COMPILE_DONE_CHANNEL = 'vault:compile-done';

export interface VaultApi {
  status(): Promise<VaultStatus | null>;
  /** Start `wiki compile` (long-running). Returns immediately. */
  compile(): Promise<CompileStart>;
  /** Whether a compile is currently running (to restore UI on panel reopen). */
  compileStatus(): Promise<{ running: boolean }>;
  /** Fires when a compile finishes. */
  onCompileDone(cb: (r: CompileResult) => void): void;
}
