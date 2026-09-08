import { expect, test, type Page } from "@playwright/test";

const navigation = ["概览", "账户与 Provider", "刷新队列", "状态", "设置"];

async function expectDesktopSidebar(page: Page) {
  const sidebar = page.locator(".sidebar");
  const main = page.locator("#main");
  await expect(sidebar).toBeVisible();
  const sidebarBox = await sidebar.boundingBox();
  const mainBox = await main.boundingBox();
  expect(sidebarBox).not.toBeNull();
  expect(mainBox).not.toBeNull();
  expect(sidebarBox?.x).toBe(0);
  expect(sidebarBox?.width).toBe(240);
  expect(mainBox!.x).toBeGreaterThanOrEqual(sidebarBox!.x + sidebarBox!.width);
}

test("prototype covers primary navigation and host-owned actions", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "额度总览", level: 1 })).toBeVisible();
  await expect(page.getByText("窗口额度 · 周 → 5小时")).toBeVisible();
  await expect(page.locator("[data-transport=fixture]")).toBeVisible();

  await page.getByRole("button", { name: "账户与 Provider" }).click();
  await expect(page.locator("[data-sidebar-position=left]")).toBeVisible();
  await expect(page.getByRole("heading", { name: "已配置 Provider" })).toBeVisible();
  await page.getByRole("button", { name: "添加 Provider" }).click();
  await expect(page.getByRole("status")).toContainText("临时测试账户已添加");
  await expect(page.getByRole("heading", { name: "Fixture · 临时测试账户" })).toBeVisible();

  await page.getByRole("button", { name: "设置" }).click();
  await expect(page.locator("[data-sidebar-position=left]")).toBeVisible();
  await page.getByRole("button", { name: "导出脱敏诊断" }).click();
  await expect(page.getByRole("status")).toContainText("脱敏诊断已导出");
  await expect(page.getByText("当前版本未启用")).toHaveCount(1);
  await expect(page.getByRole("button", { name: "保存设置" })).toHaveCount(0);
  await page.getByRole("button", { name: "清理本机数据" }).click();
  await expect(page.getByRole("status")).toContainText("没有更改数据");
});

test("failure, empty, offline and responsive states remain operable", async ({ page }) => {
  await page.goto("/?scenario=keychain-locked");
  await page.getByRole("button", { name: "全部刷新" }).click();
  await expect(page.getByRole("status")).toContainText("macOS 登录钥匙串已锁定；解锁后再刷新");

  await page.goto("/?scenario=outcome-unknown");
  await page.getByRole("button", { name: "全部刷新" }).click();
  await expect(page.getByRole("status")).toContainText("刷新结果未知");

  await page.goto("/?scenario=partial");
  await page.getByRole("button", { name: "全部刷新" }).click();
  await expect(page.getByRole("status")).toContainText("部分刷新未完成");

  await page.goto("/?scenario=empty");
  await expect(page.getByTestId("empty-state")).toBeVisible();
  await page.getByRole("button", { name: "添加第一个账户" }).click();
  await expect(page.getByTestId("empty-state")).not.toBeVisible();
  await expect(page.getByText(/1 Provider ·/)).toBeVisible();
  await page.getByRole("button", { name: "账户与 Provider" }).click();
  await expect(page.getByRole("heading", { name: "Fixture · 临时测试账户" })).toBeVisible();

  await page.goto("/?scenario=offline");
  await expect(page.getByRole("status")).toContainText("当前离线");
  await expect(page.getByRole("button", { name: "全部刷新" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "重新连接本机服务" })).toBeEnabled();

  await page.setViewportSize({ width: 1024, height: 768 });
  await page.getByRole("button", { name: "账户与 Provider" }).click();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  expect(await page.evaluate(() => [...document.querySelectorAll(".provider-card")].every((card) => card.scrollWidth <= card.clientWidth))).toBe(true);

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.getByRole("article", { name: /5 小时窗口 · 72% · 可用/u })).toBeVisible();
  await expect(page.locator(".quota-row .status")).toHaveText("可用");
  await expect(page.getByRole("button", { name: "设置" })).toBeVisible();
  await page.getByRole("button", { name: "设置" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Provider 行为" })).toBeVisible();
});

test("launch catalog separates creatable, blocked and information products", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "账户与 Provider" }).click();

  const catalog = page.locator("[data-provider-id]");
  await expect(catalog).toHaveCount(10);
  await expect(catalog.locator("button:enabled")).toHaveCount(5);
  await expect(catalog.locator("button:disabled")).toHaveCount(5);

  expect(await catalog.evaluateAll((cards) => cards.map((card) => card.getAttribute("data-provider-id")))).toEqual([
    "deepseek-api-balance-cn", "kimi-api-balance-cn", "kimi-code-token-plan",
    "minimax-token-plan-cn", "glm-coding-plan-cn", "volcengine-ark-agent-plan-personal",
    "volcengine-billing-balance", "bailian-coding-plan", "bailian-token-plan-personal", "xiaomi-mimo-token-plan",
  ]);

  const search = page.getByRole("textbox", { name: "搜索 Provider Preset" });
  await search.fill("Cursor");
  await expect(catalog).toHaveCount(0);
  await expect(page.getByText("没有匹配的 Provider")).toBeVisible();
  await search.fill("");

  const filter = page.getByRole("group", { name: "Provider 能力筛选" });
  const filterButtons = filter.getByRole("button");
  const filterBox = await filter.boundingBox();
  const filterButtonBoxes = await filterButtons.evaluateAll((buttons) => buttons.map((button) => {
    const box = button.getBoundingClientRect();
    return { bottom: box.bottom, top: box.top };
  }));
  expect(filterBox).not.toBeNull();
  expect(filterButtonBoxes).toHaveLength(3);
  expect(new Set(filterButtonBoxes.map(({ top }) => top)).size).toBe(1);
  expect(filterButtonBoxes.every(({ bottom }) => bottom <= filterBox!.y + filterBox!.height))
    .toBe(true);

  await filter.getByRole("button", { name: "Window View" }).click();
  await expect(catalog).toHaveCount(6);
  await expect(page.locator('[data-provider-id="xiaomi-mimo-token-plan"]')).toHaveCount(0);

  await filter.getByRole("button", { name: "Wallet View" }).click();
  await expect(catalog).toHaveCount(4);
  await expect(page.locator('[data-provider-id="volcengine-billing-balance"] button')).toBeDisabled();

  for (const width of [1024, 390]) {
    await page.setViewportSize({ width, height: 844 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
    expect(await page.evaluate(() => [...document.querySelectorAll(".preset-card")]
      .every((card) => card.scrollWidth <= card.clientWidth))).toBe(true);
  }
});

test("latest prototype keeps five operable navigation items and a left sidebar", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/");
  await expect(page.locator(".nav-item")).toHaveCount(5);
  await expectDesktopSidebar(page);

  for (const name of navigation) {
    await page.getByRole("button", { name, exact: true }).click();
    await expect(page.locator('[aria-current="page"]')).toHaveCount(1);
    await expectDesktopSidebar(page);
  }

  await page.getByRole("button", { name: "账户与 Provider", exact: true }).click();
  await expectDesktopSidebar(page);
  await page.getByRole("button", { name: "设置", exact: true }).click();
  await expectDesktopSidebar(page);
  await page.getByRole("button", { name: "刷新队列", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Global Refresh" })).toBeVisible();
  await expect(page.getByText("等待手动刷新", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "状态", exact: true }).click();
  await expect(page.getByText("fixture scheduler_state: healthy", { exact: true })).toBeVisible();

  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  for (const name of navigation) {
    await page.getByRole("button", { name, exact: true }).click();
    await expect(page.locator('[aria-current="page"]')).toHaveCount(1);
  }
});
