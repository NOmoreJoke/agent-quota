import { isAppearance, type Appearance } from "./appearancePreference";

type Snapshot = { theme: Appearance; persisted: boolean };
export type AppearancePorts = {
  read: () => Appearance | null;
  write: (theme: Appearance) => boolean;
  apply: (theme: Appearance) => void;
  broadcast: (theme: Appearance) => Promise<void>;
  listen: (receive: (value: unknown) => void) => Promise<() => void>;
};

// Independent of quota transport: appearance changes never read or refresh Provider data.
export function createAppearanceStore(ports: AppearancePorts) {
  let snapshot: Snapshot = { theme: ports.read() ?? "light", persisted: true };
  const listeners = new Set<() => void>();
  let stop: (() => void) | undefined;
  let generation = 0;
  ports.apply(snapshot.theme);

  const update = (theme: Appearance, persisted = true) => {
    if (snapshot.theme === theme && snapshot.persisted === persisted) return;
    snapshot = { theme, persisted };
    ports.apply(theme);
    listeners.forEach((listener) => listener());
  };
  const receive = (value: unknown) => {
    if (!isAppearance(value) || !snapshot.persisted) return;
    // Re-read the committed preference so delayed events cannot restore an older theme.
    update(ports.read() ?? value);
  };
  return {
    getSnapshot: () => snapshot,
    setTheme: (value: unknown) => {
      if (!isAppearance(value)) return;
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
          if (saved && snapshot.persisted) update(saved);
        }).catch(() => undefined);
      }
      return () => {
        listeners.delete(listener);
        if (!listeners.size) { generation++; stop?.(); stop = undefined; }
      };
    },
  };
}
