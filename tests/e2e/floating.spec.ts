import { expect, test } from "@playwright/test";

test("floating hover, pin, keyboard, scrolling and return to main work", async ({ page }) => {
  await page.setViewportSize({ width: 384, height: 536 });
  await page.goto("/?surface=floating&scenario=floating");
  const trigger = page.getByRole("button", { name: "展开用量悬浮窗" });
  await expect(trigger).toHaveAttribute("aria-expanded", "false");
  await trigger.hover();
  await expect(page.getByRole("heading", { name: "用量速览" })).toBeVisible();
  await expect(page.getByText("演示数据 · 本机最近快照")).toBeVisible();
  const categories = page.getByRole("group", { name: "额度分类" });
  await expect(categories.getByRole("button")).toHaveText(["Window View", "Wallet View"]);
  const windowProviders = page.getByRole("group", { name: "窗口额度供应商" });
  await expect(windowProviders.getByRole("button")).toHaveText(["GLM", "MiniMax", "Kimi Code"]);
  await expect(page.locator(".floating-provider")).toHaveCount(1);
  await expect(page.locator(".floating-quota-row p")).toHaveText(["5小时 · 已用 24%", "周额度 · 剩余 68%"]);
  await windowProviders.getByRole("button", { name: "MiniMax", exact: true }).click();
  await expect(page.getByRole("region", { name: "MiniMax", exact: true })).toContainText("不可用");
  await categories.getByRole("button", { name: "Wallet View" }).click();
  const walletProviders = page.getByRole("group", { name: "钱包余额供应商" });
  await expect(walletProviders.getByRole("button")).toHaveText(["DeepSeek", "Kimi"]);
  await expect(page.getByRole("region", { name: "DeepSeek", exact: true })).toContainText("CNY 128.60");
  await expect(page.getByRole("meter")).toHaveCount(0);
  await expect(page.getByRole("region", { name: "MiniMax", exact: true })).toHaveCount(0);
  await page.getByRole("heading", { name: "用量速览" }).click();
  await page.screenshot({ path: "output/playwright/floating-wallet-view.png" });
  await walletProviders.getByRole("button", { name: "Kimi", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("region", { name: "Kimi", exact: true })).toContainText("CNY 64.20");
  await categories.getByRole("button", { name: "Window View" }).click();
  await expect(windowProviders.getByRole("button", { name: "MiniMax", exact: true })).toHaveAttribute("aria-pressed", "true");
  await windowProviders.getByRole("button", { name: "GLM", exact: true }).click();
  await page.getByRole("heading", { name: "用量速览" }).click();
  await page.screenshot({ path: "output/playwright/floating-window-view.png" });
  await page.getByRole("button", { name: "保持展开" }).click();
  await page.mouse.move(0, 0);
  await expect(page.getByRole("button", { name: "保持展开" })).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "刷新用量" }).click();
  await expect(page.getByRole("status")).toHaveText("额度已刷新。");
  await page.keyboard.press("Escape");
  await expect(trigger).toHaveAttribute("aria-expanded", "false");
  await page.keyboard.press("Enter");
  await expect(trigger).toHaveAttribute("aria-expanded", "true");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await expect(windowProviders.getByRole("button", { name: "GLM", exact: true })).toHaveAttribute("aria-pressed", "true");
  await page.screenshot({ path: "output/playwright/floating-expanded.png" });
  await page.getByRole("button", { name: "主窗口 ↗" }).click();
  await expect(page.getByRole("heading", { name: "额度总览", level: 1 })).toBeVisible();
});

test("floating empty, offline and unknown outcomes remain honest", async ({ page }) => {
  await page.setViewportSize({ width: 384, height: 536 });
  for (const scenario of ["empty", "offline", "outcome-unknown"]) {
    await page.goto(`/?surface=floating&scenario=${scenario}`);
    await page.getByRole("button", { name: "展开用量悬浮窗" }).hover();
    if (scenario === "empty") await expect(page.getByRole("button", { name: "前往主窗口添加" })).toBeVisible();
    if (scenario === "offline") {
      await expect(page.getByText("最近缓存 · 待刷新", { exact: false })).toBeVisible();
      await expect(page.getByRole("button", { name: "重新连接" })).toBeVisible();
      await expect(page.getByRole("button", { name: "刷新用量" })).toHaveCount(0);
    }
    if (scenario === "outcome-unknown") {
      await page.getByRole("button", { name: "刷新用量" }).click();
      await expect(page.getByRole("status")).toContainText("刷新结果未知");
    }
  }
});
