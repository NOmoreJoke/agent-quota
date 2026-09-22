// The only persisted Renderer preference. No accounts, projections or credentials belong here.
export type Appearance = "light" | "dark";
export const appearanceKey = "agent-quota.appearance.v1";

export function isAppearance(value: unknown): value is Appearance {
  return value === "light" || value === "dark";
}

export function readAppearance(): Appearance | null {
  try {
    const value = window.localStorage.getItem("agent-quota.appearance.v1");
    return isAppearance(value) ? value : null;
  } catch { return null; }
}

export function writeAppearance(theme: Appearance): boolean {
  if (!isAppearance(theme)) return false;
  try {
    window.localStorage.setItem("agent-quota.appearance.v1", theme);
    return true;
  } catch { return false; }
}
