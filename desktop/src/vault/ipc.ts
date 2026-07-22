// Vault IPC contract — shared by main + preload (per-domain, like listeners/ipc.ts).

import type { VaultStatus, EntryItem } from './status';
import type { CompileResult, CompileStart, CompileProgress, EngineCommandId } from './compile';
import type { DoctorResult } from './doctor';
import type { QueryResult } from './query';
import type { MenuResult } from './menu';
import type { Collector } from './collectors';
import type { TriageRecord } from './triage';

/** Advanced engine actions surfaced behind the "Advanced" disclosure. Renderer-safe
 *  (no node imports) — labels are end-user phrasing, all $0 / non-destructive. */
export const ADVANCED_COMMANDS: { id: Exclude<EngineCommandId, 'update'>; label: string; hint: string }[] = [
  { id: 'lint', label: 'Check for problems', hint: 'Scan the wiki for structural issues' },
  { id: 'links', label: 'Find broken links', hint: 'Check every link still points somewhere' },
  { id: 'dedup', label: 'Find duplicates', hint: 'Suggest pages to merge — no changes made' },
  { id: 'review', label: 'Review quality', hint: 'A local pass over your pages' },
  { id: 'dream', label: 'Refresh people & project pages', hint: 'Rebuild them from your latest notes ($)' },
];

export const VAULT_STATUS_CHANNEL = 'vault:status';
export const VAULT_LIST_CHANNEL = 'vault:list';
export const VAULT_PREVIEW_CHANNEL = 'vault:preview';
export const VAULT_COLLECTORS_CHANNEL = 'vault:collectors';
export const VAULT_TRIAGE_CHANNEL = 'vault:triage';
export const VAULT_TRIAGE_ACTION_CHANNEL = 'vault:triage-action';
export const VAULT_DOCTOR_CHANNEL = 'vault:doctor';
export const VAULT_MENU_CHANNEL = 'vault:menu';
export const VAULT_QUERY_CHANNEL = 'vault:query';
export const VAULT_RUN_CHANNEL = 'vault:run';
export const VAULT_RUN_ARGS_CHANNEL = 'vault:run-args';
export const VAULT_RUN_STATUS_CHANNEL = 'vault:run-status';
export const VAULT_RUN_PROGRESS_CHANNEL = 'vault:run-progress';
export const VAULT_RUN_DONE_CHANNEL = 'vault:run-done';
export const VAULT_COMPILE_CHANNEL = 'vault:compile';
export const VAULT_COMPILE_STATUS_CHANNEL = 'vault:compile-status';
export const VAULT_COMPILE_PROGRESS_CHANNEL = 'vault:compile-progress';
export const VAULT_COMPILE_DONE_CHANNEL = 'vault:compile-done';
export const VAULT_OPEN_OBSIDIAN_CHANNEL = 'vault:open-obsidian';
export const VAULT_OPEN_FILE_CHANNEL = 'vault:open-file';
export const VAULT_OPEN_FDA_CHANNEL = 'vault:open-fda';

export interface VaultApi {
  status(): Promise<VaultStatus | null>;
  /** All knowledge entries (newest first) for the Browse window. */
  list(): Promise<EntryItem[]>;
  /** Lazy content preview (body snippet) of one entry, by vault-relative path. */
  preview(file: string): Promise<string>;
  /** Registered substrate collectors (intake sources) from `wiki collect --list --json`. */
  collectors(): Promise<Collector[]>;
  /** Intent-inbox records from `wiki triage list --json`. Pending-only unless showAll. */
  triage(showAll: boolean): Promise<TriageRecord[]>;
  /** Accept or dismiss one inbox record (`wiki triage <action> <stem>`). */
  triageAction(stem: string, action: 'accept' | 'dismiss'): Promise<{ ok: boolean; message: string }>;
  /** Open the active vault in Obsidian. */
  openInObsidian(): Promise<{ ok: boolean }>;
  /** Open one vault file (path relative to vault root) in Obsidian. */
  openFile(file: string): void;
  /** Open System Settings → Privacy → Full Disk Access. */
  openFullDiskAccess(): void;
  /** Health + update-available, from `wiki doctor --json` (read-only, ~seconds). */
  doctor(): Promise<DoctorResult | null>;
  /** Ask the knowledge base — `wiki query "Q" --brief --json`. LLM cost; returns the answer. */
  query(question: string): Promise<QueryResult>;
  /** The engine's prioritized actionable menu — `wiki menu --json`. */
  menu(): Promise<MenuResult | null>;
  /** Run an engine command (update / lint / links / dedup / review). */
  run(id: EngineCommandId): Promise<CompileStart>;
  /** Run an arbitrary engine command from a menu suggestion (cmd string → args). */
  runArgs(args: string[]): Promise<CompileStart>;
  /** Which engine command is running right now (one at a time), or null. */
  runStatus(): Promise<{ running: 'compile' | EngineCommandId | null }>;
  /** Fires on each `[i/total]` step of a run()/runArgs() command (if it emits any). */
  onRunProgress(cb: (r: { id: string; progress: CompileProgress }) => void): void;
  /** Fires when a run() command finishes. */
  onRunDone(cb: (r: { id: EngineCommandId; result: CompileResult }) => void): void;
  /** Start `wiki compile` (long-running). Returns immediately. */
  compile(): Promise<CompileStart>;
  /** Current compile state (running + last progress) — to restore UI on reopen. */
  compileStatus(): Promise<{ running: boolean; progress: CompileProgress }>;
  /** Fires on each progress step (structured PROGRESS lines from the compiler). */
  onCompileProgress(cb: (p: CompileProgress) => void): void;
  /** Fires when a compile finishes. */
  onCompileDone(cb: (r: CompileResult) => void): void;
}
