import { useMemo, useState } from "react";
import { hideFloatingWindow, showMainWindow } from "../host/floatingWindow";
import { transportMode } from "../host/transport";
import {
  compareWindowOrder,
  displayedHealth,
  effectiveHealth,
  isWeeklyWindow,
  providerName,
  providerOrder,
  windowFamily,
  windowMetric,
} from "./quotaPresentation";
import { useAppearance } from "../hooks/useAppearance";
import { useFloatingShell } from "../hooks/useFloatingShell";
import { useQuotaController } from "../hooks/useQuotaController";
import "./floating.css";

const healthLabels: Record<string, string> = {
  ok: "可用",
  error: "查询失败",
  exhausted: "已用尽",
  unavailable: "不可用",
  incompatible: "不兼容",
  unsupported: "不支持",
  unknown: "未知",
};
type QuotaView = "window" | "wallet";
const quotaViews: { id: QuotaView; label: string }[] = [
  { id: "window", label: "Window View" },
  { id: "wallet", label: "Wallet View" },
];

export function FloatingQuota() {
  useAppearance();
  const quota = useQuotaController();
  const shell = useFloatingShell(quota);
  const [view, setView] = useState<QuotaView>("window");
  const [selectedProviders, setSelectedProviders] = useState<Record<QuotaView, string | null>>({
    window: null,
    wallet: null,
  });

  const allGroups = useMemo(
    () =>
      providerOrder
        .map((provider) => ({
          provider,
          rows: quota.capabilities
            .filter((row) => providerName(row.capability_ref) === provider)
            .map((row, sourceIndex) => ({ row, sourceIndex }))
            .sort((left, right) => compareWindowOrder(left, right, true))
            .map(({ row }) => row),
        }))
        .filter(({ rows }) => rows.length > 0),
    [quota.capabilities],
  );
  const groups = useMemo(
    () =>
      quota.accounts.length === 0
        ? []
        : allGroups
            .map((group) => ({
              ...group,
              rows: group.rows.filter(
                (row) => row.display_kind === (view === "window" ? "window" : "balance"),
              ),
            }))
            .filter(({ rows }) => rows.length > 0),
    [allGroups, quota.accounts.length, view],
  );
  const selectedGroup =
    groups.find(({ provider }) => provider === selectedProviders[view]) ?? groups[0];
  const otherRows = quota.capabilities.filter(
    (row) => row.display_kind !== "window" && row.display_kind !== "balance",
  ).length;
  const exhausted = useMemo(
    () =>
      new Set(
        quota.capabilities
          .filter((row) => isWeeklyWindow(row) && displayedHealth(row) === "exhausted")
          .map(windowFamily),
      ),
    [quota.capabilities],
  );
  const unavailable = quota.connection === "offline" || quota.connection === "unavailable";
  const stale = quota.freshness !== "fresh" || unavailable;
  const issues = quota.capabilities.filter(
    (row) => effectiveHealth(row, exhausted) !== "ok",
  ).length;
  const summary = quota.loading
    ? "正在读取"
    : unavailable
      ? "连接待恢复"
      : quota.accounts.length === 0
        ? "待添加账户"
        : issues
          ? `${issues} 项需关注`
          : `${allGroups.length} 个平台`;

  return (
    <div
      ref={shell.root}
      className={`floating-shell ${shell.expanded ? "is-expanded" : ""}`}
      data-transport={transportMode}
      onPointerEnter={shell.onPointerEnter}
      onPointerLeave={shell.onPointerLeave}
      onFocusCapture={(event) => shell.onFocusCapture(event.target)}
      onBlurCapture={(event) => shell.onBlurCapture(event.currentTarget, event.relatedTarget)}
    >
      <div className="floating-capsule">
        <button
          ref={shell.trigger}
          className="floating-trigger"
          aria-label="展开用量悬浮窗"
          aria-expanded={shell.expanded}
          aria-controls="floating-details"
          onClick={shell.expand}
        >
          <span
            className={`floating-orb ${unavailable || issues ? "needs-attention" : ""}`}
            aria-hidden="true"
          >
            <i />
            <i />
            <i />
          </span>
          <span className="floating-brand">Agent Quota</span>
          <span className="floating-summary">{summary}</span>
        </button>
        <button
          className="floating-drag"
          aria-label="拖动悬浮窗"
          title="按住拖动"
          onPointerDown={(event) => shell.onStartDrag(event.button, () => event.preventDefault())}
        >
          ⠿
        </button>
      </div>

      {shell.expanded && (
        <section id="floating-details" className="floating-details" aria-label="各平台用量">
          <header className="floating-heading">
            <div>
              <h1>用量速览</h1>
              <p>
                {transportMode === "fixture" ? "演示数据 · " : ""}
                {stale ? "最近缓存 · 待刷新" : "本机最近快照"}
              </p>
            </div>
            <button
              className={`floating-pin ${shell.pinned ? "is-pinned" : ""}`}
              aria-label="保持展开"
              aria-pressed={shell.pinned}
              onClick={shell.togglePinned}
            >
              {shell.pinned ? "已固定" : "固定"}
            </button>
          </header>
          <div className="floating-filters">
            <div className="floating-view-switch" role="group" aria-label="额度分类">
              {quotaViews.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  aria-pressed={view === item.id}
                  onClick={() => setView(item.id)}
                >
                  {item.label}
                </button>
              ))}
            </div>
            {groups.length > 0 && (
              <div
                className="floating-provider-switch"
                role="group"
                aria-label={view === "window" ? "窗口额度供应商" : "钱包余额供应商"}
              >
                {groups.map((group) => (
                  <button
                    key={group.provider}
                    type="button"
                    aria-pressed={selectedGroup?.provider === group.provider}
                    onClick={() =>
                      setSelectedProviders((previous) => ({ ...previous, [view]: group.provider }))
                    }
                  >
                    {group.provider}
                  </button>
                ))}
              </div>
            )}
          </div>
          <div
            key={`${view}:${selectedGroup?.provider ?? "empty"}`}
            className="floating-scroll"
            tabIndex={0}
            aria-label="额度列表"
          >
            {unavailable && (
              <p className="floating-notice" role="status">
                本机服务暂不可用，已有数值仅供参考。
              </p>
            )}
            {otherRows > 0 && quota.accounts.length > 0 && (
              <p className="floating-other-status">
                另有 {otherRows} 项状态或计数，本视图暂不展示。
              </p>
            )}
            {quota.accounts.length === 0 && !quota.loading ? (
              <div className="floating-empty">
                <span>从一个账户开始</span>
                <p>添加平台后，在这里查看用量。</p>
                <button onClick={() => void shell.windowAction(showMainWindow)}>
                  前往主窗口添加
                </button>
              </div>
            ) : !selectedGroup ? (
              <p className="floating-empty">
                {quota.loading
                  ? "正在读取本机额度…"
                  : view === "window"
                    ? "暂无窗口额度"
                    : "暂无钱包余额"}
              </p>
            ) : (
              <section className="floating-provider" aria-label={selectedGroup.provider}>
                <h2>
                  <span className="floating-provider-mark">
                    {selectedGroup.provider === "其他" ? "·" : selectedGroup.provider.slice(0, 1)}
                  </span>
                  {selectedGroup.provider}
                  <small>{selectedGroup.rows.length} 项</small>
                </h2>
                {selectedGroup.rows.map((row) => {
                  const health = effectiveHealth(row, exhausted);
                  const metric = row.display_kind === "window" ? windowMetric(row.value_display) : null;
                  const remaining = metric
                    ? metric.mode === "remaining"
                      ? metric.percentage
                      : 100 - metric.percentage
                    : null;
                  return (
                    <article
                      className={`floating-quota-row ${health !== "ok" ? "has-issue" : ""} ${stale ? "is-stale" : ""}`}
                      data-health={health}
                      key={row.capability_ref}
                    >
                      <div>
                        <span className="floating-kind">
                          {row.display_kind === "balance"
                            ? "钱包余额"
                            : row.display_kind === "window"
                              ? "额度窗口"
                              : "状态"}
                        </span>
                        <span className="floating-health">{healthLabels[health] ?? health}</span>
                      </div>
                      <p>{row.value_display}</p>
                      {remaining !== null && (
                        <>
                          <div
                            className="floating-meter"
                            role="meter"
                            aria-label={`${selectedGroup.provider} ${row.value_display} · 剩余额度`}
                            aria-valuemin={0}
                            aria-valuemax={100}
                            aria-valuenow={remaining}
                          >
                            <i style={{ width: `${remaining}%` }} />
                          </div>
                          <small className="floating-remaining">
                            剩余 {Number(remaining.toFixed(2))}%
                            {health === "unavailable" ? " · 受周额度限制" : ""}
                          </small>
                        </>
                      )}
                    </article>
                  );
                })}
              </section>
            )}
          </div>
          {(quota.notice || shell.windowError) && (
            <p className="floating-notice" role="status">
              {shell.windowError || quota.notice?.text}
            </p>
          )}
          <footer className="floating-footer">
            <span>按需刷新</span>
            {unavailable ? (
              <button disabled={quota.busy || quota.loading} onClick={() => void quota.retryLoad()}>
                重新连接
              </button>
            ) : (
              <button
                disabled={quota.busy || quota.loading || quota.connection !== "ready"}
                onClick={() => void quota.refresh()}
              >
                {quota.busy ? "刷新中…" : "刷新用量"}
              </button>
            )}
            <button
              className="floating-open"
              onClick={() => void shell.windowAction(showMainWindow)}
            >
              主窗口 ↗
            </button>
            <button
              aria-label="隐藏悬浮窗"
              title="隐藏并返回主窗口"
              onClick={() => void shell.windowAction(hideFloatingWindow)}
            >
              ×
            </button>
          </footer>
        </section>
      )}
    </div>
  );
}
