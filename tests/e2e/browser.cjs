// Usar con tests/serve_portal.py; cuenta sintética exclusiva de ese servidor.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
(async () => {
  const browser = await chromium.launch({headless:true, ...(process.env.BROWSER_CHANNEL ? {channel:process.env.BROWSER_CHANNEL} : {})});
  try {
    const page = await browser.newPage({viewport:{width:1100,height:850}});
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto('http://127.0.0.1:8765');
    await page.locator('#username').fill('cliente-prueba');
    await page.locator('#password').fill('solo-prueba-local-2026');
    await page.getByRole('button', {name:'Iniciar sesión'}).click();
    await page.locator('#chat').waitFor({state:'visible'});
    await page.locator('#message').fill('Mi laptop no enciende');
    await page.locator('#send').click();
    await page.getByText('Comprueba la toma de corriente', {exact:false}).waitFor();
    await page.locator('#message').fill('Quiero un presupuesto de ejemplo');
    await page.locator('#send').click();
    await page.locator('.quote').waitFor();
    const quote = await page.locator('.quote').innerText();
    if (!quote.includes('MANO DE OBRA') || !quote.includes('REPUESTOS') || !quote.includes('260.00')) throw Error('Presupuesto no visible');
    await page.reload();
    await page.locator('.quote').waitFor();
    if (await page.locator('.bubble').count() !== 4) throw Error('Historial incorrecto');
    await page.screenshot({path:'.local/portal-desktop.png',fullPage:true});
    await page.setViewportSize({width:390,height:844});
    if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)) throw Error('Desbordamiento móvil');
    await page.screenshot({path:'.local/portal-mobile.png',fullPage:true});
    await page.locator('#logout').click();
    await page.locator('#access').waitFor({state:'visible'});
    if (errors.length) throw Error(errors.join('\n'));
    console.log('Navegador OK: login, envío, respuesta, presupuesto, historial, móvil y logout.');
  } finally { await browser.close(); }
})().catch(error => {console.error(error); process.exit(1);});
