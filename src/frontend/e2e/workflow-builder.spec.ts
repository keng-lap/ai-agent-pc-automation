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

  const beforeX = await editedNode.evaluate((element) => Number.parseFloat(getComputedStyle(element).left));
  expect(Number.isFinite(beforeX)).toBe(true);
  await editedNode.focus();
  await expect(editedNode).toBeFocused();
  await editedNode.press('ArrowRight');
  await expect.poll(() => editedNode.evaluate((element) => Number.parseFloat(getComputedStyle(element).left)))
    .toBeGreaterThan(beforeX);

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

  const sourcePort = page.getByRole('button', { name: 'เชื่อมออกจาก เริ่ม Workflow · ถัดไป' });
  const targetPort = page.getByRole('button', { name: 'เชื่อมเข้าที่ วิเคราะห์ด้วย AI' });
  await targetPort.scrollIntoViewIfNeeded();
  const source = await sourcePort.boundingBox();
  const target = await targetPort.boundingBox();
  expect(source).not.toBeNull();
  expect(target).not.toBeNull();

  await page.mouse.move(source!.x + source!.width / 2, source!.y + source!.height / 2);
  await page.mouse.down();
  await page.mouse.move(target!.x + target!.width / 2, target!.y + target!.height / 2, { steps: 8 });
  await page.mouse.up();

  await expect(page.locator('.canvas-heading')).toContainText('9 Nodes · 7 Connections');
  await expect(page.locator('.builder-message')).toContainText('เชื่อม Node สำเร็จ');
});

test('workflow builder remains available before sign-in while chat stays protected', async ({ page }) => {
  await page.route('**/api/auth/session', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ enabled: true, authenticated: false, authenticator_enrolled: false }),
  }));

  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'เข้าสู่ระบบก่อนใช้งาน' })).toBeVisible();

  await page.getByRole('button', { name: /ออกแบบ Workflow/ }).click();
  await expect(page.getByRole('heading', { name: 'ออกแบบ Workflow' })).toBeVisible();
  await expect(page.getByText('PROTOTYPE · NO EXECUTION')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'เข้าสู่ระบบก่อนใช้งาน' })).toHaveCount(0);

  await page.getByRole('link', { name: /สนทนากับ Agent/ }).click();
  await expect(page.getByRole('heading', { name: 'เข้าสู่ระบบก่อนใช้งาน' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'ออกแบบ Workflow' })).toHaveCount(0);
});

test('workflow builder exposes script and software installation node types as non-executing design items', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: /ออกแบบ Workflow/ }).click();

  await expect(page.getByRole('button', { name: /รัน Custom Script/ })).toBeVisible();
  await expect(page.getByRole('button', { name: /ติดตั้งโปรแกรม/ })).toBeVisible();
  await expect(page.getByRole('button', { name: /ติดตั้งหลายโปรแกรม/ })).toBeVisible();

  await page.getByRole('button', { name: /รัน Custom Script/ }).click();
  await expect(page.locator('.canvas-heading')).toContainText('8 Nodes · 6 Connections');
  await expect(page.getByText('PROTOTYPE · NO EXECUTION')).toBeVisible();
});

test('job monitor shows active jobs and previous run details without real execution', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: /ติดตามงาน/ }).click();

  await expect(page.getByRole('heading', { name: 'ติดตามการทำงาน' })).toBeVisible();
  await expect(page.getByText('PROTOTYPE · MOCK DATA')).toBeVisible();
  await expect(page.getByText('RUN-2026-0118 · Workstation setup · v3', { exact: true })).toBeVisible();
  await expect(page.getByText('ติดตั้ง Visual Studio Code').first()).toBeVisible();

  await page.getByRole('button', { name: /ประวัติการทำงาน/ }).click();
  await expect(page.getByText('RUN-2026-0115')).toBeVisible();
  await page.getByRole('button', { name: /รันสคริปต์สำรองข้อมูล/ }).click();
  await expect(page.getByText('Simulated failure · exit code 1 · no script executed')).toBeVisible();
  await expect(page.getByText(/ไม่มีการเชื่อมต่อ Job Engine/)).toBeVisible();
});


test('workflow builder supports full-screen mode and independently toggles side panels', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: /ออกแบบ Workflow/ }).click();

  const fullScreenButton = page.getByRole('button', { name: 'เต็มหน้าจอ' });
  await fullScreenButton.click();
  await expect(page.locator('html')).toHaveClass(/workflow-fullscreen/);
  await expect(page.locator('.side-rail')).toBeHidden();
  await expect(page.getByRole('button', { name: 'ออกจากเต็มหน้าจอ' })).toBeVisible();

  await page.getByRole('button', { name: /เมนูหลัก/ }).click();
  await expect(page.locator('.side-rail')).toBeVisible();
  await page.getByRole('button', { name: /เมนูหลัก/ }).click();
  await expect(page.locator('.side-rail')).toBeHidden();

  await page.getByRole('button', { name: /คลัง Node/ }).click();
  await expect(page.locator('.node-library')).toBeHidden();
  await expect(page.locator('.canvas-panel')).toBeVisible();

  await page.getByRole('button', { name: /คลัง Node/ }).click();
  await expect(page.locator('.node-library')).toBeVisible();
  await page.getByRole('button', { name: /รายละเอียด/ }).click();
  await expect(page.locator('.properties-panel')).toBeHidden();
  await page.getByRole('button', { name: /รายละเอียด/ }).click();
  await expect(page.locator('.properties-panel')).toBeVisible();

  await page.getByRole('button', { name: 'ออกจากเต็มหน้าจอ' }).click();
  await expect(page.locator('html')).not.toHaveClass(/workflow-fullscreen/);
  await expect(page.locator('.side-rail')).toBeVisible();
});


test('canvas pans by dragging blank space and with Space plus left-drag without moving nodes', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: /ออกแบบ Workflow/ }).click();
  const viewport = page.locator('.canvas-viewport');
  const node = page.locator('.workflow-node').first();
  const beforeNode = await node.evaluate((element) => ({
    left: Number.parseFloat(getComputedStyle(element).left),
    top: Number.parseFloat(getComputedStyle(element).top),
  }));

  const box = await viewport.boundingBox();
  expect(box).not.toBeNull();
  const startX = box!.x + box!.width - 55;
  const startY = box!.y + box!.height - 55;
  await page.mouse.move(startX, startY);
  await page.mouse.down();
  await page.mouse.move(startX - 90, startY - 65, { steps: 6 });
  await page.mouse.up();

  await expect.poll(() => viewport.evaluate((element) => element.scrollLeft)).toBeGreaterThan(0);
  await expect.poll(() => viewport.evaluate((element) => element.scrollTop)).toBeGreaterThan(0);

  const afterBlankPan = await node.evaluate((element) => ({
    left: Number.parseFloat(getComputedStyle(element).left),
    top: Number.parseFloat(getComputedStyle(element).top),
  }));
  expect(afterBlankPan).toEqual(beforeNode);

  await viewport.focus();
  await page.keyboard.down('Space');
  const currentBox = await viewport.boundingBox();
  expect(currentBox).not.toBeNull();
  const secondX = currentBox!.x + currentBox!.width - 55;
  const secondY = currentBox!.y + currentBox!.height - 55;
  const previousScrollLeft = await viewport.evaluate((element) => element.scrollLeft);
  await page.mouse.move(secondX, secondY);
  await page.mouse.down();
  await page.mouse.move(secondX - 45, secondY, { steps: 4 });
  await page.mouse.up();
  await page.keyboard.up('Space');
  await expect.poll(() => viewport.evaluate((element) => element.scrollLeft)).toBeGreaterThan(previousScrollLeft);
});
