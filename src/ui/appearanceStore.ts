import {
  isAppearance,
  isMotionPreference,
  type Appearance,
  type MotionPreference,
} from "./appearancePreference";

export type PreferencePorts<T extends string> = {
  read: () => T | null;
  write: (value: T) => boolean;
  apply: (value: T) => void;
  broadcast: (value: T) => Promise<void>;
  listen: (receive: (value: unknown) => void) => Promise<() => void>;
};
export type AppearancePorts = PreferencePorts<Appearance>;
export type MotionPorts = PreferencePorts<MotionPreference>;

function createPreferenceStore<T extends string>(
  ports: PreferencePorts<T>,
  fallback: T,
  validate: (value: unknown) => value is T,
) {
  let state = { value: ports.read() ?? fallback, persisted: true };
  const listeners = new Set<() => void>();
  let stop: (() => void) | undefined;
  let generation = 0;
  ports.apply(state.value);

  const update = (value: T, persisted = true) => {
    if (state.value === value && state.persisted === persisted) return;
    state = { value, persisted };
    ports.apply(value);
    listeners.forEach((listener) => listener());
  };
  const receive = (value: unknown) => {
    if (!validate(value) || !state.persisted) return;
    // Re-read the committed preference so delayed events cannot restore an older value.
    update(ports.read() ?? value);
  };
  return {
    getState: () => state,
    setValue: (value: unknown) => {
      if (!validate(value)) return;
      const persisted = ports.write(value);
      update(value, persisted);
      if (persisted) void ports.broadcast(value).catch(() => undefined);
    },
    subscribe: (listener: () => void) => {
      listeners.add(listener);
      if (listeners.size === 1) {
        const current = ++generation;
        void ports.listen(receive).then((unsubscribe) => {
          if (generation !== current || !listeners.size) { unsubscribe(); return; }
          stop = unsubscribe;
          const saved = ports.read();
          // A delayed registration must not discard an explicit, unsaved local choice.
          if (saved && state.persisted) update(saved);
        }).catch(() => undefined);
      }
      return () => {
        listeners.delete(listener);
        if (!listeners.size) { generation++; stop?.(); stop = undefined; }
      };
    },
  };
}

// Independent of quota transport: appearance and motion changes never read or refresh Provider data.
export function createAppearanceStore(ports: AppearancePorts) {
  const store = createPreferenceStore(ports, "light", isAppearance);
  let cached = store.getState();
  let snapshot = { theme: cached.value, persisted: cached.persisted };
  return {
    getSnapshot: () => {
      const next = store.getState();
      if (next !== cached) {
        cached = next;
        snapshot = { theme: next.value, persisted: next.persisted };
      }
      return snapshot;
    },
    setTheme: store.setValue,
    subscribe: store.subscribe,
  };
}

export function createMotionStore(ports: MotionPorts) {
  const store = createPreferenceStore(ports, "on", isMotionPreference);
  let cached = store.getState();
  let snapshot = { motion: cached.value, persisted: cached.persisted };
  return {
    getSnapshot: () => {
      const next = store.getState();
      if (next !== cached) {
        cached = next;
        snapshot = { motion: next.value, persisted: next.persisted };
      }
      return snapshot;
    },
    setMotion: store.setValue,
    subscribe: store.subscribe,
  };
}
