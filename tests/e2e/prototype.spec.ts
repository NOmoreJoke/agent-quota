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
  await expect(page.locator(".contract-note")).toHaveCount(0);
  await expect(page.locator("[data-transport=fixture]")).toBeVisible();

  await page.getByRole("button", { name: "账户与 Provider" }).click();
  await expect(page.locator("[data-sidebar-position=left]")).toBeVisible();
  await expect(page.getByRole("heading", { name: "已配置 Provider" })).toBeVisible();
  await expect(page.locator(".contract-note")).toHaveCount(1);
  await page.getByRole("button", { name: "安全与隐私说明 →" }).click();
  await expect(page.getByRole("heading", { name: "安全" })).toBeVisible();
  await page.getByRole("button", { name: "账户与 Provider" }).click();
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
  await expect(catalog).toHaveCount(15);
  await expect(catalog.locator("button:enabled")).toHaveCount(7);
  await expect(catalog.locator("button:disabled")).toHaveCount(8);

  expect(await catalog.evaluateAll((cards) => cards.map((card) => card.getAttribute("data-provider-id")))).toEqual([
    "deepseek-api-balance-cn", "kimi-api-balance-cn", "kimi-code-token-plan",
    "minimax-token-plan-cn", "glm-coding-plan-cn", "google-antigravity",
    "volcengine-ark-agent-plan-personal", "volcengine-billing-balance",
    "bailian-coding-plan", "bailian-token-plan-personal", "xiaomi-mimo-token-plan",
    "glm-api-balance-cn", "minimax-api-balance-cn",
    "workbuddy-personal-cn", "qoder-personal-cn",
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
  await expect(catalog).toHaveCount(8);
  await expect(page.locator('[data-provider-id="xiaomi-mimo-token-plan"]')).toHaveCount(0);

  await filter.getByRole("button", { name: "Wallet View" }).click();
  await expect(catalog).toHaveCount(10);
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

test("action buttons stay single-line, unclipped, and bottom-aligned across adaptive viewports", async ({ page }) => {
  for (const scenarioUrl of ["/?scenario=floating", "/", "/?scenario=antigravity"]) {
    await page.goto(scenarioUrl);
    await page.getByRole("button", { name: "账户与 Provider", exact: true }).click();
    await expect(page.getByRole("heading", { name: "已配置 Provider" })).toBeVisible();

    for (const width of [1280, 1120, 1024, 820, 390]) {
      await page.setViewportSize({ width, height: 844 });
      const metrics = await page.evaluate(() => {
        const pageFits = document.documentElement.scrollWidth <= document.documentElement.clientWidth;
        const selectors = [
          ".topbar button",
          ".sidebar-foot button",
          ".contract-note button",
          ".segmented button",
          ".provider-actions button",
          ".preset-card button",
        ];
        const buttons = selectors
          .flatMap((selector) => [...document.querySelectorAll<HTMLButtonElement>(selector)])
          .filter((button) => button.offsetParent !== null);

        const clippedOrWrapped = buttons
          .filter((button) => {
            const box = button.getBoundingClientRect();
            return button.scrollWidth > button.clientWidth + 1 || box.height > 42;
          })
          .map((button) => ({
            text: button.textContent?.trim(),
            height: Math.round(button.getBoundingClientRect().height),
            scrollWidth: button.scrollWidth,
            clientWidth: button.clientWidth,
          }));

        const overflowingCards = [...document.querySelectorAll<HTMLElement>(".provider-card, .preset-card")]
          .filter((card) => card.scrollWidth > card.clientWidth + 1)
          .map((card) => card.className);

        const cardsByRow = new Map<number, number[]>();
        for (const card of document.querySelectorAll<HTMLElement>(".provider-card")) {
          const cardTop = Math.round(card.getBoundingClientRect().top);
          const actions = card.querySelector<HTMLElement>(".provider-actions");
          if (!actions) continue;
          const rowKey = [...cardsByRow.keys()].find((key) => Math.abs(key - cardTop) <= 2) ?? cardTop;
          const list = cardsByRow.get(rowKey) ?? [];
          list.push(Math.round(actions.getBoundingClientRect().bottom));
          cardsByRow.set(rowKey, list);
        }
        const misalignedRows = [...cardsByRow.values()].filter(
          (bottoms) => Math.max(...bottoms) - Math.min(...bottoms) > 2,
        );

        return { pageFits, clippedOrWrapped, overflowingCards, misalignedRows };
      });

      expect(metrics).toEqual({
        pageFits: true,
        clippedOrWrapped: [],
        overflowingCards: [],
        misalignedRows: [],
      });
      if (scenarioUrl === "/?scenario=floating" && (width === 1280 || width === 1120)) {
        await page.screenshot({ path: `output/playwright/accounts-adaptive-${width}.png` });
      }
    }
  }
});

test("expired credential prompts reauthorization in main and floating surfaces", async ({ page }) => {
  await page.goto("/?scenario=reauth");
  const prompt = page.getByTestId("reauth-prompt");
  await expect(prompt).toBeVisible();
  await expect(prompt).toContainText("凭据已过期，请重新授权");
  await expect(prompt).toContainText("Kimi Code Token Plan");

  await prompt.getByRole("button", { name: "稍后处理" }).first().click();
  await expect(prompt).toHaveCount(0);
  await expect(page.getByTestId("reauth-banner")).toContainText("Kimi Code Token Plan 凭据已过期");

  await page.getByRole("button", { name: "全部刷新" }).click();
  await expect(prompt).toBeVisible();
  await prompt.getByRole("button", { name: "重新授权" }).click();
  await expect(prompt).toHaveCount(0);
  await expect(page.getByTestId("reauth-banner")).toHaveCount(0);

  await page.goto("/?surface=floating&scenario=reauth");
  await expect(page.locator(".floating-summary")).toHaveText("1 项需授权");
  await page.getByRole("button", { name: "展开用量悬浮窗" }).click();
  const floatingAlert = page.getByTestId("floating-reauth-alert");
  await expect(floatingAlert).toBeVisible();
  await expect(floatingAlert).toContainText("Kimi Code Token Plan");
  await floatingAlert.getByRole("button", { name: "重新授权" }).click();
  await expect(floatingAlert).toHaveCount(0);
});

test("settings motion switch toggles animated loading, persists across reload, and syncs to floating window", async ({ page, context }) => {
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page.setViewportSize({ width: 1280, height: 844 });
  await page.goto("/?scenario=floating");
  await expect(page.locator("html")).toHaveAttribute("data-motion", "on");

  const floating = await context.newPage();
  await floating.emulateMedia({ reducedMotion: "no-preference" });
  await floating.setViewportSize({ width: 384, height: 536 });
  await floating.goto("/?surface=floating&scenario=floating");
  await expect(floating.locator("html")).toHaveAttribute("data-motion", "on");

  await page.getByRole("button", { name: "设置", exact: true }).click();
  const motionButton = page.getByRole("button", { name: "开启动效加载" });
  await expect(motionButton).toBeVisible();
  await expect(motionButton).toHaveAttribute("aria-pressed", "true");
  await expect(motionButton).toContainText("动效加载：已开启");

  const activePulse = await motionButton.locator(".motion-bars i").first()
    .evaluate((el) => getComputedStyle(el).animationName);
  expect(activePulse).toBe("bars-fade");
  await page.screenshot({ path: "output/playwright/settings-motion-on.png" });

  await motionButton.click();
  await expect(motionButton).toHaveAttribute("aria-pressed", "false");
  await expect(motionButton).toContainText("开启动效加载");
  await expect(page.locator("html")).toHaveAttribute("data-motion", "off");
  await expect(floating.locator("html")).toHaveAttribute("data-motion", "off");

  const disabledPulse = await motionButton.locator(".motion-bars i").first()
    .evaluate((el) => ({ animationName: getComputedStyle(el).animationName, transitionDuration: getComputedStyle(el).transitionDuration }));
  expect(disabledPulse).toEqual({ animationName: "none", transitionDuration: "0s" });

  await page.reload();
  await page.getByRole("button", { name: "设置", exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute("data-motion", "off");
  await expect(motionButton).toHaveAttribute("aria-pressed", "false");

  await motionButton.click();
  await expect(page.locator("html")).toHaveAttribute("data-motion", "on");
  await expect(floating.locator("html")).toHaveAttribute("data-motion", "on");
});
