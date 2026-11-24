// The only persisted Renderer preferences (fixed enums only). No accounts, projections or credentials belong here.
export type Appearance = "light" | "dark";
export type MotionPreference = "on" | "off";
export const appearanceKey = "agent-quota.appearance.v1";
export const motionKey = "agent-quota.motion.v1";

export function isAppearance(value: unknown): value is Appearance {
  return value === "light" || value === "dark";
}

export function isMotionPreference(value: unknown): value is MotionPreference {
  return value === "on" || value === "off";
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

export function readMotionPreference(): MotionPreference | null {
  try {
    const value = window.localStorage.getItem("agent-quota.motion.v1");
    return isMotionPreference(value) ? value : null;
  } catch { return null; }
}

export function writeMotionPreference(motion: MotionPreference): boolean {
  if (!isMotionPreference(motion)) return false;
  try {
    window.localStorage.setItem("agent-quota.motion.v1", motion);
    return true;
  } catch { return false; }
}
