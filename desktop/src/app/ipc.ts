// App-level IPC — login-item (autostart), quit, and opening the Settings window.
// Surfaced in the panel (header gear + footer Quit), not a tray right-click menu
// (those are unreliable on macOS for LSUIElement apps).

export const APP_LOGIN_GET_CHANNEL = 'app:login-get';
export const APP_LOGIN_SET_CHANNEL = 'app:login-set';
export const APP_QUIT_CHANNEL = 'app:quit';
export const APP_OPEN_SETTINGS_CHANNEL = 'app:open-settings';
export const APP_OPEN_BROWSE_CHANNEL = 'app:open-browse';
export const APP_OPEN_COCKPIT_CHANNEL = 'app:open-cockpit';
export const APP_CLOSE_COCKPIT_CHANNEL = 'app:close-cockpit';
export const APP_ONBOARDING_DONE_CHANNEL = 'app:onboarding-done';

export interface AppApi {
  /** current "open at login" state */
  getLoginItem(): Promise<boolean>;
  /** set "open at login"; returns the new state */
  setLoginItem(open: boolean): Promise<boolean>;
  quit(): void;
  /** open the Settings window (singleton) */
  openSettings(): void;
  /** open the Browse window (singleton) */
  openBrowse(): void;
  /** open the full-window Cockpit view */
  openCockpit(): void;
  /** close the Cockpit view (back to the compact popover) */
  closeCockpit(): void;
  /** mark first-run onboarding complete + close the onboarding window */
  onboardingDone(): void;
}
