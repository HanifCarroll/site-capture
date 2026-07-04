const fs = require('node:fs')

function loadJob() {
  if (globalThis.SITE_CAPTURE_JOB_OBJECT) return globalThis.SITE_CAPTURE_JOB_OBJECT
  const envJob = process.env.SITE_CAPTURE_JOB
  if (envJob) return JSON.parse(envJob)
  return JSON.parse(fs.readFileSync('.site-capture-job.json', 'utf8'))
}

async function main() {
  const job = loadJob()
  const warnings = []
  let status = null
  let title = null
  let finalUrl = null
  let error = null

  if (!job.url) throw new Error('SITE_CAPTURE_JOB.url is required')

  if (!state.siteCapturePage || state.siteCapturePage.isClosed()) {
    state.siteCapturePage = await context.newPage()
  }
  const capturePage = state.siteCapturePage
  if (job.viewport) {
    await capturePage.setViewportSize(job.viewport)
  }

  try {
    const response = await capturePage.goto(job.url, {
      waitUntil: 'domcontentloaded',
      timeout: job.gotoTimeoutMs || 45000,
    })
    status = response ? response.status() : null
  } catch (err) {
    error = String(err && err.message ? err.message : err)
    warnings.push(`Navigation issue: ${error}`)
  }

  try {
    if (typeof waitForPageLoad === 'function') {
      const load = await waitForPageLoad({
        page: capturePage,
        timeout: job.loadTimeoutMs || 10000,
        minWait: job.waitMs || 500,
      })
      if (!load || load.success === false) warnings.push(`Load check did not complete cleanly: ${JSON.stringify(load)}`)
    } else {
      await capturePage.waitForLoadState('networkidle', { timeout: job.loadTimeoutMs || 10000 })
    }
  } catch (err) {
    warnings.push(`Load wait issue: ${String(err && err.message ? err.message : err)}`)
  }

  const scrollSteps = Number(job.scrollSteps || 0)
  for (let i = 0; i < scrollSteps; i += 1) {
    try {
      await capturePage.mouse.wheel(0, 900)
      await capturePage.waitForTimeout(Number(job.scrollDelayMs || 250))
    } catch (err) {
      warnings.push(`Scroll issue: ${String(err && err.message ? err.message : err)}`)
      break
    }
  }
  try {
    await capturePage.evaluate(() => window.scrollTo(0, 0))
  } catch {}

  try {
    title = await capturePage.title()
  } catch (err) {
    warnings.push(`Title issue: ${String(err && err.message ? err.message : err)}`)
  }
  try {
    finalUrl = capturePage.url()
  } catch {}

  const formats = new Set(job.formats || [])
  let screenshot = null
  let markdown = null
  let html = null
  let links = []

  if (formats.has('screenshot')) {
    try {
      await capturePage.screenshot({ path: job.screenshotPath, fullPage: true, scale: 'css' })
      screenshot = 'page.png'
    } catch (err) {
      warnings.push(`Screenshot issue: ${String(err && err.message ? err.message : err)}`)
    }
  }

  if (formats.has('markdown')) {
    try {
      let content
      if (typeof getPageMarkdown === 'function') {
        content = await getPageMarkdown({ page: capturePage, showDiffSinceLastCall: false })
      } else {
        content = await capturePage.content()
        warnings.push('getPageMarkdown helper unavailable; wrote rendered HTML to page.md')
      }
      fs.writeFileSync(job.markdownPath, content, 'utf8')
      markdown = job.markdownFile
    } catch (err) {
      warnings.push(`Markdown issue: ${String(err && err.message ? err.message : err)}`)
    }
  }

  if (formats.has('html')) {
    try {
      const rendered = await capturePage.content()
      fs.writeFileSync(job.htmlPath, rendered, 'utf8')
      html = job.htmlFile
    } catch (err) {
      warnings.push(`HTML issue: ${String(err && err.message ? err.message : err)}`)
    }
  }

  try {
    links = await capturePage.$$eval('a[href]', anchors => anchors.map(anchor => anchor.href).filter(Boolean))
    fs.writeFileSync(job.linksPath, JSON.stringify(links, null, 2) + '\n', 'utf8')
  } catch (err) {
    warnings.push(`Link extraction issue: ${String(err && err.message ? err.message : err)}`)
  }

  const ok = !error && (status === null || (status >= 200 && status < 400))
  const result = {
    url: job.url,
    final_url: finalUrl,
    status,
    title,
    ok,
    screenshot,
    markdown,
    html,
    links,
    warnings,
    error,
  }
  return result
}

async function runCapture() {
  try {
    const result = await main()
    return 'SITE_CAPTURE_RESULT ' + JSON.stringify(result)
  } catch (err) {
    let url = null
    try {
      url = loadJob().url
    } catch {}
    const result = {
      url,
      final_url: null,
      status: null,
      title: null,
      ok: false,
      screenshot: null,
      markdown: null,
      html: null,
      links: [],
      warnings: [],
      error: String(err && err.stack ? err.stack : err),
    }
    return 'SITE_CAPTURE_RESULT ' + JSON.stringify(result)
  }
}

console.log(await runCapture())
