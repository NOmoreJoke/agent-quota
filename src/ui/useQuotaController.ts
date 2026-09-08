import { useCallback, useEffect, useRef, useState } from "react";
import { invokeHost, transportMode } from "../host/transport";
import { safeErrorMessage, type Account, type Capability, type Scheduler } from "./quotaPresentation";

type Notice = { tone: "danger" | "info" | "success" | "warning"; text: string };
type RefreshState = {
  phase: "idle" | "running" | "completed";
  outcome: "none" | "success" | "warning" | "error";
  text: string;
};

class InactiveView extends Error {}

function readableError(error: unknown): string {
  return error instanceof Error ? error.message : "发生未知错误";
}

export function useQuotaController() {
  const [loading, setLoading] = useState(true);
  const [connection, setConnection] = useState<"checking" | "ready" | "offline" | "unavailable">("checking");
  const mounted = useRef(false);
  const lifetime = useRef(0);
  const [offline, setOffline] = useState(false);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [capabilities, setCapabilities] = useState<Capability[]>([]);
  const [freshness, setFreshness] = useState("stale");
  const [scheduler, setScheduler] = useState<Scheduler>({ health: "absent", installed: false });
  const [notice, setNotice] = useState<Notice | null>(null);
  const [busy, setBusy] = useState(false);
  const actionPending = useRef(false);
  const loadVersion = useRef(0);
  const [refreshState, setRefreshState] = useState<RefreshState>({
    phase: "idle", outcome: "none", text: "等待手动刷新",
  });

  const callHost = useCallback(async (...args: Parameters<typeof invokeHost>) => {
    const version = lifetime.current;
    if (!mounted.current) throw new InactiveView();
    const result = await invokeHost(...args);
    if (!mounted.current || version !== lifetime.current) throw new InactiveView();
    return result;
  }, []);

  const load = useCallback(async (): Promise<boolean> => {
    if (!mounted.current) return false;
    const version = ++loadVersion.current;
    setLoading(true);
    setConnection("checking");
    setNotice(null);
    try {
      const results = await Promise.all([
        callHost("bootstrap_state", {}),
        callHost("accounts_read", { scope_ref: "scope-all" }),
        callHost("quota_overview", { scope_ref: "scope-all" }),
        callHost("scheduler_state", {}),
      ]);
      if (version !== loadVersion.current) return false;
      const [bootstrap, accountResult, quotaResult, schedulerResult] = results;
      const appState = bootstrap.application_state as { offline: boolean };
      setOffline(appState.offline);
      for (const result of results) {
        if (result.status !== "ok") {
          const error = result.safe_error as { code?: string } | undefined;
          throw new Error(safeErrorMessage(error?.code ?? "provider-unavailable"));
        }
      }
      const projection = quotaResult.projection as { capability_rows: Capability[]; freshness: string };
      setAccounts(accountResult.accounts as Account[]);
      setCapabilities(projection.capability_rows);
      setFreshness(projection.freshness);
      setScheduler(schedulerResult.scheduler_state as Scheduler);
      setConnection(appState.offline ? "offline" : "ready");
      return true;
    } catch (error) {
      if (mounted.current && version === loadVersion.current) {
        setConnection("unavailable");
        setFreshness("stale");
        setNotice({ tone: "danger", text: `无法载入本机状态：${readableError(error)}` });
      }
      return false;
    } finally {
      if (version === loadVersion.current) setLoading(false);
    }
  }, [callHost]);

  useEffect(() => {
    mounted.current = true;
    void load();
    return () => {
      mounted.current = false;
      lifetime.current += 1;
      loadVersion.current += 1;
    };
  }, [load]);

  const runAction = async (label: string, action: () => Promise<void>, readOnly = false) => {
    if (!mounted.current || actionPending.current || (!readOnly && connection !== "ready")) return;
    actionPending.current = true;
    setBusy(true);
    try {
      await action();
    } catch (error) {
      if (mounted.current && !(error instanceof InactiveView)) {
        setNotice({ tone: "danger", text: `${label}失败：${readableError(error)}` });
      }
    } finally {
      actionPending.current = false;
      if (mounted.current) setBusy(false);
    }
  };

  const refresh = (scopeRef = "scope-all") => runAction("刷新", async () => {
    setRefreshState({ phase: "running", outcome: "none", text: "正在请求 host" });
    setNotice({ tone: "info", text: "正在刷新 Provider 额度…" });
    try {
      const result = await callHost("refresh_scope", { scope_ref: scopeRef });
      const safeError = result.safe_error as { code?: string } | undefined;
      const phase = (result.refresh_state as { phase: string }).phase;
      if (safeError?.code === "outcome-unknown") {
        setRefreshState({ phase: "completed", outcome: "warning", text: "刷新结果未知；请先检查账户状态" });
        setNotice({ tone: "warning", text: "刷新结果未知。为避免重复操作，请先检查账户状态，再手动重试。" });
      } else if (safeError?.code || result.status !== "ok" || phase === "failed") {
        const loaded = await load();
        const message = safeErrorMessage(safeError?.code ?? "provider-unavailable");
        setRefreshState({ phase: "completed", outcome: "warning", text: `部分刷新未完成：${message}` });
        if (loaded) setNotice({ tone: "warning", text: `部分刷新未完成：${message}；已保留成功结果与最近缓存。` });
      } else if (phase === "running") {
        setRefreshState({ phase: "running", outcome: "none", text: "host 仍在后台刷新" });
        setNotice({ tone: "info", text: "刷新仍在后台运行，可在刷新队列查看状态。" });
      } else if (await load()) {
        setRefreshState({ phase: "completed", outcome: "success", text: "额度已刷新" });
        setNotice({ tone: "success", text: "额度已刷新。" });
      } else {
        setRefreshState({ phase: "completed", outcome: "warning", text: "刷新请求已完成，但本机状态未能重新载入" });
      }
    } catch (error) {
      setRefreshState({ phase: "completed", outcome: "error", text: `刷新失败：${readableError(error)}` });
      throw error;
    }
  });

  const reportActionError = (result: Record<string, unknown>, label: string): boolean => {
    const error = result.safe_error as { code?: string } | undefined;
    if (!error?.code) return false;
    setFreshness("stale");
    setNotice({
      tone: "warning",
      text: error.code === "outcome-unknown"
        ? `${label}结果未知；请检查账户状态，勿重复提交。`
        : `${label}未完整完成：${safeErrorMessage(error.code)}；请检查账户状态。`,
    });
    return true;
  };

  const nativeCredential = () => runAction("添加账户", async () => {
    const result = await callHost("credential_dialog_open", { dialog_purpose: "create-credential-reference" });
    if (result.opaque_reference_status === "reference-created" && !await load()) return;
    if (reportActionError(result, "添加凭据")) return;
    const safeError = result.safe_error as { code?: string } | undefined;
    setNotice({
      tone: result.status === "ok" ? "success" : "info",
      text: result.status === "ok"
        ? transportMode === "fixture" ? "临时测试账户已添加；刷新页面会重置。" : "Provider 已添加并保存到 Keychain。"
        : result.opaque_reference_status === "reference-created"
          ? `凭据已保存，但首次查询失败：${safeErrorMessage(safeError?.code ?? "provider-unavailable")}。`
          : "原生凭据窗口已取消；Renderer 从不接收密钥正文。",
    });
  });

  const reauthenticate = (principalRef: string) => runAction("重新认证", async () => {
    const result = await callHost("reauthenticate", { principal_ref: principalRef });
    const error = result.safe_error as { code?: string } | undefined;
    if (error?.code === "outcome-unknown" && reportActionError(result, "重新认证")) return;
    if (!await load()) return;
    if (reportActionError(result, "重新认证")) return;
    setNotice({ tone: result.status === "ok" ? "success" : "danger", text: result.reauth_state === "pending" ? "请在原生窗口完成重新认证。" : result.status === "ok" ? "重新认证并刷新完成。" : "重新认证失败。" });
  });

  const destructive = (intent: "delete" | "purge", selection: string) => runAction(intent === "delete" ? "删除" : "清理", async () => {
    const result = await callHost("destructive_confirmation_open", { operation_intent: intent, opaque_selection_handle: selection });
    if (reportActionError(result, intent === "delete" ? "删除" : "清理")) return;
    if (result.status === "committed" && !await load()) return;
    const committed = result.status === "committed";
    setNotice({
      tone: committed ? "success" : "info",
      text: intent === "delete"
        ? committed ? "账户及 Keychain 凭据已删除。" : "删除已取消。"
        : committed ? "本机数据已由原生流程清理。" : "原生清理确认已取消；没有更改数据。",
    });
  });

  const exportRedacted = () => runAction("导出", async () => {
    const result = await callHost("export_redacted", { export_profile: "redacted-diagnostics", scope_ref: "scope-all" });
    const status = result.export_status;
    setNotice({
      tone: status === "completed" ? "success" : status === "cancelled" ? "info" : "danger",
      text: status === "completed" ? "脱敏诊断已导出。" : status === "cancelled" ? "导出已取消；没有写入文件。" : "导出失败。",
    });
  });

  const retryLoad = () => runAction("重新连接", async () => { await load(); }, true);

  return {
    connection, retryLoad, loading, offline, accounts, capabilities, freshness, scheduler, notice, setNotice,
    busy, refreshState, refresh, nativeCredential, reauthenticate, destructive, exportRedacted,
  };
}
