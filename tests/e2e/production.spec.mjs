import { test, expect } from '@playwright/test';

const businessId = process.env.E2E_DEMO_BUSINESS_ID;
const widgetKey = process.env.E2E_DEMO_WIDGET_API_KEY;
const leadPageUrl = process.env.E2E_LEAD_PAGE_URL;
const ownerToken = process.env.E2E_OWNER_TOKEN;

test.describe('Talk2Pay production browser matrix', () => {
  test('home page serves the canonical public brand and current pricing', async ({ page }) => {
    await page.goto('/?e2e=brand');
    await expect(page).toHaveTitle(/Talk2Pay/);
    await expect(page.locator('body')).toContainText('Talk2Pay');
    await expect(page.locator('body')).not.toContainText('ConversaPay');
    await expect(page.locator('body')).toContainText('₪200');
    await expect(page.locator('body')).toContainText('₪350');
  });

  test('widget loads, opens, sends a message, and receives a reply', async ({ page }) => {
    test.skip(!businessId || !widgetKey, 'Set E2E_DEMO_BUSINESS_ID and E2E_DEMO_WIDGET_API_KEY for the live widget flow');
    await page.goto(`/widget-demo?business_id=${encodeURIComponent(businessId)}&api_key=${encodeURIComponent(widgetKey)}&e2e=widget`);
    const toggle = page.locator('#conversapay-chat-widget .cp-toggle');
    await expect(toggle).toBeVisible();
    await toggle.click();
    const input = page.locator('#conversapay-chat-widget #cpInput');
    await expect(input).toBeVisible();
    await input.fill('אני מחפש מוצר לבדיקה');
    const responsePromise = page.waitForResponse((response) => response.url().includes('/api/v1/chat') && response.request().method() === 'POST');
    await page.locator('#conversapay-chat-widget #cpSend').click();
    const response = await responsePromise;
    expect(response.ok()).toBeTruthy();
    await expect(page.locator('#conversapay-chat-widget .cp-message.bot')).toHaveCount(2, { timeout: 30_000 });
  });

  test('lead form accepts company, confirms success, and persists exactly once', async ({ page, request }) => {
    test.skip(!leadPageUrl || !ownerToken, 'Set E2E_LEAD_PAGE_URL and E2E_OWNER_TOKEN for the live lead persistence flow');
    const email = `e2e-${Date.now()}@example.invalid`;
    await page.goto(`${leadPageUrl}${leadPageUrl.includes('?') ? '&' : '?'}e2e=lead`);
    const form = page.locator('#contactForm');
    await expect(form).toBeVisible();
    await form.locator('[name="name"]').fill('Talk2Pay E2E');
    await form.locator('[name="email"]').fill(email);
    await form.locator('[name="company"]').fill('E2E Company');
    await form.locator('[name="message"]').fill('Production lead persistence check');
    await form.locator('button[type="submit"]').click();
    await expect(page.locator('#formStatus')).toContainText('תודה', { timeout: 30_000 });

    const leadsUrl = new URL('/api/v1/site-builder/leads', process.env.E2E_BASE_URL || 'https://conversapay-proj.onrender.com');
    let matches = [];
    await expect.poll(async () => {
      const response = await request.get(leadsUrl.toString(), { headers: { Authorization: `Bearer ${ownerToken}` } });
      expect(response.ok()).toBeTruthy();
      const payload = await response.json();
      matches = (payload.items || []).filter((item) => item.email === email);
      return matches.length;
    }, { timeout: 30_000, intervals: [1000, 2000, 5000] }).toBe(1);
    expect(matches[0].company).toBe('E2E Company');
  });
});
