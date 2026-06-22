// App-level IPC — login-item (autostart) + quit. Surfaced in the panel footer,
// not a tray right-click menu (those are unreliable on macOS for LSUIElement apps).

export const APP_LOGIN_GET_CHANNEL = 'app:login-get';
export const APP_LOGIN_SET_CHANNEL = 'app:login-set';
export const APP_QUIT_CHANNEL = 'app:quit';

export interface AppApi {
  /** current "open at login" state */
  getLoginItem(): Promise<boolean>;
  /** set "open at login"; returns the new state */
  setLoginItem(open: boolean): Promise<boolean>;
  quit(): void;
}
