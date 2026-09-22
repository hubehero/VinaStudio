/**
 * Commands the native Qt menu bar invokes on the web application.
 *
 * The native shell owns accelerators and the menu structure; this module is the
 * single place where those actions land, so the two halves cannot drift.
 */

export interface NativeCommands {
  newProject: () => void
  openProject: () => void
  saveProject: () => void
  saveProjectAs: () => void
  setLocale: (locale: string) => void
}

export function registerNativeCommands(commands: NativeCommands): void {
  window.vinastudio = {
    newProject: () => commands.newProject(),
    openProject: () => commands.openProject(),
    saveProject: () => commands.saveProject(),
    saveProjectAs: () => commands.saveProjectAs(),
    setLocale: (locale: unknown) => commands.setLocale(String(locale)),
  }
}

export function clearNativeCommands(): void {
  delete window.vinastudio
}
