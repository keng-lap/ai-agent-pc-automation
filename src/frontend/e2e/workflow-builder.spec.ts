import { expect, test } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  await page.route('**/api/auth/session', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ enabled: false, authenticated: false, authenticator_enrolled: false }),
  }));
  await page.route('**/api/settings/gemini', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ configured: false, model: 'test-model' }),
  }));
});

test('workflow builder supports node creation, connection, editing, keyboard movement and zoom', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: /ออกแบบ Workflow/ }).click();

  await expect(page.getByRole('heading', { name: 'ออกแบบ Workflow' })).toBeVisible();
  await expect(page.getByText('PROTOTYPE · NO EXECUTION')).toBeVisible();
  await expect(page.locator('.canvas-heading')).toContainText('7 Nodes · 6 Connections');

  await page.locator('.node-library .library-item').filter({ hasText: 'เริ่ม Workflow' }).click();
  await page.locator('.node-library .library-item').filter({ hasText: 'วิเคราะห์ด้วย AI' }).click();
  await expect(page.locator('.canvas-heading')).toContainText('9 Nodes · 6 Connections');

  await page.getByRole('button', { name: 'เชื่อมออกจาก เริ่ม Workflow · ถัดไป' }).click();
  await page.getByRole('button', { name: 'เชื่อมเข้าที่ วิเคราะห์ด้วย AI' }).click();
  await expect(page.locator('.canvas-heading')).toContainText('9 Nodes · 7 Connections');

  const node = page.getByRole('group', { name: 'วิเคราะห์ด้วย AI' });
  await node.click();
  await page.locator('#node-label').fill('ตรวจสอบซ้ำ');
  const editedNode = page.getByRole('group', { name: 'ตรวจสอบซ้ำ' });
  await expect(editedNode).toBeVisible();

  const before = await editedNode.boundingBox();
  expect(before).not.toBeNull();
  await editedNode.focus();
  await expect(editedNode).toBeFocused();
  await editedNode.press('ArrowRight');
  const after = await editedNode.boundingBox();
  expect(after).not.toBeNull();
  expect(after!.x).toBeGreaterThan(before!.x);

  await page.getByRole('button', { name: 'ขยาย Canvas' }).click();
  await expect(page.locator('.canvas-tools').getByText('110%', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'รีเซ็ตมุมมอง' }).click();
  await expect(page.locator('.canvas-tools').getByText('100%', { exact: true })).toBeVisible();
});

test('workflow builder keeps the page within a narrow mobile viewport', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 568 });
  await page.goto('/');
  await page.getByRole('button', { name: /ออกแบบ Workflow/ }).click();

  await expect(page.getByRole('heading', { name: 'ออกแบบ Workflow' })).toBeVisible();
  const dimensions = await page.evaluate(() => ({
    documentWidth: document.documentElement.scrollWidth,
    viewportWidth: document.documentElement.clientWidth,
    canvasWidth: document.querySelector('.canvas-viewport')?.scrollWidth ?? 0,
    canvasClientWidth: document.querySelector('.canvas-viewport')?.clientWidth ?? 0,
  }));
  expect(dimensions.documentWidth).toBeLessThanOrEqual(dimensions.viewportWidth);
  expect(dimensions.canvasWidth).toBeGreaterThan(dimensions.canvasClientWidth);
});


test('supports dragging an output port directly onto a target input port', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: /ออกแบบ Workflow/ }).click();
  await page.locator('.node-library .library-item').filter({ hasText: 'เริ่ม Workflow' }).click();
  await page.locator('.node-library .library-item').filter({ hasText: 'วิเคราะห์ด้วย AI' }).click();

  const source = await page.getByRole('button', { name: 'เชื่อมออกจาก เริ่ม Workflow · ถัดไป' }).boundingBox();
  const target = await page.getByRole('button', { name: 'เชื่อมเข้าที่ วิเคราะห์ด้วย AI' }).boundingBox();
  expect(source).not.toBeNull();
  expect(target).not.toBeNull();

  await page.mouse.move(source!.x + source!.width / 2, source!.y + source!.height / 2);
  await page.mouse.down();
  await page.mouse.move(target!.x + target!.width / 2, target!.y + target!.height / 2, { steps: 8 });
  await page.mouse.up();

  await expect(page.locator('.canvas-heading')).toContainText('9 Nodes · 7 Connections');
  await expect(page.getByRole('status')).toContainText('เชื่อม Node สำเร็จ');
});
