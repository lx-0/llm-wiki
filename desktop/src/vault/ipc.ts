// Vault IPC contract — shared by main + preload (per-domain, like listeners/ipc.ts).

import type { VaultStatus } from './status';

export const VAULT_STATUS_CHANNEL = 'vault:status';

export interface VaultApi {
  status(): Promise<VaultStatus | null>;
}
