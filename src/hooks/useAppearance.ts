import { useSyncExternalStore } from "react";
import { emit, listen } from "@tauri-apps/api/event";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { transportMode } from "../host/transport";
import {
  appearanceKey,
  isAppearance,
  isMotionPreference,
  motionKey,
  readAppearance,
  readMotionPreference,
  writeAppearance,
  writeMotionPreference,
  type Appearance,
  type MotionPreference,
} from "../ui/appearancePreference";
import { createAppearanceStore, createMotionStore } from "../ui/appearanceStore";

const appearanceEvent = "quota-appearance-changed";
const motionEvent = "quota-motion-changed";
let nativeThemeQueue = Promise.resolve();

function createCrossWindowListener<T extends string>(
  storageKey: string,
  eventName: string,
  validate: (value: unknown) => value is T,
) {
  return async (receive: (value: unknown) => void) => {
    const onStorage = (event: StorageEvent) => {
      if (event.key === storageKey && validate(event.newValue)) receive(event.newValue);
    };
    window.addEventListener("storage", onStorage);
    let unlisten: (() => void) | undefined;
    try {
      if (transportMode !== "fixture") {
        unlisten = await listen<unknown>(eventName, (event) => {
          if (validate(event.payload)) receive(event.payload);
        });
      }
    } catch {
      /* Browser storage events still synchronize the persisted preference. */
    }
    return () => {
      window.removeEventListener("storage", onStorage);
      unlisten?.();
    };
  };
}

const store = createAppearanceStore({
  read: readAppearance,
  write: writeAppearance,
  apply: (theme) => {
    document.documentElement.dataset.theme = theme;
    if (transportMode !== "fixture") {
      nativeThemeQueue = nativeThemeQueue
        .catch(() => undefined)
        .then(() => getCurrentWindow().setTheme(theme));
      void nativeThemeQueue.catch(() => undefined);
    }
  },
  broadcast: async (theme) => {
    if (transportMode !== "fixture") await emit(appearanceEvent, theme);
  },
  listen: createCrossWindowListener(appearanceKey, appearanceEvent, isAppearance),
});

const motionStore = createMotionStore({
  read: readMotionPreference,
  write: writeMotionPreference,
  apply: (motion) => {
    document.documentElement.dataset.motion = motion;
  },
  broadcast: async (motion) => {
    if (transportMode !== "fixture") await emit(motionEvent, motion);
  },
  listen: createCrossWindowListener(motionKey, motionEvent, isMotionPreference),
});

export function useAppearance() {
  const snapshot = useSyncExternalStore(store.subscribe, store.getSnapshot);
  return { ...snapshot, setTheme: (theme: Appearance) => store.setTheme(theme) };
}

export function useMotion() {
  const snapshot = useSyncExternalStore(motionStore.subscribe, motionStore.getSnapshot);
  return { ...snapshot, setMotion: (motion: MotionPreference) => motionStore.setMotion(motion) };
}
