import { expect, test } from "@playwright/test";

test("prototype covers primary navigation and host-owned actions", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "额度总览", level: 1 })).toBeVisible();
  await expect(page.getByText("窗口使用率 · 降序")).toBeVisible();
  await expect(page.locator("[data-transport=fixture]")).toBeVisible();

  await page.getByRole("button", { name: "账户与 Provider" }).click();
  await expect(page.locator("[data-sidebar-position=right]")).toBeVisible();
  await expect(page.getByRole("heading", { name: "已启用 Provider" })).toBeVisible();
  await page.getByRole("button", { name: "添加 Provider" }).click();
  await expect(page.getByRole("status")).toContainText("临时测试账户已添加");
  await expect(page.getByRole("heading", { name: "Fixture · 临时测试账户" })).toBeVisible();

  await page.getByRole("button", { name: "设置" }).click();
  await expect(page.locator("[data-sidebar-position=right]")).toBeVisible();
  await page.getByRole("button", { name: "导出脱敏诊断" }).click();
  await expect(page.getByRole("status")).toContainText("脱敏诊断已导出");
  await page.getByRole("button", { name: "清理本机数据" }).click();
  await expect(page.getByRole("status")).toContainText("没有更改数据");
});

test("failure, empty, offline and responsive states remain operable", async ({ page }) => {
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

  await page.setViewportSize({ width: 1024, height: 768 });
  await page.getByRole("button", { name: "账户与 Provider" }).click();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  expect(await page.evaluate(() => [...document.querySelectorAll(".provider-card")].every((card) => card.scrollWidth <= card.clientWidth))).toBe(true);

  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("button", { name: "设置" })).toBeVisible();
  await page.getByRole("button", { name: "设置" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Provider 行为" })).toBeVisible();
});

test("provider preset catalog is complete, searchable, filtered and responsive", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "账户与 Provider" }).click();

  const catalog = page.locator("[data-provider-id]");
  await expect(catalog).toHaveCount(78);

  const search = page.getByRole("textbox", { name: "搜索 Provider Preset" });
  await search.fill("Cursor");
  await expect(catalog).toHaveCount(1);
  await expect(page.getByRole("button", { name: "Cursor 不可添加" })).toBeDisabled();
  await search.fill("");

  const filter = page.getByRole("group", { name: "Provider 能力筛选" });
  await filter.getByRole("button", { name: "Window View" }).click();
  expect(await catalog.count()).toBeGreaterThan(0);
  expect(await catalog.locator(".preset-capabilities small:first-child").allTextContents())
    .not.toContain("Window · unsupported");

  await filter.getByRole("button", { name: "Wallet View" }).click();
  expect(await catalog.count()).toBeGreaterThan(0);
  expect(await catalog.locator(".preset-capabilities small:nth-child(2)").allTextContents())
    .not.toContain("Wallet · unsupported");

  for (const width of [1024, 390]) {
    await page.setViewportSize({ width, height: 844 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
    expect(await page.evaluate(() => [...document.querySelectorAll(".preset-card")]
      .every((card) => card.scrollWidth <= card.clientWidth))).toBe(true);
  }
});
