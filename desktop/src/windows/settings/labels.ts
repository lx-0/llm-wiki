// The two status words the Settings and Onboarding windows show — one word, no sentence.

export function captureLabel(listener: { running: boolean; zombieSuspected: boolean } | null): string {
  if (!listener) return 'Not configured';
  if (!listener.running) return 'Paused';
  return listener.zombieSuspected ? 'Check' : 'Recording';
}

export function fileAccessLabel(vault: { accessible: boolean } | null): string {
  if (!vault) return 'No library';
  return vault.accessible ? 'Granted' : 'Not granted';
}
