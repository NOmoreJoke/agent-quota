import { useEffect, useMemo, useRef, useState } from "react";
import { dragFloatingWindow, hideFloatingWindow, resizeFloatingWindow, showMainWindow } from "../host/floatingWindow";
import { transportMode } from "../host/transport";
import { compareWindowOrder, displayedHealth, effectiveHealth, isWeeklyWindow, providerName, providerOrder, windowFamily, windowMetric } from "./quotaPresentation";
import { useQuotaController } from "./useQuotaController";
import "./floating.css";
import { useAppearance } from "./appearance";

const healthLabels: Record<string, string> = {
  ok: "可用", error: "查询失败", exhausted: "已用尽", unavailable: "不可用",
  incompatible: "不兼容", unsupported: "不支持", unknown: "未知",
};
type QuotaView = "window" | "wallet";
const quotaViews: { id: QuotaView; label: string }[] = [
  { id: "window", label: "Window View" },
  { id: "wallet", label: "Wallet View" },
];

export function FloatingQuota() {
  useAppearance();
  const quota = useQuotaController();
  const [expanded, setExpanded] = useState(false);
  const [pinned, setPinned] = useState(false);
  const [view, setView] = useState<QuotaView>("window");
  const [selectedProviders, setSelectedProviders] = useState<Record<QuotaView, string | null>>({ window: null, wallet: null });
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

  const allGroups = useMemo(() => providerOrder.map((provider) => ({
    provider,
    rows: quota.capabilities.filter((row) => providerName(row.capability_ref) === provider)
      .map((row, sourceIndex) => ({ row, sourceIndex })).sort((left, right) => compareWindowOrder(left, right, true)).map(({ row }) => row),
  })).filter(({ rows }) => rows.length > 0), [quota.capabilities]);
  const groups = useMemo(() => quota.accounts.length === 0 ? [] : allGroups.map((group) => ({
    ...group, rows: group.rows.filter((row) => row.display_kind === (view === "window" ? "window" : "balance")),
  })).filter(({ rows }) => rows.length > 0), [allGroups, quota.accounts.length, view]);
  const selectedGroup = groups.find(({ provider }) => provider === selectedProviders[view]) ?? groups[0];
  const otherRows = quota.capabilities.filter((row) => row.display_kind !== "window" && row.display_kind !== "balance").length;
  const exhausted = useMemo(() => new Set(quota.capabilities
    .filter((row) => isWeeklyWindow(row) && displayedHealth(row) === "exhausted").map(windowFamily)), [quota.capabilities]);
  const unavailable = quota.connection === "offline" || quota.connection === "unavailable";
  const stale = quota.freshness !== "fresh" || unavailable;
  const issues = quota.capabilities.filter((row) => effectiveHealth(row, exhausted) !== "ok").length;
  const summary = quota.loading ? "正在读取" : unavailable ? "连接待恢复" : quota.accounts.length === 0 ? "待添加账户" : issues ? `${issues} 项需关注` : `${allGroups.length} 个平台`;

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
    if (!quotaRef.current.busy && !quotaRef.current.loading && Date.now() - lastHoverRead.current > 2000) {
      lastHoverRead.current = Date.now();
      void quotaRef.current.readSnapshot();
    }
  }

  function collapse() {
    clearTimer();
    expandedRef.current = false;
    setExpanded(false);
  }

  function scheduleCollapse() {
    clearTimer();
    hoverTimer.current = setTimeout(() => {
      if (!pinnedRef.current && !pointerInside.current && !keyboardInside.current && !dragging.current) collapse();
    }, 350);
  }

  async function windowAction(action: () => Promise<void>) {
    try { await action(); setWindowError(""); }
    catch { setWindowError("窗口操作失败，请重试。"); }
  }

  useEffect(() => {
    let active = true;
    void resizeFloatingWindow(expanded).catch(() => {
      if (active) setWindowError("悬浮窗尺寸调整失败，请重新打开。");
    });
    return () => { active = false; };
  }, [expanded]);

  useEffect(() => () => { if (hoverTimer.current) clearTimeout(hoverTimer.current); }, []);

  useEffect(() => {
    const escape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      pinnedRef.current = false; setPinned(false);
      trigger.current?.focus();
      if (hoverTimer.current) clearTimeout(hoverTimer.current);
      expandedRef.current = false; setExpanded(false);
    };
    window.addEventListener("keydown", escape);
    return () => window.removeEventListener("keydown", escape);
  }, []);

  return (
    <div ref={root} className={`floating-shell ${expanded ? "is-expanded" : ""}`} data-transport={transportMode}
      onPointerEnter={() => { pointerInside.current = true; clearTimer(); hoverTimer.current = setTimeout(expand, 160); }}
      onPointerLeave={() => { pointerInside.current = false; scheduleCollapse(); }}
      onFocusCapture={(event) => {
        if (event.target.matches(":focus-visible")) { keyboardInside.current = true; expand(); }
      }}
      onBlurCapture={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) { keyboardInside.current = false; scheduleCollapse(); }
      }}>
      <div className="floating-capsule">
        <button ref={trigger} className="floating-trigger" aria-label="展开用量悬浮窗" aria-expanded={expanded} aria-controls="floating-details" onClick={expand}>
          <span className={`floating-orb ${unavailable || issues ? "needs-attention" : ""}`} aria-hidden="true"><i/><i/><i/></span>
          <span className="floating-brand">Agent Quota</span>
          <span className="floating-summary">{summary}</span>
        </button>
        <button className="floating-drag" aria-label="拖动悬浮窗" title="按住拖动"
          onPointerDown={(event) => {
            if (event.button !== 0) return;
            event.preventDefault(); clearTimer(); dragging.current = true;
            void windowAction(dragFloatingWindow).finally(() => { dragging.current = false; });
          }}>⠿</button>
      </div>

      {expanded && <section id="floating-details" className="floating-details" aria-label="各平台用量">
        <header className="floating-heading"><div><h1>用量速览</h1><p>{transportMode === "fixture" ? "演示数据 · " : ""}{stale ? "最近缓存 · 待刷新" : "本机最近快照"}</p></div>
          <button className={`floating-pin ${pinned ? "is-pinned" : ""}`} aria-label="保持展开" aria-pressed={pinned} onClick={() => {
            pinnedRef.current = !pinned; setPinned(!pinned);
          }}>{pinned ? "已固定" : "固定"}</button>
        </header>
        <div className="floating-filters">
          <div className="floating-view-switch" role="group" aria-label="额度分类">
            {quotaViews.map((item) => <button key={item.id} type="button" aria-pressed={view === item.id}
              onClick={() => setView(item.id)}>{item.label}</button>)}
          </div>
          {groups.length > 0 && <div className="floating-provider-switch" role="group" aria-label={view === "window" ? "窗口额度供应商" : "钱包余额供应商"}>
            {groups.map((group) => <button key={group.provider} type="button" aria-pressed={selectedGroup?.provider === group.provider}
              onClick={() => setSelectedProviders((previous) => ({ ...previous, [view]: group.provider }))}>{group.provider}</button>)}
          </div>}
        </div>
        <div key={`${view}:${selectedGroup?.provider ?? "empty"}`} className="floating-scroll" tabIndex={0} aria-label="额度列表">
          {unavailable && <p className="floating-notice" role="status">本机服务暂不可用，已有数值仅供参考。</p>}
          {otherRows > 0 && quota.accounts.length > 0 && <p className="floating-other-status">另有 {otherRows} 项状态或计数，本视图暂不展示。</p>}
          {quota.accounts.length === 0 && !quota.loading ? <div className="floating-empty"><span>从一个账户开始</span><p>添加平台后，在这里查看用量。</p><button onClick={() => void windowAction(showMainWindow)}>前往主窗口添加</button></div>
            : !selectedGroup ? <p className="floating-empty">{quota.loading ? "正在读取本机额度…" : view === "window" ? "暂无窗口额度" : "暂无钱包余额"}</p>
              : <section className="floating-provider" aria-label={selectedGroup.provider}>
                <h2><span className="floating-provider-mark">{selectedGroup.provider === "其他" ? "·" : selectedGroup.provider.slice(0, 1)}</span>{selectedGroup.provider}<small>{selectedGroup.rows.length} 项</small></h2>
                {selectedGroup.rows.map((row) => {
                  const health = effectiveHealth(row, exhausted);
                  const metric = row.display_kind === "window" ? windowMetric(row.value_display) : null;
                  const remaining = metric ? metric.mode === "remaining" ? metric.percentage : 100 - metric.percentage : null;
                  return <article className={`floating-quota-row ${health !== "ok" ? "has-issue" : ""} ${stale ? "is-stale" : ""}`} data-health={health} key={row.capability_ref}>
                    <div><span className="floating-kind">{row.display_kind === "balance" ? "钱包余额" : row.display_kind === "window" ? "额度窗口" : "状态"}</span><span className="floating-health">{healthLabels[health] ?? health}</span></div>
                    <p>{row.value_display}</p>
                    {remaining !== null && <><div className="floating-meter" role="meter" aria-label={`${selectedGroup.provider} ${row.value_display} · 剩余额度`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={remaining}><i style={{ width: `${remaining}%` }}/></div><small className="floating-remaining">剩余 {Number(remaining.toFixed(2))}%{health === "unavailable" ? " · 受周额度限制" : ""}</small></>}
                  </article>;
                })}
              </section>}
        </div>
        {(quota.notice || windowError) && <p className="floating-notice" role="status">{windowError || quota.notice?.text}</p>}
        <footer className="floating-footer">
          <span>按需刷新</span>
          {unavailable ? <button disabled={quota.busy || quota.loading} onClick={() => void quota.retryLoad()}>重新连接</button>
            : <button disabled={quota.busy || quota.loading || quota.connection !== "ready"} onClick={() => void quota.refresh()}>{quota.busy ? "刷新中…" : "刷新用量"}</button>}
          <button className="floating-open" onClick={() => void windowAction(showMainWindow)}>主窗口 ↗</button>
          <button aria-label="隐藏悬浮窗" title="隐藏并返回主窗口" onClick={() => void windowAction(hideFloatingWindow)}>×</button>
        </footer>
      </section>}
    </div>
  );
}
