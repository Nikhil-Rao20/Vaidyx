// The public site (/tb-nik): the product page's hero at every size and the whole page on a laptop and a phone, the phone menu, the
// signed-in variant of the actions, and the About, Docs and Contact pages. Mock mode only (nothing is sent anywhere).
import { expect, test } from "@playwright/test";
import { MOCK, SHOTS, SIZES, shoot, visit, watchConsole } from "../support/helpers";

test.describe("landing", () => {
  test.skip(!MOCK, "the public site is taken with mocked answers");

  test("product page", async ({ page }) => {
    const errors = watchConsole(page);
    await visit(page, "/", { signedOut: true });
    await expect(page.getByTestId("landing-hero")).toBeVisible();
    await expect(page.getByRole("heading", { level: 1 })).toContainText(/\S/);  // the words are the owner's, in content.ts
    await expect(page.getByTestId("landing-signin")).toHaveText(/Sign in/);
    await shoot(page, "landing", "hero", { fullPage: false, before: (pg) => pg.waitForTimeout(2600) });
    await shoot(page, "landing", "full", { fullPage: true, sizes: [SIZES[0], SIZES[2]] });
    await page.setViewportSize(SIZES[2]);
    await page.getByRole("button", { name: "Open the menu" }).click();
    await expect(page.getByRole("navigation", { name: "Pages" }).last()).toBeVisible();
    await page.waitForTimeout(400);
    await page.screenshot({ path: `${SHOTS}/landing-menu-light-390.png` });
    await page.getByRole("button", { name: "Close the menu" }).click();
    for (const id of ["how", "sources", "journey", "safety"]) await expect(page.locator(`#${id}`)).toHaveCount(1);
    await expect(page.getByTestId("open-docs").first()).toBeAttached();
    await expect(page.getByTestId("ask-demo")).toBeAttached();
    await expect(page.getByTestId("journey-diagram")).toBeAttached();
    await page.getByTestId("journey-next").click();
    await expect(page.getByTestId("journey-panel")).toHaveAttribute("data-step", "quote");
    await page.getByTestId("journey-restart").click();
    await expect(page.getByTestId("journey-panel")).toHaveAttribute("data-step", "uhid");
    await expect(page.locator('#why a[href="https://doi.org/10.3332/ecancer.2026.2090"]').first()).toBeAttached();
    await expect(page.getByTestId("safety")).toBeAttached();
    expect(errors, errors.join("\n")).toEqual([]);
  });

  // 12 Nov: the five boxes under the hero ("What Vaidyx does"), the sections they open, and "Customisable for your hospital".
  test("the five boxes, their sections and the customisable section", async ({ page }) => {
    const errors = watchConsole(page);
    await visit(page, "/", { signedOut: true });
    await expect(page.getByTestId("landing-hero")).toBeVisible();
    const boxes = [
      { key: "proof", to: "sources", title: "Every answer shows its proof" },
      { key: "pubmed", to: "pubmed", title: "Evidence from PubMed" },
      { key: "benchmark", to: "benchmark", title: "Models tested before use" },
      { key: "local", to: "local", title: "Runs inside your hospital" },
      { key: "assistant", to: "how", title: "One assistant, start to finish" },
    ];
    const pillars = page.getByTestId("pillars");
    await expect(pillars.locator("a.l-pillar")).toHaveCount(5);
    // under the hero: the boxes start below the hero's end and before the problem section
    const order = await page.evaluate(() => {
      const y = (sel: string) => (document.querySelector(sel) as HTMLElement).getBoundingClientRect().top + window.scrollY;
      const hero = document.querySelector('[data-testid="landing-hero"]') as HTMLElement;
      return { heroEnd: y('[data-testid="landing-hero"]') + hero.offsetHeight, boxes: y('[data-testid="pillars"]'), why: y("#why") };
    });
    expect(order.boxes).toBeGreaterThanOrEqual(order.heroEnd);
    expect(order.boxes).toBeLessThan(order.why);
    for (const b of boxes) {
      const box = page.getByTestId(`pillar-${b.key}`);
      await box.scrollIntoViewIfNeeded();
      await expect(box).toBeVisible();
      await expect(box).toContainText(b.title);
      await expect(box).toHaveAttribute("href", `#${b.to}`);
      await box.click();
      // the click lands on the section: its heading is in view and clear of the top bar (16 px + 56 px)
      const heading = page.locator(`#${b.to} h2`).first();
      await expect(heading).toBeInViewport();
      expect(await heading.evaluate((e) => e.getBoundingClientRect().top)).toBeGreaterThanOrEqual(72);
    }
    // a box is a link a keyboard reaches
    await page.getByTestId("pillar-proof").focus();
    await expect(page.getByTestId("pillar-proof")).toBeFocused();
    // the three new sections show what they say
    await expect(page.getByTestId("pubmed-line")).toHaveCount(2);
    await expect(page.getByTestId("pubmed-label")).toContainText("Published evidence, not advice for this patient.");
    await expect(page.getByTestId("pubmed-demo").locator('a[href^="https://pubmed.ncbi.nlm.nih.gov/"]')).toHaveCount(2);
    await expect(page.getByTestId("benchmark-row")).toHaveCount(13);
    await expect(page.locator('[data-testid="benchmark-row"][data-kind="general"]')).toHaveCount(2);
    await expect(page.getByTestId("benchmark-row").first()).toContainText("Gemma-4-31B-it");
    await expect(page.getByTestId("benchmark-row").first()).toContainText("76.6");
    await expect(page.getByTestId("benchmark-link")).toHaveAttribute("href", /\/research$/);
    await expect(page.getByTestId("local-server")).toContainText("Gemma-4-31B (non-medical)");
    await expect(page.getByTestId("local-server")).toContainText("Qwen3.5-4B (Chinese, non-medical)");
    await expect(page.getByTestId("local-pubmed")).toBeAttached();
    // Customisable for your hospital: the tabs change the panel, the level switch changes the checklist, arrows move the tabs
    const custom = page.getByTestId("customise");
    await custom.scrollIntoViewIfNeeded();
    await expect(custom.getByRole("heading", { level: 2 })).toContainText("for your hospital");
    const panel = page.getByTestId("custom-panel");
    await expect(custom.getByRole("tab")).toHaveCount(6);
    await expect(panel).toHaveAttribute("data-tab", "hospital");
    await expect(page.getByTestId("custom-pmjay")).toHaveAttribute("aria-checked", "true");
    await page.getByTestId("custom-pmjay").click();
    await expect(page.getByTestId("custom-pmjay")).toHaveAttribute("aria-checked", "false");
    await page.getByTestId("custom-tab-checklists").click();
    await expect(panel).toHaveAttribute("data-tab", "checklists");
    await expect(page.getByTestId("custom-tab-checklists")).toHaveAttribute("aria-selected", "true");
    await expect(panel).toContainText("Breast cancer");
    await expect(page.locator('[data-testid="custom-check-row"][data-needed="true"]')).toHaveCount(3);
    await page.getByTestId("custom-level-optimal").click();
    await expect(page.locator('[data-testid="custom-check-row"][data-needed="true"]')).toHaveCount(4);
    await page.getByTestId("custom-tab-checklists").focus();
    await page.keyboard.press("ArrowRight");
    await expect(panel).toHaveAttribute("data-tab", "agents");
    await expect(page.getByTestId("custom-tab-agents")).toBeFocused();
    await expect(panel).toContainText("Radiology support");
    await page.keyboard.press("End");
    await expect(panel).toHaveAttribute("data-tab", "meetings");
    await expect(panel).toContainText("Every week on Friday");
    await shoot(page, "landing", "customise", { fullPage: false, sizes: [SIZES[0], SIZES[2]], before: async (pg) => { await pg.getByTestId("customise").scrollIntoViewIfNeeded(); } });
    // a phone: nothing scrolls sideways, and nothing in the new sections is wider than the screen
    await page.setViewportSize(SIZES[2]);
    await page.waitForTimeout(300);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
    const wide = await page.evaluate(() => ["what", "pubmed", "benchmark", "local", "customise"].flatMap((id) =>
      [...document.querySelectorAll(`#${id} :is(h2, h3, p, li, a, .l-card, .l-tile, .l-box, .l-zone)`)]
        .filter((e) => !e.closest('[role="tablist"]') && e.getBoundingClientRect().right > window.innerWidth + 1)
        .map((e) => `${id}: ${e.tagName} ${(e.textContent ?? "").slice(0, 40)}`)));
    expect(wide, wide.join("\n")).toEqual([]);
    await page.getByTestId("pillar-local").scrollIntoViewIfNeeded();
    await page.getByTestId("pillar-local").click();
    await expect(page.locator("#local h2").first()).toBeInViewport();
    expect(errors, errors.join("\n")).toEqual([]);
  });

  test("about, docs and contact", async ({ page }) => {
    await visit(page, "/about", { signedOut: true });
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Meet");
    for (const id of ["team", "tanuh"]) await expect(page.locator(`#${id}`)).toHaveCount(1);
    await shoot(page, "site", "about", { fullPage: true, sizes: [SIZES[0], SIZES[2]], themes: ["light"] });
    await visit(page, "/docs", { signedOut: true });
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Documentation");
    await shoot(page, "site", "docs", { fullPage: true, sizes: [SIZES[0], SIZES[2]], themes: ["light"] });
    await visit(page, "/contact", { signedOut: true });
    await expect(page.getByTestId("contact-email")).toHaveAttribute("href", /mailto:.*subject=/);
    await expect(page.getByTestId("contact-notice")).toContainText("not built yet");
    await shoot(page, "site", "contact", { fullPage: true, sizes: [SIZES[0], SIZES[2]], themes: ["light"] });
    // the enquiry form posts to the site's own endpoint (answered by the mock) and thanks the visitor
    await page.getByLabel("Your name").fill("Dr Test Person");
    await page.getByLabel("Your email").fill("test.person@example.org");
    await page.getByLabel("Hospital or institution").fill("Example Hospital");
    await page.getByLabel("Message").fill("We would like to try Vaidyx for our breast Tumour Board.");
    await page.getByRole("button", { name: "Send enquiry" }).click();
    await expect(page.getByTestId("contact-done")).toBeVisible();
  });

  test("research", async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await visit(page, "/research", { signedOut: true });
    await expect(page.getByRole("heading", { level: 1 })).toContainText(/\S/);
    await expect(page.getByTestId("research-download")).toHaveAttribute("href", "/static/tb-nik/research/vaidyx-benchmark-2026.pdf");
    const pdf = await page.request.get("/static/tb-nik/research/vaidyx-benchmark-2026.pdf");
    expect(pdf.status()).toBe(200);
    expect((await pdf.body()).subarray(0, 5).toString()).toBe("%PDF-");
    await expect(page.locator("figure table")).toHaveCount(21); // Tables 1 and 3-22; Table 2 is the data cards
    await expect(page.locator(".r-fig svg.vfig")).toHaveCount(9);
    await expect(page.getByTestId("fig-ranking")).toContainText("Figure 1.");
    await expect(page.getByTestId("research-datacards")).toContainText("Table 2.");
    await expect(page.getByTestId("research-datacards").locator(".l-box")).toHaveCount(11);
    await expect(page.getByTestId("research-text-cot").locator("tbody tr")).toHaveCount(13);
    await expect(page.getByTestId("research-text-cot").locator("tbody tr").first()).toContainText("Gemma-4-31B-it");
    await expect(page.getByTestId("research-table-models")).toContainText("China");
    await shoot(page, "site", "research", { fullPage: true, sizes: [SIZES[0], SIZES[2]], themes: ["light", "dark"] });
    expect(errors, errors.join("\n")).toEqual([]);
  });

  test("signed in", async ({ page }) => {
    await visit(page, "/", { role: "treating" });
    await expect(page.getByTestId("landing-signin")).toHaveText(/Open Case Files/);
    await page.getByTestId("landing-signin").click();
    await expect(page).toHaveURL(/\/tb-nik\/cases$/);
  });
});
