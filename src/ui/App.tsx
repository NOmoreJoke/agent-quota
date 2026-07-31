import { useCallback, useEffect, useMemo, useState } from "react";
import { invokeHost, transportMode } from "../host/transport";

type View = "overview" | "accounts" | "settings";
type Notice = { tone: "danger" | "info" | "success" | "warning"; text: string };
type Account = { display_label: string; lifecycle: string; principal_ref: string };
type Capability = {
  capability_ref: string;
  display_kind: string;
  health: string;
  value_display: string;
};

const nav: { id: View; label: string; icon: string }[] = [
  { id: "overview", label: "额度总览", icon: "◫" },
  { id: "accounts", label: "账户管理", icon: "◎" },
  { id: "settings", label: "设置", icon: "⚙" },
];

function readableError(error: unknown): string {
  return error instanceof Error ? error.message : "发生未知错误";
}

function StatusPill({ value }: { value: string }) {
  const label: Record<string, string> = {
    active: "可用",
    disabled: "已停用",
    "needs-reauth": "需重新认证",
    ok: "正常",
    error: "异常",
    incompatible: "不兼容",
    unsupported: "不支持",
  };
  return <span className={`status status-${value}`}>{label[value] ?? value}</span>;
}

function EmptyState({ onAdd }: { onAdd: () => void }) {
  return (
    <section className="empty" data-testid="empty-state">
      <div className="empty-mark">＋</div>
      <h2>还没有可查看的账户</h2>
      <p>添加凭据后，额度会保存在本机并显示在这里。</p>
      <button
        type="button"
        className="primary"
        data-action="add-credential"
        onClick={onAdd}
      >
        添加第一个账户
      </button>
    </section>
  );
}

export function App() {
  const [view, setView] = useState<View>("overview");
  const [dark, setDark] = useState(false);
  const [loading, setLoading] = useState(true);
  const [offline, setOffline] = useState(false);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [capabilities, setCapabilities] = useState<Capability[]>([]);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setNotice(null);
    try {
      const [bootstrap, accountResult, quotaResult] = await Promise.all([
        invokeHost("bootstrap_state", {}),
        invokeHost("accounts_read", { scope_ref: "scope-all" }),
        invokeHost("quota_overview", { scope_ref: "scope-all" }),
      ]);
      const appState = bootstrap.application_state as { offline: boolean };
      const projection = quotaResult.projection as { capability_rows: Capability[] };
      setOffline(appState.offline);
      setAccounts(accountResult.accounts as Account[]);
      setCapabilities(projection.capability_rows);
      const bootError = bootstrap.safe_error as { code?: string } | undefined;
      if (bootError?.code === "provider-unavailable") {
        setNotice({
          tone: "warning",
          text: "桌面壳已启动，但本机 Sidecar 尚未连接；当前仅可检查界面与安全边界。",
        });
      }
    } catch (error) {
      setNotice({ tone: "danger", text: `无法载入本机状态：${readableError(error)}` });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const refresh = async () => {
    setRefreshing(true);
    setNotice({ tone: "info", text: "正在刷新本机额度…" });
    try {
      const result = await invokeHost("refresh_scope", { scope_ref: "scope-all" });
      const safeError = result.safe_error as { code?: string } | undefined;
      if (safeError?.code === "outcome-unknown") {
        setNotice({
          tone: "warning",
          text: "刷新结果未知。为避免重复操作，请先检查账户状态，再手动重试。",
        });
      } else if ((result.refresh_state as { phase: string }).phase === "running") {
        setNotice({ tone: "info", text: "刷新仍在后台运行，可稍后返回查看。" });
      } else {
        setNotice({ tone: "success", text: "额度已刷新。" });
      }
    } catch (error) {
      setNotice({ tone: "danger", text: `刷新失败：${readableError(error)}` });
    } finally {
      setRefreshing(false);
    }
  };

  const nativeCredential = async () => {
    try {
      const result = await invokeHost("credential_dialog_open", {
        dialog_purpose: "create-credential-reference",
      });
      if (result.status === "ok") {
        const accountResult = await invokeHost("accounts_read", { scope_ref: "scope-all" });
        setAccounts(accountResult.accounts as Account[]);
      }
      setNotice({
        tone: result.status === "ok" ? "success" : "info",
        text:
          result.status === "ok"
            ? transportMode === "fixture"
              ? "临时测试账户已添加；刷新页面会重置。"
              : "凭据引用已保存。"
            : "原生凭据窗口已取消；网页界面从不接收密钥正文。",
      });
    } catch (error) {
      setNotice({ tone: "danger", text: `添加账户失败：${readableError(error)}` });
    }
  };

  const exportRedacted = async () => {
    const result = await invokeHost("export_redacted", {
      export_profile: "redacted-diagnostics",
      scope_ref: "scope-all",
    });
    setNotice({
      tone: result.status === "ok" ? "success" : "danger",
      text: result.status === "ok" ? "脱敏诊断已导出。" : "导出失败。",
    });
  };

  const saveSettings = async () => {
    await invokeHost("config_validate_apply", {
      config_change_set: {
        changes: [
          {
            change_kind: "refresh-policy",
            change_ref: "setting-auto-refresh",
            refresh_policy: autoRefresh ? "scheduler-eligible" : "manual-only",
          },
        ],
        expected_generation: 0,
      },
    });
    setNotice({ tone: "success", text: "设置已通过校验并保存。" });
  };

  const needsReauth = useMemo(
    () => accounts.filter((account) => account.lifecycle === "needs-reauth").length,
    [accounts],
  );

  return (
    <div className={dark ? "app theme-dark" : "app"} data-transport={transportMode}>
      <a className="skip-link" href="#main">跳至主要内容</a>
      <aside className="sidebar" aria-label="主导航">
        <div className="brand" aria-label="Agent Quota">
          <span className="brand-mark">AQ</span>
          <span>Agent Quota</span>
        </div>
        <nav>
          {nav.map((item) => (
            <button
              type="button"
              key={item.id}
              className={view === item.id ? "nav-item active" : "nav-item"}
              aria-current={view === item.id ? "page" : undefined}
              onClick={() => setView(item.id)}
            >
              <span aria-hidden="true">{item.icon}</span>
              {item.label}
            </button>
          ))}
        </nav>
        <div className="sidebar-foot">
          <span className={offline ? "health-dot offline" : "health-dot"} />
          {offline ? "离线 · Sidecar 未连接" : "本机服务正常"}
          <small>{transportMode === "fixture" ? "原型数据" : "Tauri 安全通道"}</small>
        </div>
      </aside>

      <main id="main" tabIndex={-1}>
        <header className="topbar">
          <div>
            <span className="eyebrow">LOCAL QUOTA CONTROL</span>
            <h1>{nav.find((item) => item.id === view)?.label}</h1>
          </div>
          <div className="top-actions">
            <button
              type="button"
              className="icon-button"
              aria-label={dark ? "切换浅色外观" : "切换深色外观"}
              onClick={() => setDark((value) => !value)}
            >
              {dark ? "☀" : "◐"}
            </button>
            <button type="button" className="primary" onClick={() => void refresh()} disabled={refreshing}>
              {refreshing ? "刷新中…" : "刷新全部"}
            </button>
          </div>
        </header>

        {offline && (
          <div className="banner warning" role="status">
            当前离线：展示最近一次本机缓存；写操作已暂停。
          </div>
        )}
        {notice && (
          <div className={`banner ${notice.tone}`} role="status" aria-live="polite">
            {notice.text}
            <button type="button" aria-label="关闭通知" onClick={() => setNotice(null)}>×</button>
          </div>
        )}

        {loading ? (
          <section className="loading-grid" aria-label="正在加载">
            <div className="skeleton" /><div className="skeleton" /><div className="skeleton" />
          </section>
        ) : view === "overview" ? (
          accounts.length === 0 ? <EmptyState onAdd={() => void nativeCredential()} /> : (
            <section aria-label="额度摘要">
              <div className="metric-grid">
                <article className="metric-card accent">
                  <span>已连接账户</span>
                  <strong>{accounts.length}</strong>
                  <small>{needsReauth > 0 ? `${needsReauth} 个需要处理` : "全部状态正常"}</small>
                </article>
                <article className="metric-card">
                  <span>可用额度项</span>
                  <strong>{capabilities.filter((row) => row.health === "ok").length}</strong>
                  <small>跨服务统一展示</small>
                </article>
                <article className="metric-card">
                  <span>更新策略</span>
                  <strong>{autoRefresh ? "自动" : "手动"}</strong>
                  <small>敏感操作始终手动确认</small>
                </article>
              </div>
              <div className="section-heading">
                <div><span className="eyebrow">LATEST SNAPSHOT</span><h2>当前额度</h2></div>
                <span className="muted">本机脱敏结果</span>
              </div>
              <div className="quota-list">
                {capabilities.map((row) => (
                  <article className="quota-row" key={row.capability_ref}>
                    <div className={`provider-mark ${row.health}`}>{row.display_kind.slice(0, 1).toUpperCase()}</div>
                    <div className="quota-copy">
                      <strong>{row.value_display}</strong>
                      <span>{row.capability_ref.replace("cap-", "")}</span>
                    </div>
                    <StatusPill value={row.health} />
                  </article>
                ))}
              </div>
            </section>
          )
        ) : view === "accounts" ? (
          <section>
            <div className="section-heading">
              <div><span className="eyebrow">LOCAL REFERENCES</span><h2>账户与认证</h2></div>
              <button type="button" className="primary" onClick={() => void nativeCredential()}>
                添加账户
              </button>
            </div>
            <p className="boundary-note">密钥仅进入 macOS 原生安全窗口；Renderer 只接收不可逆的本机引用。</p>
            <div className="table-card" role="table" aria-label="账户列表">
              {accounts.map((account) => (
                <div className="account-row" role="row" key={account.principal_ref}>
                  <div className="avatar" aria-hidden="true">{account.display_label.slice(0, 1)}</div>
                  <div className="account-name">
                    <strong>{account.display_label}</strong>
                    <span>{account.principal_ref}</span>
                  </div>
                  <StatusPill value={account.lifecycle} />
                  {account.lifecycle === "needs-reauth" ? (
                    <button
                      type="button"
                      className="text-button"
                      onClick={async () => {
                        const result = await invokeHost("reauthenticate", {
                          principal_ref: account.principal_ref,
                        });
                        setNotice({
                          tone: "info",
                          text:
                            (result.reauth_state as string) === "pending"
                              ? "请在原生窗口完成重新认证。"
                              : "重新认证完成。",
                        });
                      }}
                    >
                      重新认证
                    </button>
                  ) : <span className="row-spacer" />}
                </div>
              ))}
            </div>
          </section>
        ) : (
          <section className="settings-grid">
            <article className="settings-card">
              <span className="eyebrow">REFRESH</span>
              <h2>刷新策略</h2>
              <label className="switch-row">
                <span><strong>后台自动刷新</strong><small>仅执行只读额度查询</small></span>
                <input
                  type="checkbox"
                  checked={autoRefresh}
                  onChange={(event) => setAutoRefresh(event.target.checked)}
                />
              </label>
              <button type="button" className="primary" onClick={() => void saveSettings()}>
                保存设置
              </button>
            </article>
            <article className="settings-card">
              <span className="eyebrow">PRIVACY</span>
              <h2>诊断与导出</h2>
              <p>仅导出脱敏状态、版本与错误代码；不包含凭据、Cookie、请求头或本机路径。</p>
              <button type="button" className="secondary" onClick={() => void exportRedacted()}>
                导出脱敏诊断
              </button>
            </article>
            <article className="settings-card danger-zone">
              <span className="eyebrow">DESTRUCTIVE</span>
              <h2>清理本机数据</h2>
              <p>删除前必须进入宿主拥有的原生确认面，网页界面不能直接提交。</p>
              <button
                type="button"
                className="danger-button"
                onClick={async () => {
                  const result = await invokeHost("destructive_confirmation_open", {
                    operation_intent: "purge",
                    opaque_selection_handle: "selection-all-local-data",
                  });
                  setNotice({
                    tone: "info",
                    text:
                      result.status === "committed"
                        ? "本机数据已由原生流程清理。"
                        : "原生清理确认已取消；没有更改数据。",
                  });
                }}
              >
                打开原生清理确认
              </button>
            </article>
          </section>
        )}
      </main>
    </div>
  );
}
