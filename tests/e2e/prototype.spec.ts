import { expect, test } from "@playwright/test";

test("prototype covers primary navigation and host-owned actions", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "额度总览", level: 1 })).toBeVisible();
  await expect(page.getByText("当前额度")).toBeVisible();
  await expect(page.locator("[data-transport=fixture]")).toBeVisible();

  await page.getByRole("button", { name: "账户管理" }).click();
  await expect(page.getByRole("heading", { name: "账户与认证" })).toBeVisible();
  await page.getByRole("button", { name: "添加账户" }).click();
  await expect(page.getByRole("status")).toContainText("临时测试账户已添加");
  await expect(page.getByText("Fixture · 临时测试账户")).toBeVisible();

  await page.getByRole("button", { name: "设置" }).click();
  await page.getByRole("button", { name: "导出脱敏诊断" }).click();
  await expect(page.getByRole("status")).toContainText("脱敏诊断已导出");
  await page.getByRole("button", { name: "打开原生清理确认" }).click();
  await expect(page.getByRole("status")).toContainText("没有更改数据");
});

test("failure, empty, offline and responsive states remain operable", async ({ page }) => {
  await page.goto("/?scenario=outcome-unknown");
  await page.getByRole("button", { name: "刷新全部" }).click();
  await expect(page.getByRole("status")).toContainText("刷新结果未知");

  await page.goto("/?scenario=empty");
  await expect(page.getByTestId("empty-state")).toBeVisible();
  await page.getByRole("button", { name: "添加第一个账户" }).click();
  await expect(page.getByTestId("empty-state")).not.toBeVisible();
  await expect(page.getByRole("region", { name: "额度摘要" }).getByText("1", { exact: true }))
    .toBeVisible();
  await page.getByRole("button", { name: "账户管理" }).click();
  await expect(page.getByText("Fixture · 临时测试账户")).toBeVisible();

  await page.goto("/?scenario=offline");
  await expect(page.getByRole("status")).toContainText("当前离线");

  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("button", { name: "设置" })).toBeVisible();
  await page.getByRole("button", { name: "设置" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "清理本机数据" })).toBeVisible();
});
