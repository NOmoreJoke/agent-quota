import { useSyncExternalStore } from "react";
import { emit, listen } from "@tauri-apps/api/event";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { transportMode } from "../host/transport";
import { appearanceKey, isAppearance, readAppearance, writeAppearance, type Appearance } from "./appearancePreference";
import { createAppearanceStore } from "./appearanceStore";

const appearanceEvent = "quota-appearance-changed";
let nativeThemeQueue = Promise.resolve();
const store = createAppearanceStore({
  read: readAppearance,
  write: writeAppearance,
  apply: (theme) => {
    document.documentElement.dataset.theme = theme;
    if (transportMode !== "fixture") {
      nativeThemeQueue = nativeThemeQueue.catch(() => undefined).then(() => getCurrentWindow().setTheme(theme));
      void nativeThemeQueue.catch(() => undefined);
    }
  },
  broadcast: async (theme) => {
    if (transportMode !== "fixture") await emit(appearanceEvent, theme);
  },
  listen: async (receive) => {
    const onStorage = (event: StorageEvent) => {
      if (event.key === appearanceKey && isAppearance(event.newValue)) receive(event.newValue);
    };
    window.addEventListener("storage", onStorage);
    let unlisten: (() => void) | undefined;
    try {
      if (transportMode !== "fixture") {
        unlisten = await listen<unknown>(appearanceEvent, (event) => {
          if (isAppearance(event.payload)) receive(event.payload);
        });
      }
    } catch { /* Browser storage events still synchronize the persisted preference. */ }
    return () => { window.removeEventListener("storage", onStorage); unlisten?.(); };
  },
});

export function useAppearance() {
  const snapshot = useSyncExternalStore(store.subscribe, store.getSnapshot);
  return { ...snapshot, setTheme: (theme: Appearance) => store.setTheme(theme) };
}
