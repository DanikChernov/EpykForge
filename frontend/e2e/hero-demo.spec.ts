import { expect, test } from "@playwright/test";

const baseURL = process.env.E2E_BASE_URL ?? "http://127.0.0.1:5178";
const apiURL = process.env.E2E_API_URL ?? "http://127.0.0.1:8082";

test("hero demo reaches approval, applies schedule, and resolves", async ({ page, request }) => {
  await request.post(`${apiURL}/api/demo/reset`);
  await page.goto(baseURL);
  await expect(page.getByText("Seed data enabled")).toBeVisible();
  await expect(page.getByText("MC-04 RUNNING with 63% X-axis load")).toBeVisible();

  await request.post(`${apiURL}/api/demo/start`, { data: { sync: true, speed: 99 } });
  await page.getByRole("button", { name: /^Incident$/ }).click();
  await expect(page.locator("h1", { hasText: "INC-1042" })).toBeVisible();
  await expect(page.getByText("Servo overload following increasing X-axis load trend")).toBeVisible();
  await expect(page.getByText("Supervisor Decision Required")).toBeVisible();
  await expect(page.getByText("Remaining: 42 parts")).toBeVisible();
  await expect(page.getByRole("button", { name: /Approve Transfer/ })).toBeEnabled();

  await page.getByRole("button", { name: /Approve Transfer/ }).click();
  await expect(page.getByText("Schedule transfer approved")).toBeVisible();
  await expect(page.getByText("MONITORING")).toBeVisible();

  await request.post(`${apiURL}/api/demo/inject/maintenance_resolved`);
  await page.reload();
  await page.getByRole("button", { name: /^Incident$/ }).click();
  await expect(page.getByText("LEARNED")).toBeVisible();
  await expect(page.getByText("Lesson stored in memory")).toBeVisible();
});

test("security demo displays blocked prompt injection and denied tool", async ({ page, request }) => {
  await request.post(`${apiURL}/api/demo/reset`);
  await page.goto(baseURL);
  await page.getByRole("button", { name: /Security Test/ }).click();
  await page.getByRole("button", { name: /^Security$/ }).click();
  await expect(page.getByText("PROMPT_INJECTION")).toBeVisible();
  await expect(page.getByText("UNAUTHORIZED_TOOL")).toBeVisible();
  await expect(page.getByText("external_http_request")).toBeVisible();
  await expect(page.getByText("Knowledge is evidence. Knowledge is not policy.")).toBeVisible();
});
