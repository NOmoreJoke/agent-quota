import { expect, test } from "@playwright/test";

const views = ["概览", "账户与 Provider", "刷新队列", "状态", "设置"];

test("main and floating windows share light/dark appearance and preserve it on reload", async ({ page, context }) => {
  await page.goto("/?scenario=floating");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  const floating = await context.newPage();
  await floating.setViewportSize({ width: 384, height: 536 });
  await floating.goto("/?surface=floating&scenario=floating");
  await floating.getByRole("button", { name: "展开用量悬浮窗" }).hover();
  await floating.getByRole("button", { name: "保持展开" }).click();

  for (const theme of ["dark", "light"] as const) {
    await page.getByRole("button", { name: theme === "dark" ? "深色" : "浅色", exact: true }).click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
    await expect(floating.locator("html")).toHaveAttribute("data-theme", theme);
    const background = theme === "dark" ? "rgb(28, 25, 23)" : "rgb(255, 255, 255)";
    const panel = theme === "dark" ? "rgb(33, 30, 27)" : "rgb(255, 255, 255)";
    for (const view of views) {
      await page.getByRole("button", { name: view, exact: true }).click();
      await expect(page.locator(".app")).toHaveCSS("background-color", background);
      await expect(page.getByRole("group", { name: "外观主题" })).toBeVisible();
      await expect(page.getByRole("button", { name: theme === "dark" ? "深色" : "浅色", exact: true })).toHaveAttribute("aria-pressed", "true");
    }
    await expect(floating.locator("html")).toHaveCSS("background-color", "rgba(0, 0, 0, 0)");
    await expect(floating.locator("body")).toHaveCSS("background-color", "rgba(0, 0, 0, 0)");
    await expect(floating.locator(".floating-shell")).toHaveCSS("background-color", panel);
    await floating.getByRole("button", { name: "Wallet View", exact: true }).click();
    await expect(floating.getByRole("region", { name: "DeepSeek", exact: true })).toContainText("CNY 128.60");
    await floating.screenshot({ path: `output/playwright/appearance-floating-${theme}.png` });
    await page.getByRole("button", { name: "概览", exact: true }).click();
    await page.screenshot({ path: `output/playwright/appearance-main-${theme}.png` });
    await page.reload();
    await floating.reload();
    await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
    await expect(floating.locator("html")).toHaveAttribute("data-theme", theme);
    await floating.getByRole("button", { name: "展开用量悬浮窗" }).hover();
    await floating.getByRole("button", { name: "保持展开" }).click();
    await floating.getByRole("button", { name: "Window View", exact: true }).click();
  }

  await page.setViewportSize({ width: 390, height: 844 });
  for (const view of views) {
    await page.getByRole("button", { name: view, exact: true }).click();
    await page.getByRole("button", { name: "深色", exact: true }).click();
    await expect(page.getByRole("group", { name: "外观主题" })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
});

test("saved dark appearance is applied before the React bundle and invalid preferences fall back to light", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "深色", exact: true }).click();
  let release: (() => void) | undefined;
  const bundleGate = new Promise<void>((resolve) => { release = resolve; });
  await page.route("**/src/main.tsx", async (route) => { await bundleGate; await route.continue(); });
  await page.reload({ waitUntil: "commit" });
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.locator("html")).toHaveCSS("background-color", "rgb(28, 25, 23)");
  await expect(page.locator("#root")).toBeEmpty();
  release?.();
  await expect(page.getByRole("group", { name: "外观主题" })).toBeVisible();
  await page.unroute("**/src/main.tsx");
  await page.evaluate(() => window.localStorage.setItem("agent-quota.appearance.v1", "system"));
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
});

test("floating surface stays transparent before its React bundle in both saved themes", async ({ page }) => {
  for (const theme of ["dark", "light"] as const) {
    await page.goto("/");
    await page.getByRole("button", { name: theme === "dark" ? "深色" : "浅色", exact: true }).click();
    let release: (() => void) | undefined;
    const bundleGate = new Promise<void>((resolve) => { release = resolve; });
    await page.route("**/src/main.tsx", async (route) => { await bundleGate; await route.continue(); });
    await page.goto("/?surface=floating", { waitUntil: "commit" });
    await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
    await expect(page.locator("html")).toHaveCSS("background-color", "rgba(0, 0, 0, 0)");
    await expect(page.locator("body")).toHaveCSS("background-color", "rgba(0, 0, 0, 0)");
    await expect(page.locator("#root")).toBeEmpty();
    release?.();
    await expect(page.getByRole("button", { name: "展开用量悬浮窗" })).toBeVisible();
    await expect(page.locator("html")).toHaveCSS("background-color", "rgba(0, 0, 0, 0)");
    await expect(page.locator("body")).toHaveCSS("background-color", "rgba(0, 0, 0, 0)");
    await page.unroute("**/src/main.tsx");
  }
});

test("empty and offline states keep the selected palette in both surfaces", async ({ page }) => {
  await page.goto("/");
  for (const theme of ["dark", "light"]) {
    await page.goto("/");
    await page.getByRole("button", { name: theme === "dark" ? "深色" : "浅色", exact: true }).click();
    for (const scenario of ["empty", "offline"]) {
      await page.goto(`/?scenario=${scenario}`);
      await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
      await expect(page.getByRole("group", { name: "外观主题" })).toBeVisible();
      if (scenario === "empty") await expect(page.getByTestId("empty-state")).toBeVisible();
      else await expect(page.getByText("当前离线：展示最近一次本机缓存；写操作已暂停。")).toBeVisible();
      await page.goto(`/?surface=floating&scenario=${scenario}`);
      await page.getByRole("button", { name: "展开用量悬浮窗" }).hover();
      await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
      if (scenario === "empty") await expect(page.getByRole("button", { name: "前往主窗口添加" })).toBeVisible();
      else await expect(page.getByRole("button", { name: "重新连接" })).toBeVisible();
    }
  }
});
