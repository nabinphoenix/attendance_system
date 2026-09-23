import { test, expect, Page } from '@playwright/test';
import { mockWorkspace, moduleTitle } from './fixtures';

const widths = [[320,568],[360,800],[375,812],[390,844],[412,915],[430,932],[768,1024],[1440,1000]];
const routes = [
  ['student','/student/dashboard'], ['student','/settings'], ['student','/student/routine'], ['student','/student/check-in'],
  ['teacher','/teacher/sessions'], ['teacher','/teacher/sessions/1'], ['teacher','/teacher/attendance'],
  ['admin','/admin/dashboard'], ['admin','/admin/users'], ['admin','/admin/academic/batches'], ['admin','/admin/academic/sections'],
  ['admin','/admin/academic/intakes'], ['admin','/admin/academic/promotions'], ['admin','/admin/academic/semester-resources'],
  ['coordinator','/coordinator/cases'], ['super_admin','/super-admin/dashboard'], ['super_admin','/super-admin/users'],
  ['student','/login'], ['student','/forgot-password'], ['student','/reset-password#token=test-token-at-least-32-characters'],
];
async function noOverflow(page: Page) {
  const result = await page.evaluate(() => ({ width: window.innerWidth, scroll: document.documentElement.scrollWidth, offenders: [...document.querySelectorAll('main *')].filter(el => {const r=el.getBoundingClientRect();return r.width>0 && (r.left < -1 || r.right > window.innerWidth+1) && !el.closest('.overflow-x-auto,.table-wrap');}).slice(0,8).map(el=>`${el.tagName}.${el.className}`) }));
  expect(result.width).toBe(page.viewportSize()!.width);
  expect(result, JSON.stringify(result)).toMatchObject({ scroll: result.width });
  expect(result.offenders).toEqual([]);
}
for(const [width,height] of widths) for(const theme of ['light','dark']) {
  test(`${width}px ${theme}: major role pages fit the viewport`, async({page}, testInfo)=>{
    await page.setViewportSize({width,height}); await page.addInitScript(value=>localStorage.setItem('antimbench-theme',value),theme);
    const state=await mockWorkspace(page); const errors:string[]=[];page.on('pageerror',error=>errors.push(error.message));
    for(const [role,path] of routes) {
      state.role=role;
      await test.step(path,async()=>{
        await page.goto(path); await expect(page.locator('h1').first()).toBeVisible();
        await expect(page.getByText(/Loading student dashboard|Loading canonical routine/)).toHaveCount(0);
        await expect(page.locator('html')).toHaveAttribute('data-theme',theme);
        // Allow the mocked data's React render to settle before measuring.
        await page.waitForLoadState('networkidle');
        expect(errors, path).toEqual([]);
        await noOverflow(page);
        if((width===390||width===1440)&&['/student/dashboard','/settings','/teacher/sessions/1'].includes(path)) {
          await page.screenshot({path:testInfo.outputPath(`${path.replaceAll('/','-')}-${theme}.png`),fullPage:true});
        }
      });
    }
  });
}

test('mobile navigation traps focus, closes on route change and restores focus with Escape',async({page})=>{
  await page.setViewportSize({width:320,height:568});await mockWorkspace(page);await page.addInitScript(()=>localStorage.setItem('sidebar_collapsed','true'));
  await page.goto('/student/dashboard');const trigger=page.getByRole('button',{name:'Open navigation'});await trigger.click();
  const drawer=page.getByRole('dialog',{name:'Mobile navigation'});await expect(drawer).toBeVisible();await expect(drawer.getByRole('link',{name:'My routine'})).toBeVisible();
  for(let i=0;i<14;i++) {await page.keyboard.press('Tab');expect(await drawer.evaluate(el=>el.contains(document.activeElement))).toBeTruthy();}
  await page.keyboard.press('Escape');await expect(drawer).not.toBeVisible();await expect(trigger).toBeFocused();
  await trigger.click();await drawer.getByRole('link',{name:'Settings',exact:true}).click();await expect(page).toHaveURL(/\/settings$/);await expect(drawer).not.toBeVisible();await noOverflow(page);
  // A Super Admin entering a college retains a route back on the smallest screen.
  await page.route('**/api/v1/auth/me', route=>route.fulfill({json:{id:1,name:'Platform administrator',email:'platform@example.com',role:'super_admin',active_college_id:1}}));
  await page.goto('/admin/users');await page.getByRole('button',{name:'Open navigation'}).click();
  await expect(page.getByRole('dialog',{name:'Mobile navigation'}).getByRole('link',{name:'Back to platform'})).toHaveAttribute('href','/super-admin/colleges');
  await noOverflow(page);
});

test('student filters change results and can be cleared on a phone',async({page})=>{
  await page.setViewportSize({width:320,height:568});await mockWorkspace(page);await page.goto('/student/dashboard');
  const search=page.getByPlaceholder('Course, lecturer, or room');await search.fill('no-such-class');await expect(page.getByRole('heading',{name:moduleTitle,exact:true})).toHaveCount(0);
  await page.locator('section').filter({has:search}).getByRole('button',{name:'Clear filters',exact:true}).click();await expect(search).toHaveValue('');await expect(page.getByRole('heading',{name:moduleTitle,exact:true}).first()).toBeVisible();await noOverflow(page);
});

test('locked sign-in leads to generic recovery; reset requires matching passwords',async({page})=>{
  await page.setViewportSize({width:360,height:800});await mockWorkspace(page);
  await page.route('**/api/v1/auth/login',route=>route.fulfill({status:423,json:{detail:'Your account is locked after multiple unsuccessful login attempts.'}}));
  await page.goto('/login');await page.getByLabel('Email address').fill('student@example.com');await page.getByLabel('Password',{exact:true}).fill('wrong-password');await page.getByRole('button',{name:'Sign in',exact:true}).click();
  await expect(page.locator('main').getByRole('alert')).toContainText('Your account is locked');await page.getByRole('link',{name:'Reset password',exact:true}).click();await expect(page.getByRole('heading',{name:'Forgot your password?'})).toBeVisible();await page.getByLabel('Email address').fill('unknown@example.com');await page.getByRole('button',{name:'Send reset link'}).click();await expect(page.getByRole('status')).toContainText('If an account exists');
  await page.goto('/reset-password#token=test-token-at-least-32-characters');await expect(page.getByLabel('New password',{exact:true})).toBeVisible();expect(new URL(page.url()).hash).toBe('');
  await page.getByLabel('New password',{exact:true}).fill('FreshPassword123!');await page.getByLabel('Confirm new password').fill('Mismatch123!');await page.getByRole('button',{name:'Reset password',exact:true}).click();await expect(page.locator('main').getByRole('alert')).toContainText('do not match');
  await page.getByLabel('Confirm new password').fill('FreshPassword123!');await page.getByRole('button',{name:'Reset password',exact:true}).click();await expect(page.getByRole('status')).toContainText('account unlocked');await noOverflow(page);
});

test('admin confirms unlock on a phone and can horizontally scroll its table',async({page})=>{
  await page.setViewportSize({width:320,height:568});const state=await mockWorkspace(page);state.role='admin';await page.goto('/admin/users');
  await page.getByRole('button',{name:'Unlock account',exact:true}).click();const dialog=page.getByRole('dialog',{name:'Unlock account?'});await expect(dialog).toBeVisible();await expect(dialog).toContainText('password will stay the same');await noOverflow(page);
  await dialog.getByRole('button',{name:'Unlock account',exact:true}).click();await expect(dialog).not.toBeVisible();await expect(page.getByRole('button',{name:'Unlock account',exact:true})).toHaveCount(0);
});

test('QR/code check-in controls and live roster list remain usable on mobile',async({page})=>{
  await page.setViewportSize({width:320,height:568});const state=await mockWorkspace(page);await page.goto('/student/check-in');await page.getByRole('button',{name:'Continue',exact:true}).click();
  await page.getByRole('button',{name:'Enter Attendance Code'}).click();await page.getByLabel('Six-digit attendance code').fill('123456');await expect(page.getByRole('button',{name:'Mark Attendance'})).toBeEnabled();await expect(page.locator('input[type=file]')).toHaveCount(0);await noOverflow(page);
  state.role='teacher';await page.goto('/teacher/sessions/1');await expect(page.getByText('Network verified').first()).toBeVisible();await noOverflow(page);
  const list=page.getByRole('button',{name:/list/i});if(await list.count()) {await list.first().click();await noOverflow(page);}
});


test('promotion shuffle preview and held-student decisions fit a narrow viewport',async({page})=>{
  await page.setViewportSize({width:320,height:568});const state=await mockWorkspace(page);state.role='admin';await page.goto('/admin/academic/promotions');
  await page.getByLabel('Source semester',{exact:true}).selectOption('1');await page.getByLabel('Target semester',{exact:true}).selectOption('2');
  await page.getByLabel('Placement strategy').selectOption('random_balanced');
  await page.getByRole('button',{name:'Preview progression',exact:true}).click();await expect(page.getByRole('button',{name:'Apply progression',exact:true})).toBeVisible();await noOverflow(page);
  await page.getByRole('button',{name:'View decisions',exact:true}).click();await expect(page.getByRole('button',{name:'Release',exact:true})).toBeVisible();await noOverflow(page);
});
