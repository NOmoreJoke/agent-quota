import { Window, getCurrentWindow, currentMonitor, LogicalSize, PhysicalPosition } from "@tauri-apps/api/window";
import { transportMode } from "./transport";
import { listen } from "@tauri-apps/api/event";

export const floatingSize = { collapsed: { width: 264, height: 72 }, expanded: { width: 384, height: 536 } };

export type ProjectionChange = { source: string; refreshOutcome?: "success" | "warning" | "unknown" };

export async function onQuotaProjectionChanged(callback: (change: ProjectionChange) => void): Promise<() => void> {
  if (transportMode === "fixture") return () => undefined;
  const label = getCurrentWindow().label;
  return listen<ProjectionChange>("quota-projection-changed", (event) => {
    if (event.payload.source !== label) callback(event.payload);
  });
}

export async function showFloatingWindow(): Promise<void> {
  if (transportMode === "fixture") {
    window.open(`${window.location.pathname}${window.location.search || "?"}${window.location.search ? "&" : ""}surface=floating`, "quota-floating-preview");
    return;
  }
  const floating = await Window.getByLabel("floating");
  if (!floating) throw new Error("悬浮窗尚未创建");
  await floating.show();
}

export async function showMainWindow(): Promise<void> {
  if (transportMode === "fixture") {
    const url = new URL(window.location.href);
    url.searchParams.delete("surface");
    window.location.assign(url);
    return;
  }
  const main = await Window.getByLabel("main");
  if (!main) throw new Error("主窗口不可用");
  await main.show();
  await main.unminimize();
  await main.setFocus();
}

export async function hideFloatingWindow(): Promise<void> {
  // Keep a visible way back when the user hides the widget.
  await showMainWindow();
  if (transportMode !== "fixture") await getCurrentWindow().hide();
}

export async function dragFloatingWindow(): Promise<void> {
  if (transportMode !== "fixture") await getCurrentWindow().startDragging();
}

let resizeQueue: Promise<void> = Promise.resolve();
export function resizeFloatingWindow(expanded: boolean): Promise<void> {
  if (transportMode === "fixture") return Promise.resolve();
  const resize = async () => {
    const floating = getCurrentWindow();
    const size = floatingSize[expanded ? "expanded" : "collapsed"];
    const [monitor, position] = await Promise.all([currentMonitor(), floating.outerPosition()]);
    await floating.setSize(new LogicalSize(size.width, size.height));
    if (monitor) {
      const { position: origin, size: area } = monitor.workArea;
      const scale = monitor.scaleFactor;
      await floating.setPosition(new PhysicalPosition(
        Math.max(origin.x, Math.min(position.x, origin.x + area.width - size.width * scale)),
        Math.max(origin.y, Math.min(position.y, origin.y + area.height - size.height * scale)),
      ));
    }
  };
  resizeQueue = resizeQueue.catch(() => undefined).then(resize);
  return resizeQueue;
}
