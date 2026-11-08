import { expect, test } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  await page.route('**/api/auth/session', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      enabled: false,
      authenticated: false,
      authenticator_enrolled: false,
    }),
  }));
  await page.route('**/api/settings/gemini', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ configured: false, model: 'test-model' }),
  }));
});


const desktopViewports = [
  { name: 'desktop-1920x1080', width: 1920, height: 1080 },
  { name: 'desktop-1366x768', width: 1366, height: 768 },
  { name: 'desktop-1280x720', width: 1280, height: 720 },
] as const;

for (const viewport of desktopViewports) {
  test(`loads the local app without horizontal overflow at ${viewport.width}x${viewport.height}`, async ({ page }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await page.goto('/');

    await expect(page.locator('h1')).toContainText('AI Agent PC Automation');
    await expect(page.getByRole('heading', { name: /คุยกับ Agent|Chat with your Agent/ })).toBeVisible();

    const dimensions = await page.evaluate(() => ({
      documentWidth: document.documentElement.scrollWidth,
      viewportWidth: document.documentElement.clientWidth,
      bodyWidth: document.body.scrollWidth,
    }));

    expect(dimensions.documentWidth, 'document must not overflow horizontally').toBeLessThanOrEqual(dimensions.viewportWidth);
    expect(dimensions.bodyWidth, 'body must not overflow horizontally').toBeLessThanOrEqual(dimensions.viewportWidth);

    await page.screenshot({
      path: `test-results/${viewport.name}.png`,
      fullPage: true,
    });
  });
}

test('language switch is usable without invoking computer actions', async ({ page }) => {
  await page.goto('/');

  const englishButton = page.getByRole('button', { name: 'EN', exact: true });
  await englishButton.click();

  await expect(page.getByRole('heading', { name: 'Chat with your Agent' })).toBeVisible();
  await expect(englishButton).toHaveAttribute('aria-pressed', 'true');
});
