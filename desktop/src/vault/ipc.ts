// Vault IPC contract — shared by main + preload (per-domain, like listeners/ipc.ts).

import type { VaultStatus } from './status';
import type { CompileResult, CompileStart, CompileProgress } from './compile';

export const VAULT_STATUS_CHANNEL = 'vault:status';
export const VAULT_COMPILE_CHANNEL = 'vault:compile';
export const VAULT_COMPILE_STATUS_CHANNEL = 'vault:compile-status';
export const VAULT_COMPILE_PROGRESS_CHANNEL = 'vault:compile-progress';
export const VAULT_COMPILE_DONE_CHANNEL = 'vault:compile-done';
export const VAULT_OPEN_OBSIDIAN_CHANNEL = 'vault:open-obsidian';

export interface VaultApi {
  status(): Promise<VaultStatus | null>;
  /** Open the active vault in Obsidian. */
  openInObsidian(): Promise<{ ok: boolean }>;
  /** Start `wiki compile` (long-running). Returns immediately. */
  compile(): Promise<CompileStart>;
  /** Current compile state (running + last progress) — to restore UI on reopen. */
  compileStatus(): Promise<{ running: boolean; progress: CompileProgress }>;
  /** Fires on each progress step ([idx/total] from the compiler). */
  onCompileProgress(cb: (p: CompileProgress) => void): void;
  /** Fires when a compile finishes. */
  onCompileDone(cb: (r: CompileResult) => void): void;
}
