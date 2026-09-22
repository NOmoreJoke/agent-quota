import { useAppearance } from "./appearance";

export function AppearanceSwitch() {
  const { theme, persisted, setTheme } = useAppearance();
  return <section className="appearance" aria-label="外观设置">
    <span className="appearance-label">外观</span>
    <div className="appearance-switch" role="group" aria-label="外观主题">
      <button type="button" aria-pressed={theme === "light"} onClick={() => setTheme("light")}><span aria-hidden="true">☀</span>浅色</button>
      <button type="button" aria-pressed={theme === "dark"} onClick={() => setTheme("dark")}><span aria-hidden="true">☾</span>深色</button>
    </div>
    {persisted && <small className="appearance-hint">同步主窗口与悬浮窗</small>}
    {!persisted && <small role="status">外观偏好未能保存，本次窗口仍已切换。</small>}
  </section>;
}
