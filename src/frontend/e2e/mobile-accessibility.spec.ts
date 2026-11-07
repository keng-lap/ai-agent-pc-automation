import { expect, test } from '@playwright/test';

const mobileViewports = [
  { name: 'small-320x568', width: 320, height: 568 },
  { name: 'iphone-se-375x667', width: 375, height: 667 },
  { name: 'iphone-390x844', width: 390, height: 844 },
  { name: 'large-mobile-430x932', width: 430, height: 932 },
] as const;

for (const viewport of mobileViewports) {
  test(`mobile layout is usable without horizontal overflow at ${viewport.width}x${viewport.height}`, async ({ page }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await page.goto('/');

    await expect(page.getByRole('heading', { name: /คุยกับ Agent|Chat with your Agent/ })).toBeVisible();
    await expect(page.getByRole('textbox', { name: 'ข้อความของคุณ' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'ส่งข้อความ' })).toBeVisible();

    const dimensions = await page.evaluate(() => ({
      documentWidth: document.documentElement.scrollWidth,
      viewportWidth: document.documentElement.clientWidth,
      bodyWidth: document.body.scrollWidth,
    }));

    expect(dimensions.documentWidth, 'document must not overflow horizontally').toBeLessThanOrEqual(dimensions.viewportWidth);
    expect(dimensions.bodyWidth, 'body must not overflow horizontally').toBeLessThanOrEqual(dimensions.viewportWidth);
  });
}

test('mobile controls expose accessible names and keyboard focus', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');

  await expect(page.getByRole('group', { name: 'เลือกภาษา' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'ไทย', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByRole('button', { name: 'EN', exact: true })).toHaveAttribute('aria-pressed', 'false');
  await expect(page.getByRole('log', { name: 'ข้อความสนทนา' })).toBeVisible();

  const messageBox = page.getByRole('textbox', { name: 'ข้อความของคุณ' });
  await messageBox.fill('ทดสอบการเข้าถึงด้วยแป้นพิมพ์');
  await messageBox.focus();
  await expect(messageBox).toBeFocused();

  const sendButton = page.getByRole('button', { name: 'ส่งข้อความ' });
  await expect(sendButton).toBeEnabled();
  await sendButton.focus();
  await expect(sendButton).toBeFocused();
});
