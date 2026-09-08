import { useMemo, useState } from "react";
import { transportMode } from "../host/transport";
import { filterProducts, productStatus } from "./launchProducts";
import { useQuotaController } from "./useQuotaController";
import {
  providerOrder, safeErrorMessage, providerName, providerFromAccount,
  windowMetric, displayedHealth, isWeeklyWindow, windowFamily,
  compareWindowOrder, effectiveHealth,
} from "./quotaPresentation";

type View = "overview" | "accounts" | "queue" | "status" | "settings";
type OverviewMode = "window" | "wallet";
const nav: { id: View; label: string; icon: string }[] = [
  { id: "overview", label: "概览", icon: "grid" },
  { id: "accounts", label: "账户与 Provider", icon: "users" },
  { id: "queue", label: "刷新队列", icon: "refresh" },
  { id: "status", label: "状态", icon: "activity" },
  { id: "settings", label: "设置", icon: "settings" },
];

function Icon({ name }: { name: string }) {
  const common = {
    fill: "none",
    stroke: "currentColor",
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    strokeWidth: 1.8,
  };
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" {...common}>
      {name === "grid" && <><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></>}
      {name === "users" && <><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/></>}
      {name === "refresh" && <><path d="M20 7h-5V2"/><path d="M20 7a9 9 0 1 0 1 9"/></>}
      {name === "activity" && <polyline points="3 12 7 12 10 3 14 21 17 12 21 12"/>}
      {name === "settings" && <><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.83 2.83-.06-.06A1.7 1.7 0 0 0 15 19.4a1.7 1.7 0 0 0-1 .6 1.7 1.7 0 0 0-.4 1.1V21h-4v-.1A1.7 1.7 0 0 0 8.6 19.4a1.7 1.7 0 0 0-1.88.34l-.06.06-2.83-2.83.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-.6-1 1.7 1.7 0 0 0-1.1-.4H3v-4h.1A1.7 1.7 0 0 0 4.6 8.6a1.7 1.7 0 0 0-.34-1.88l-.06-.06 2.83-2.83.06.06A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-.6 1.7 1.7 0 0 0 .4-1.1V3h4v.1A1.7 1.7 0 0 0 15.4 4.6a1.7 1.7 0 0 0 1.88-.34l.06-.06 2.83 2.83-.06.06A1.7 1.7 0 0 0 19.4 9c.14.37.35.7.6 1 .3.3.7.43 1.1.4h.1v4h-.1c-.4-.03-.8.1-1.1.4-.25.3-.46.63-.6 1Z"/></>}
      {name === "search" && <><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></>}
      {name === "plus" && <><path d="M12 5v14M5 12h14"/></>}
    </svg>
  );
}

const STATUS_LABELS: Readonly<Record<string, string>> = {
    active: "已配置",
    disabled: "已停用",
    "needs-reauth": "需重新认证",
    ok: "可用",
    exhausted: "已用尽",
    unavailable: "不可用",
    error: "异常",
    incompatible: "不兼容",
    unsupported: "不支持",
    running: "刷新中",
    done: "完成",
    queued: "等待中",
    idle: "等待中",
};

function statusLabel(value: string): string {
  return STATUS_LABELS[value] ?? value;
}

function StatusPill({ value }: { value: string }) {
  return <span className={`status status-${value}`}><i />{statusLabel(value)}</span>;
}

function EmptyState({ onAdd, disabled }: { onAdd: () => void; disabled: boolean }) {
  return (
    <section className="empty panel" data-testid="empty-state">
      <div className="empty-mark">□</div>
      <h2>未发现可用 Subject</h2>
      <p>前往「账户与 Provider」完成首次配置</p>
      <button type="button" className="primary" data-action="add-credential" disabled={disabled} onClick={onAdd}>
        添加第一个账户
      </button>
    </section>
  );
}

function ContractNote() {
  return (
    <div className="contract-note" role="note">
      <span className="note-icon">i</span>
      <span>凭据仅保存在 macOS Keychain · Renderer 隔离 · Provider 查询只读</span>
      <span className="contract-link">本机安全边界 →</span>
    </div>
  );
}

export function App() {
  const [view, setView] = useState<View>("overview");
  const [overviewMode, setOverviewMode] = useState<OverviewMode>("window");
  const [query, setQuery] = useState("");
  const [providerQuery, setProviderQuery] = useState("");
  const [providerMode, setProviderMode] = useState<"all" | OverviewMode>("all");
  const {
    connection, retryLoad, loading, offline, accounts, capabilities, freshness, scheduler, notice, setNotice,
    busy, refreshState, refresh, nativeCredential, reauthenticate, destructive, exportRedacted,
  } = useQuotaController();

  const actionsDisabled = busy || loading || connection !== "ready";
  const connectionLabel = { checking: "正在连接", ready: "本机服务正常", offline: "Sidecar 离线", unavailable: "本机连接失败" }[connection];

  const filteredCapabilities = useMemo(() => {
    const kind = overviewMode === "window" ? "window" : "balance";
    const normalized = query.trim().toLowerCase();
    return capabilities.filter((row) => row.display_kind === kind && (!normalized || `${providerName(row.capability_ref)} ${row.value_display}`.toLowerCase().includes(normalized)));
  }, [capabilities, overviewMode, query]);

  const groupedCapabilities = useMemo(() => providerOrder.map((provider) => ({
    provider,
    rows: filteredCapabilities
      .filter((row) => providerName(row.capability_ref) === provider)
      .map((row, sourceIndex) => ({ row, sourceIndex }))
      .sort(compareWindowOrder)
      .map(({ row }) => row),
  })).filter((group) => group.rows.length > 0), [filteredCapabilities]);

  const exhaustedWeeklyFamilies = useMemo(() => new Set(capabilities
    .filter((row) => isWeeklyWindow(row) && displayedHealth(row) === "exhausted")
    .map(windowFamily)), [capabilities]);

  const filteredProviders = useMemo(() => filterProducts(providerQuery, providerMode), [providerMode, providerQuery]);

  const pageTitle = view === "overview" ? "额度总览" : nav.find((item) => item.id === view)?.label;

  return (
    <div
      className="app"
      data-sidebar-position="left"
      data-transport={transportMode}
    >
      <a className="skip-link" href="#main">跳至主要内容</a>
      <aside className="sidebar" aria-label="主导航">
        <div className="brand">Agent Quota</div>
        <nav>
          {nav.map((item) => (
            <button type="button" key={item.id} className={view === item.id ? "nav-item active" : "nav-item"} aria-current={view === item.id ? "page" : undefined} onClick={() => setView(item.id)}>
              <Icon name={item.icon}/><span>{item.label}</span>
            </button>
          ))}
        </nav>
        <div className="sidebar-foot"><span className={connection === "ready" ? "health-dot" : "health-dot offline"}/>{connectionLabel}</div>
      </aside>

      <main id="main" tabIndex={-1}>
        <header className="topbar">
          <div>
            <h1>{pageTitle}</h1>
            {view === "overview" && <p>{accounts.length} Provider · {capabilities.length} Subject · {freshness === "fresh" ? "数据已更新" : "缓存数据"}</p>}
            {view === "accounts" && <p>管理 Provider 接入、凭据绑定、Subject 发现</p>}
            {view === "queue" && <p>全局手动刷新状态与安全结果投影</p>}
          </div>
          <div className="top-actions">
            {view === "overview" && <label className="search"><Icon name="search"/><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索 Provider / Subject" aria-label="搜索 Provider / Subject"/></label>}
            {view === "accounts" ? (
              <button type="button" className="primary" disabled={actionsDisabled} onClick={() => void nativeCredential()}><Icon name="plus"/>添加 Provider</button>
            ) : (view === "overview" || view === "queue") ? (
              <button type="button" className="primary" aria-label="全部刷新" onClick={() => void refresh()} disabled={actionsDisabled}><Icon name="refresh"/>{busy ? "刷新中…" : "全部刷新"}</button>
            ) : null}
          </div>
        </header>

        {offline && <div className="banner warning" role="status">当前离线：展示最近一次本机缓存；写操作已暂停。</div>}
        {notice && <div className={`banner ${notice.tone}`} role="status" aria-live="polite"><span>{notice.text}</span><button type="button" aria-label="关闭通知" onClick={() => setNotice(null)}>×</button></div>}

        {(connection === "unavailable" || connection === "offline") && <button type="button" className="secondary" disabled={busy || loading} onClick={() => void retryLoad()}>重新连接本机服务</button>}

        {loading ? (
          <section className="loading-grid" aria-label="正在加载"><div className="skeleton"/><div className="skeleton"/><div className="skeleton"/></section>
        ) : view === "overview" ? (
          accounts.length === 0 ? <EmptyState disabled={actionsDisabled} onAdd={() => void nativeCredential()}/> : (
            <section aria-label="额度摘要">
              <ContractNote/>
              <div className="segmented" role="group" aria-label="额度视图">
                <button type="button" className={overviewMode === "window" ? "active" : ""} onClick={() => setOverviewMode("window")}>Window View</button>
                <button type="button" className={overviewMode === "wallet" ? "active" : ""} onClick={() => setOverviewMode("wallet")}>Wallet View</button>
              </div>
              <section className="panel quota-panel">
                <h2>{overviewMode === "window" ? "窗口额度 · 周 → 5小时" : "Wallet 余额"}</h2>
                <p className="panel-copy">按 Provider 分组 · general 优先 · 展示官方只读查询投影 · 不跨 Provider 加总</p>
                {groupedCapabilities.length === 0 ? (
                  <div className="inline-empty">当前视图暂无可展示额度</div>
                ) : groupedCapabilities.map((group) => {
                  return <div className="provider-group" key={group.provider}>
                    <div className="provider-heading"><strong>{group.provider}</strong><span/></div>
                    {group.rows.map((row, index) => {
                      const progress = windowMetric(row.value_display)?.percentage ?? null;
                      const displayHealth = effectiveHealth(row, exhaustedWeeklyFamilies);
                      return (
                        <article
                          aria-label={`${row.value_display} · ${statusLabel(displayHealth)}`}
                          className={`quota-row ${displayHealth !== "ok" ? `row-${displayHealth}` : ""}`}
                          key={row.capability_ref}
                        >
                          <span className="rank">{row.display_kind === "window" ? `#${index + 1}` : "—"}</span>
                          <span className="scope-kind">{row.display_kind === "window" ? "窗口" : "余额"}<small>{row.display_kind === "window" ? "官方周期" : "钱包"}</small></span>
                          <span className="subject">{row.value_display}</span>
                          {progress === null ? <span className="balance-value">{row.value_display}</span> : <><span className="meter"><i style={{ width: `${progress}%` }}/></span><strong className={`remaining ${displayHealth === "exhausted" ? "depleted" : displayHealth === "unavailable" ? "unavailable" : ""}`}>{progress}%</strong></>}
                          <StatusPill value={displayHealth}/>
                        </article>
                      );
                    })}
                  </div>;
                })}
              </section>
            </section>
          )
        ) : view === "accounts" ? (
          <section>
            <ContractNote/>
            <h2 className="section-title">已配置 Provider</h2>
            <div className="provider-grid">
              {accounts.map((account) => (
                <article className="provider-card" key={account.principal_ref}>
                  <div className="provider-card-head"><div className="provider-avatar">{providerFromAccount(account.display_label).slice(0, 1)}</div><div><h3>{providerFromAccount(account.display_label)}</h3><p>{account.display_label}</p></div><StatusPill value={account.lifecycle}/></div>
                  <p className="last-refresh">凭据：macOS Keychain · 查询：只读</p>
                  {account.last_error_code && (
                    <p className="last-refresh">最近错误：{safeErrorMessage(account.last_error_code)}</p>
                  )}
                  <div className="provider-actions">
                    <button type="button" className="primary compact" disabled={actionsDisabled} onClick={() => { setView("queue"); void refresh(account.principal_ref); }}>刷新</button>
                    <button type="button" className="secondary compact" disabled={actionsDisabled} onClick={() => void reauthenticate(account.principal_ref)}>{account.lifecycle === "needs-reauth" ? "重新认证" : "更换凭据"}</button>
                    <button type="button" className="text-button danger-text" disabled={actionsDisabled} onClick={() => void destructive("delete", account.principal_ref)}>删除</button>
                  </div>
                </article>
              ))}
            </div>
            {accounts.length === 0 && (
              <EmptyState disabled={actionsDisabled} onAdd={() => void nativeCredential()} />
            )}
            <section className="catalog-section" aria-labelledby="provider-catalog-title">
              <div className="catalog-heading">
                <div>
                  <h2 id="provider-catalog-title" className="section-title">Provider Preset</h2>
                  <p>10 项产品 · 5 项可添加 · 2 项接入中 · 3 项仅展示</p>
                </div>
                <label className="search catalog-search"><Icon name="search"/><input value={providerQuery} onChange={(event) => setProviderQuery(event.target.value)} placeholder="搜索 Provider" aria-label="搜索 Provider Preset"/></label>
              </div>
              <div className="segmented catalog-filter" role="group" aria-label="Provider 能力筛选">
                <button type="button" className={providerMode === "all" ? "active" : ""} onClick={() => setProviderMode("all")}>全部</button>
                <button type="button" className={providerMode === "window" ? "active" : ""} onClick={() => setProviderMode("window")}>Window View</button>
                <button type="button" className={providerMode === "wallet" ? "active" : ""} onClick={() => setProviderMode("wallet")}>Wallet View</button>
              </div>
              <div className="preset-grid" data-testid="provider-preset-grid">
                {filteredProviders.map((provider) => {
                  const enabled = provider.creatable;
                  return (
                    <article className="preset-card" key={provider.product_id} data-provider-id={provider.product_id} data-product-state={provider.state}>
                      <div className="preset-title"><span>{provider.display_name.slice(0, 1)}</span><strong>{provider.display_name}</strong></div>
                      <div className="preset-capabilities">
                        {provider.capabilities.map((label) => <small className="capability" key={label}>{label}</small>)}
                      </div>
                      <p>{productStatus(provider)}</p>
                      <button type="button" className="secondary compact" disabled={!enabled || actionsDisabled} aria-label={`${provider.display_name} ${enabled ? "添加" : "不可添加"}`} onClick={() => void nativeCredential()}>{enabled ? "打开原生选择器" : "暂不可添加"}</button>
                    </article>
                  );
                })}
              </div>
              {filteredProviders.length === 0 && <div className="inline-empty">没有匹配的 Provider</div>}
            </section>
          </section>
        ) : view === "queue" ? (
          <section>
            <ContractNote/>
            <div className="panel refresh-state" aria-label="全局刷新状态">
              <h2>Global Refresh</h2>
              <p className="panel-copy">仅展示 host DTO 可证明的刷新状态，不生成 Provider 队列假象。</p>
              <StatusPill value={refreshState.phase === "running" ? "running" : refreshState.phase === "idle" ? "idle" : refreshState.outcome === "success" ? "done" : "error"}/>
              <p>{refreshState.text}</p>
            </div>
          </section>
        ) : view === "status" ? (
          <section>
            <div className={`banner ${scheduler.installed && scheduler.health === "healthy" ? "success" : "warning"}`}>SchedulerHost：{scheduler.health === "healthy" && scheduler.installed ? "健康" : scheduler.health === "unhealthy" ? "异常" : "未安装"}。{scheduler.installed && scheduler.health === "healthy" ? "可使用调度能力。" : "仅按需刷新可用；无 Renderer 定时器。"}</div>
            <div className="health-grid">
              <article className="health-card"><span>Scheduler</span><strong className={scheduler.installed && scheduler.health === "healthy" ? "ok-text" : "muted-text"}>{scheduler.health === "healthy" && scheduler.installed ? "健康" : scheduler.health === "unhealthy" ? "异常" : "未安装"}</strong><small>{transportMode === "fixture" ? "fixture scheduler_state" : "host scheduler_state"}: {scheduler.health}</small></article>
              <article className="health-card"><span>Sidecar</span><strong className={connection === "ready" ? "ok-text" : "danger-text"}>{connectionLabel}</strong><small>{offline ? "最近缓存" : "本机进程"}</small></article>
              <article className="health-card"><span>Renderer</span><strong className="ok-text">沙箱</strong><small>CSP locked</small></article>
            </div>
          </section>
        ) : (
          <section className="settings-page">
            <h2 className="settings-label">显示</h2>
            <div className="settings-panel"><div><span>主题</span><strong>浅色（固定）</strong></div><div><span>时区</span><strong>Asia/Shanghai (UTC+8)（固定）</strong></div><div><span>减少动效</span><strong>跟随系统（固定）</strong></div></div>
            <h2 className="settings-label">安全</h2>
            <div className="settings-panel"><div><span>凭据后端</span><strong>macOS Keychain（固定）</strong></div><div><span>Renderer 隔离</span><strong>已启用（默认）</strong></div><div><span>诊断日志</span><button type="button" className="text-button" disabled={actionsDisabled} onClick={() => void exportRedacted()}>导出脱敏诊断</button></div></div>
            <h2 className="settings-label">无障碍</h2>
            <div className="settings-panel"><div><span>键盘可达</span><strong>已启用</strong></div><div><span>200% 缩放</span><strong>支持</strong></div><div><span>颜色对比</span><strong>WCAG 2.2 AA</strong></div></div>
            <h2 className="settings-label">Provider 行为</h2>
            <div className="settings-panel"><div><span>刷新频率</span><strong>手动</strong></div><div><span>后台自动刷新</span><strong>当前版本未启用</strong></div><div className="settings-actions"><button type="button" className="danger-button compact" disabled={actionsDisabled} onClick={() => void destructive("purge", "selection-all-local-data")}>清理本机数据</button></div></div>
          </section>
        )}
      </main>
    </div>
  );
}
