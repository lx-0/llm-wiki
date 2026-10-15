// Test support for the schema-2 contract — never imported by the app (it reads the repo's
// files with node:fs). The engine generates docs/contracts/{menu,doctor}.schema.json from
// scripts/core/contracts.py (`python -m core.contracts --write`) and validates its own output
// against them in pytest; the desktop's vitest suite validates against the same two files
// here, so neither side can drift from the other silently.

import { readFileSync } from 'node:fs';
import Ajv2020, { type ValidateFunction } from 'ajv/dist/2020';

/** The repo root, from desktop/src/lib/. */
const REPO = new URL('../../../', import.meta.url);

interface ObjectSchema {
  properties: Record<string, unknown>;
}

export interface ContractSchema extends ObjectSchema {
  $defs: Record<string, ObjectSchema>;
}

/** A JSON file of the repo, parsed — `path` is repo-relative. */
export function readRepoJson<T = unknown>(path: string): T {
  return JSON.parse(readFileSync(new URL(path, REPO), 'utf-8'));
}

export const menuSchema = readRepoJson<ContractSchema>('docs/contracts/menu.schema.json');
export const doctorSchema = readRepoJson<ContractSchema>('docs/contracts/doctor.schema.json');

const ajv = new Ajv2020({ allErrors: true });
const checkMenu = ajv.compile(menuSchema);
const checkDoctor = ajv.compile(doctorSchema);

function errorsOf(check: ValidateFunction, payload: unknown): string[] {
  if (check(payload)) return [];
  return (check.errors ?? []).map((e) => `${e.instancePath || '/'} ${e.message ?? 'invalid'}`);
}

/** The violations of `wiki menu --json`'s contract — empty when the payload conforms. */
export function validateMenu(payload: unknown): string[] {
  return errorsOf(checkMenu, payload);
}

/** The violations of `wiki doctor --json`'s contract — empty when the payload conforms. */
export function validateDoctor(payload: unknown): string[] {
  return errorsOf(checkDoctor, payload);
}

/** Each payload object's field list against the fields the app knows (`known`, by `$defs`
 *  name): one line per object whose schema has a field the app does not know, or lost one it
 *  expects. Empty when the app and the schemas agree. */
export function fieldInventoryDrift(
  known: Record<string, string[]>,
  schemas: ContractSchema[] = [menuSchema, doctorSchema],
): string[] {
  const defs: Record<string, ObjectSchema> = Object.assign({}, ...schemas.map((s) => s.$defs));
  const drift: string[] = [];
  for (const [name, fields] of Object.entries(known)) {
    const actual = Object.keys(defs[name]?.properties ?? {});
    const added = actual.filter((f) => !fields.includes(f));
    const removed = fields.filter((f) => !actual.includes(f));
    if (added.length)
      drift.push(`${name}: the schema has a field the app does not know: ${added.join(', ')}`);
    if (removed.length) drift.push(`${name}: the schema lost a field the app expects: ${removed.join(', ')}`);
  }
  return drift;
}
