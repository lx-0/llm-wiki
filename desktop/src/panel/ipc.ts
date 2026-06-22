// Panel visibility — main is authoritative about whether the menubar panel is
// shown (BrowserWindow show/hide events). It pushes that to the renderer so the
// renderer can poll ONLY while visible. (document.visibilityState is unreliable
// for a never-shown Electron window.)

export const PANEL_VISIBILITY_CHANNEL = 'panel:visibility';
export const PANEL_RESIZE_CHANNEL = 'panel:resize';

export interface PanelApi {
  /** Subscribe to panel show/hide. Fires `true` on show, `false` on hide. */
  onVisibility(cb: (visible: boolean) => void): void;
  /** Ask main to size the window to this content height (auto-fit, no scroll). */
  resize(height: number): void;
}
