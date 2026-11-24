import { useEffect, useRef, useState } from "react";
import { dragFloatingWindow, resizeFloatingWindow } from "../host/floatingWindow";

type QuotaReader = {
  busy: boolean;
  loading: boolean;
  readSnapshot: () => Promise<void>;
};

export function useFloatingShell(quota: QuotaReader) {
  const [expanded, setExpanded] = useState(false);
  const [pinned, setPinned] = useState(false);
  const [windowError, setWindowError] = useState("");
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const hoverTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const expandedRef = useRef(false);
  const dragging = useRef(false);
  const pointerInside = useRef(false);
  const keyboardInside = useRef(false);
  const pinnedRef = useRef(false);
  const lastHoverRead = useRef(0);
  const quotaRef = useRef(quota);
  quotaRef.current = quota;

  function clearTimer() {
    if (hoverTimer.current) clearTimeout(hoverTimer.current);
    hoverTimer.current = null;
  }

  function expand() {
    clearTimer();
    if (dragging.current || expandedRef.current) return;
    expandedRef.current = true;
    setExpanded(true);
    // Read the existing local projection; hovering never refreshes a Provider.
    if (
      !quotaRef.current.busy
      && !quotaRef.current.loading
      && Date.now() - lastHoverRead.current > 2000
    ) {
      lastHoverRead.current = Date.now();
      void quotaRef.current.readSnapshot();
    }
  }

  function collapse() {
    clearTimer();
    expandedRef.current = false;
    setExpanded(false);
  }

  function toggleExpanded() {
    if (dragging.current) return;
    if (expandedRef.current) {
      pinnedRef.current = false;
      setPinned(false);
      collapse();
      return;
    }
    expand();
  }

  function scheduleCollapse() {
    clearTimer();
    hoverTimer.current = setTimeout(() => {
      if (!pinnedRef.current && !pointerInside.current && !keyboardInside.current && !dragging.current) collapse();
    }, 350);
  }

  async function windowAction(action: () => Promise<void>) {
    try {
      await action();
      setWindowError("");
    } catch {
      setWindowError("窗口操作失败，请重试。");
    }
  }

  function togglePinned() {
    const next = !pinned;
    pinnedRef.current = next;
    setPinned(next);
  }

  function onPointerEnter() {
    pointerInside.current = true;
    clearTimer();
    hoverTimer.current = setTimeout(expand, 160);
  }

  function onPointerLeave() {
    pointerInside.current = false;
    scheduleCollapse();
  }

  function onFocusCapture(target: EventTarget & Element) {
    if (target.matches(":focus-visible")) {
      keyboardInside.current = true;
      expand();
    }
  }

  function onBlurCapture(currentTarget: HTMLElement, relatedTarget: Node | null) {
    if (!currentTarget.contains(relatedTarget)) {
      keyboardInside.current = false;
      scheduleCollapse();
    }
  }

  function onStartDrag(button: number, preventDefault: () => void) {
    if (button !== 0) return;
    preventDefault();
    clearTimer();
    dragging.current = true;
    void windowAction(dragFloatingWindow).finally(() => {
      dragging.current = false;
    });
  }

  useEffect(() => {
    let active = true;
    void resizeFloatingWindow(expanded).catch(() => {
      if (active) setWindowError("悬浮窗尺寸调整失败，请重新打开。");
    });
    return () => {
      active = false;
    };
  }, [expanded]);

  useEffect(() => () => {
    if (hoverTimer.current) clearTimeout(hoverTimer.current);
  }, []);

  useEffect(() => {
    const escape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      pinnedRef.current = false;
      setPinned(false);
      trigger.current?.focus();
      if (hoverTimer.current) clearTimeout(hoverTimer.current);
      expandedRef.current = false;
      setExpanded(false);
    };
    window.addEventListener("keydown", escape);
    return () => window.removeEventListener("keydown", escape);
  }, []);

  return {
    root,
    trigger,
    expanded,
    pinned,
    windowError,
    expand,
    toggleExpanded,
    togglePinned,
    windowAction,
    onPointerEnter,
    onPointerLeave,
    onFocusCapture,
    onBlurCapture,
    onStartDrag,
  };
}
