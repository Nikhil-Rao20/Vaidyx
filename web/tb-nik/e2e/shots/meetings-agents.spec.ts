// The AI agents in the meeting (night-v3 Phase 6, research/05 sections 6 and 11.3): the agent tiles (title, "AI agent, support
// only", the state word, the menu), the Agents panel ("Agents in this meeting" with the coordinator's switches, a member's rows in
// words, "Members can ask the agents"), with the live channel mocked. Agents are never members of the board and never counted.
// Run: cd web/tb-nik && TBNIK_MOCK=1 npx playwright test -c e2e/playwright.config.ts meetings-agents
// Routes: e2e/support/f2.ts (SYNTHETIC).
import { expect, test, type Page } from "@playwright/test";
import { SIZES, login, prepare, watchConsole } from "../support/helpers";
import { AGENT_ANSWER_NOTE, MID, meetingState, memberState, routeCaseFile, routeMeetings, type MeetingRouteOptions } from "../support/f2";
import type { Role } from "../support/fixtures";

const OUT = process.env.AGENT_SHOTS ?? "";
// TBNIK_DEV_URL (for example http://127.0.0.1:5199, a local `vite` dev server with base /static/tb-nik/ and no HMR) serves the
// site from the source instead of the build, to check a screen before the site is built.
const DEV = process.env.TBNIK_DEV_URL ?? "";

/** The console errors that count: from the dev server, its HMR socket and React's development warnings are left out. */
const real = (errors: string[]) => (DEV ? errors.filter((e) => !/\[vite\]|Vite server|static\/tb-nik\/\?token=|Function components cannot be given refs/.test(e)) : errors);

async function routeDev(page: Page) {
  if (!DEV) return;
  const pass = async (route: import("@playwright/test").Route, url: string) => {
    const res = await fetch(url);
    route.fulfill({ status: res.status, headers: { "content-type": res.headers.get("content-type") ?? "text/plain" }, body: Buffer.from(await res.arrayBuffer()) });
  };
  await page.route("**/static/tb-nik/**", (route) => { const u = new URL(route.request().url()); return pass(route, `${DEV}${u.pathname}${u.search}`); });
  await page.route(/\/tb-nik(\/[^.]*)?$/, (route) => (route.request().resourceType() === "document" ? pass(route, `${DEV}/static/tb-nik/`) : route.fallback()));
}

async function open(page: Page, to: string, o: MeetingRouteOptions & { role?: Role; wait: string }) {
  await prepare(page, { role: o.role ?? "coordinator" });
  await routeCaseFile(page);
  const live = await routeMeetings(page, o);
  await routeDev(page);
  await login(page);
  await page.goto(`/tb-nik${to}`);
  await page.getByTestId(o.wait).first().waitFor({ timeout: 20_000 });
  await page.waitForLoadState("networkidle").catch(() => {});
  return live;
}

async function shot(page: Page, name: string) {
  if (!OUT) return;
  for (const theme of ["light", "dark"] as const) {
    await page.evaluate((t) => document.documentElement.setAttribute("data-theme", t), theme);
    await page.waitForTimeout(150);
    await page.screenshot({ path: `${OUT}/meetings-agents-${name}-${theme}-${page.viewportSize()?.width}.png` });
  }
}

test.describe("Meetings: AI agents", () => {
  for (const size of [SIZES[0], SIZES[2]]) {
    test(`coordinator: the tiles, the menu and the Agents panel at ${size.width}`, async ({ page }) => {
      const errors = watchConsole(page);
      await page.setViewportSize(size);
      const live = await open(page, `/meetings/${MID}`, { wait: "control-view", state: meetingState("in_session") });
      const pathology = page.locator("[data-testid=agent-tile][data-role=pathology]");
      await expect(pathology).toHaveAttribute("data-agent-state", "thinking");
      await expect(pathology).toContainText("Pathology, AI agent standing in");
      await expect(pathology).toContainText("AI agent, support only");
      await expect(pathology).toContainText("Thinking");
      // Listening to a name, then speaking.
      live.push({ type: "agent_state", role: "nuclear_medicine", state: "listening", by: "shanthi@vxh.example", by_name: "Shanthi Raman", question: null });
      const nm = page.locator("[data-testid=agent-tile][data-role=nuclear_medicine]");
      await expect(nm).toHaveAttribute("data-agent-state", "listening");
      await expect(nm).toContainText("Listening to Shanthi Raman");
      await expect(nm.getByRole("button", { name: /^Nuclear Medicine, AI agent standing in, AI agent, support only, Listening to Shanthi Raman/ })).toBeVisible();
      await shot(page, "tiles");
      // The tile menu: Ask the agent and, for the coordinator, Remove from this meeting.
      await nm.getByTestId("agent-tile-menu").click();
      await expect(page.getByTestId("agent-ask")).toBeVisible();
      await expect(page.getByTestId("agent-remove")).toHaveText("Remove from this meeting");
      await page.keyboard.press("Escape");
      // The Agents panel: the six roles with their switches and reasons.
      await pathology.getByRole("button").first().click();
      const panel = page.getByTestId("agents-panel");
      await expect(panel).toBeVisible();
      const rows = panel.getByTestId("agent-roster-row");
      await expect(rows).toHaveCount(6);
      await expect(panel.locator("[data-testid=agent-roster-row][data-role=pathology] [data-testid=agent-reason]")).toHaveText("Head absent");
      await expect(panel.locator("[data-testid=agent-roster-row][data-role=radiology] [data-testid=agent-reason]")).toHaveText("Head present");
      await expect(panel.locator("[data-testid=agent-roster-row][data-role=radiation_oncology] [data-testid=agent-reason]")).toHaveText("Not in this meeting");
      await expect(panel.getByRole("switch", { name: "Pathology: In this meeting" })).toBeChecked();
      await expect(panel.getByRole("switch", { name: "Radiation Oncology: In this meeting" })).not.toBeChecked();
      await expect(panel.getByRole("switch", { name: "Members can ask the agents" })).toBeChecked();
      await shot(page, "panel-coordinator");
      // A switch posts {role, on}; the settings switch puts {members_ask}.
      const add = page.waitForRequest((r) => r.method() === "POST" && r.url().endsWith(`/meetings/${MID}/agents`));
      await panel.getByRole("switch", { name: "Radiation Oncology: In this meeting" }).click();
      expect((await add).postDataJSON()).toEqual({ role: "radiation_oncology", on: true });
      const ask = page.waitForRequest((r) => r.method() === "PUT" && r.url().endsWith(`/meetings/${MID}/agents/settings`));
      await panel.getByRole("switch", { name: "Members can ask the agents" }).click();
      expect((await ask).postDataJSON()).toEqual({ members_ask: false });
      expect(real(errors)).toEqual([]);
    });
  }

  // night-v3 6.2: the points from the start of the case, their chips, Present your points and why it waits.
  for (const size of [SIZES[0], SIZES[2]]) {
    test(`coordinator: the points with chips and Present your points at ${size.width}`, async ({ page }) => {
      const errors = watchConsole(page);
      await page.setViewportSize(size);
      const live = await open(page, `/meetings/${MID}`, { wait: "control-view", state: meetingState("in_session") });
      const pathology = page.locator("[data-testid=agent-tile][data-role=pathology]");
      const nm = page.locator("[data-testid=agent-tile][data-role=nuclear_medicine]");
      if (size.width > 1000) {
        // The count on the tile (a narrow phone tile leaves it to the panel).
        await expect(pathology.locator("[data-part=count]")).toHaveText("3 points from the records");
        await expect(nm.locator("[data-part=count]")).toHaveText("No points yet");
      }
      await expect(pathology.getByRole("button", { name: /Thinking, 3 points from the records\. Open the Agents panel$/ })).toBeAttached();
      // The tile menu offers Present your points, disabled with the reason when the brief lists no points.
      await nm.getByTestId("agent-tile-menu").click();
      await expect(page.getByTestId("agent-present")).toHaveAttribute("data-disabled", "");
      await expect(page.getByTestId("agent-present-why")).toHaveText("The brief lists no points for review.");
      await page.keyboard.press("Escape");
      await pathology.getByRole("button").first().click();
      const panel = page.getByTestId("agents-panel");
      const card = panel.locator("[data-testid=agent-card][data-role=pathology]");
      await expect(card.getByTestId("points-header")).toHaveText("Points from the records, AI draft, not reviewed");
      const chips = card.getByTestId("agent-points").getByTestId("point-chip");
      await expect(chips).toHaveCount(3);
      await expect(chips.first()).toHaveText("Histopathology report, 17/09/2026, p. 1");
      await expect(chips.first()).toHaveAttribute("title", "\"Grade: Grade 2 (Nottingham score 6)\"");
      await expect(card.getByTestId("points-not-documented")).toHaveText("2 items not documented; see the Case File");
      const nmCard = panel.locator("[data-testid=agent-card][data-role=nuclear_medicine]");
      await expect(nmCard.getByTestId("present-points")).toBeDisabled();
      await expect(nmCard.getByTestId("present-why")).toHaveText("The brief lists no points for review.");
      await card.getByTestId("agent-points").scrollIntoViewIfNeeded();
      await shot(page, "points");
      // The coordinator's chip opens the record on the stage.
      const opened = page.waitForRequest((r) => r.method() === "POST" && r.url().endsWith(`/meetings/${MID}/open`));
      await chips.first().click();
      expect((await opened).postDataJSON()).toEqual({ kind: "record", doc_id: "D8a2c165d" });
      if (!(await panel.isVisible())) await pathology.getByRole("button").first().click();
      // Present your points posts and the answer lands in the card's questions with the not documented list.
      const posted = page.waitForRequest((r) => r.method() === "POST" && r.url().endsWith(`/meetings/${MID}/agents/pathology/present`));
      await card.getByTestId("present-points").click();
      await posted;
      const answer = card.getByTestId("agent-questions").locator("li", { hasText: "Present your points" });
      await expect(answer).toBeVisible();
      await expect(answer.getByTestId("point-chip")).toHaveCount(3);
      await expect(answer.getByTestId("answer-not-documented")).toContainText("HER2 FISH result");
      await answer.scrollIntoViewIfNeeded();
      await shot(page, "present-answer");
      // While the brief is prepared: "Reading the records" on the tile and the reason beside the disabled button.
      const agents = (meetingState("in_session") as unknown as { agents: Array<Record<string, unknown>> }).agents.map((a) => (a.role === "pathology" ? { ...a, brief: { status: "preparing", label: "", at: null, reviewed_by: null, message: "" }, points: [], points_count: 0 } : a));
      live.push({ type: "agents", agents });
      await expect(card.getByTestId("present-why")).toHaveText("The brief is still being prepared from the records.");
      await expect(card.getByTestId("present-points")).toBeDisabled();
      await expect(card.getByTestId("agent-points")).toContainText("Reading the records for Pathology");
      if (size.width > 1000) await expect(pathology.locator("[data-part=count]")).toHaveText("Reading the records");
      expect(real(errors)).toEqual([]);
    });
  }

  test("member: a chip shows its quote; the room screen shows the count and the first point", async ({ page }) => {
    const errors = watchConsole(page);
    await page.setViewportSize(SIZES[0]);
    await open(page, `/meetings/${MID}/member`, { role: "treating", wait: "member-view", state: memberState() });
    await page.locator("[data-testid=agent-tile][data-role=pathology]").getByRole("button").first().click();
    const card = page.getByTestId("agents-panel").locator("[data-testid=agent-card][data-role=pathology]");
    const opened = { n: 0 };
    page.on("request", (r) => { if (r.method() === "POST" && r.url().endsWith("/open")) opened.n += 1; });
    await card.getByTestId("point-chip").first().click();
    await expect(card.getByTestId("point-quote")).toHaveText("\"Grade: Grade 2 (Nottingham score 6)\"");
    expect(opened.n).toBe(0);
    await page.setViewportSize(SIZES[1]);
    await open(page, `/meetings/${MID}/room`, { wait: "room-screen", state: meetingState("in_session") });
    const tile = page.getByTestId("room-people").locator("[data-testid=agent-tile][data-role=pathology]");
    await expect(tile.locator("[data-part=count]")).toContainText("3 points from the records");
    await expect(tile.locator("[data-part=point]")).toHaveText("The histopathology report records invasive breast carcinoma of no special type, Grade 2 (Nottingham score 6).");
    expect(await page.getByTestId("room-people").evaluate((el) => el.scrollHeight <= el.clientHeight + 1)).toBe(true);
    await shot(page, "room");
    expect(real(errors)).toEqual([]);
  });

  // night-v3 6.3: ask an agent; the answer streams statement by statement; Stop; the queue; a refusal; the @mention.
  for (const size of [SIZES[0], SIZES[2]]) {
    test(`ask an agent: the answer streams, the references, the footer and Stop at ${size.width}`, async ({ page }) => {
      const errors = watchConsole(page);
      await page.setViewportSize(size);
      const live = await open(page, `/meetings/${MID}`, { wait: "control-view", state: meetingState("in_session") });
      const nm = page.locator("[data-testid=agent-tile][data-role=nuclear_medicine]");
      await nm.getByTestId("agent-tile-menu").click();
      await page.getByTestId("agent-ask").click();
      const box = page.locator("#agent-q-nuclear_medicine");
      await expect(box).toBeFocused();
      await expect(box).toHaveAttribute("placeholder", "Ask Nuclear Medicine about this Case File");
      await box.fill("Is a bone scan reported?");
      const sent = page.waitForResponse((r) => r.request().method() === "POST" && r.url().endsWith(`/meetings/${MID}/questions`));
      await page.getByTestId("send-agent-q-nuclear_medicine").click();
      const res = await sent;
      expect(res.request().postDataJSON()).toEqual({ text: "Is a bone scan reported?", role: "nuclear_medicine" });
      const q = (await res.json()).question as Record<string, unknown>;
      const card = page.getByTestId("agents-panel").locator("[data-testid=agent-card][data-role=nuclear_medicine]");
      const item = card.locator(`[data-testid=question-item][data-question=${q.id}]`);
      await expect(item.getByTestId("answer-waiting")).toHaveText("Thinking");
      // The statements arrive one by one.
      const s1 = { text: "The OPD consultation note of 15/09/2026 records that a bone scan was advised.", citations: [{ doc_id: "Df40ab347", doc_title: "OPD CONSULTATION NOTE", date: "2026-09-15", page: 0, quote: "Bone scan advised" }] };
      const s2 = { text: "No bone scan report is in this Case File.", citations: [], note: "This is a consultation record; the Medical Oncology agent can say more." };
      const base = { role: "nuclear_medicine", label: "Nuclear Medicine support", model: "gemma-4-31b", note: AGENT_ANSWER_NOTE, references: [] };
      live.push({ type: "agent_state", role: "nuclear_medicine", state: "answering", by: "mdt@vxh.example", by_name: "Priya Nair", question: q.id });
      live.push({ type: "question", question: { ...q, answer: { ...base, status: "answering", statements: [s1], text: s1.text, speech: ["AI agent, Nuclear Medicine.", s1.text] } } });
      await expect(item.getByTestId("answer-statement")).toHaveCount(1);
      await expect(item.getByTestId("answer-streaming")).toHaveText("Answering");
      live.push({ type: "question", question: { ...q, answer: { ...base, status: "answering", statements: [s1, s2], text: `${s1.text} ${s2.text}`, speech: ["AI agent, Nuclear Medicine.", s1.text, s2.text] } } });
      await expect(item.getByTestId("answer-statement")).toHaveCount(2);
      await expect(item.getByTestId("answer-statement").nth(1)).toContainText("the Medical Oncology agent can say more");
      const refs = [{ ref_id: "R1", title: "NCG Guidelines for Breast Cancer", org: "National Cancer Grid", year: 2023, page: 14, quote: "A bone scan is indicated for stage III disease or symptoms suggestive of bone involvement." }];
      live.push({ type: "question", question: { ...q, answer: { ...base, status: "answered", statements: [s1, s2], text: `${s1.text} ${s2.text}`, references: refs, at: new Date().toISOString(), seconds: 7.2, speech: ["AI agent, Nuclear Medicine.", s1.text, s2.text, "Sources are on the screen."] } } });
      await expect(item.getByTestId("answer-streaming")).toHaveCount(0);
      await expect(item.getByTestId("answer-references")).toContainText("Reference text, not about this patient");
      await expect(item.getByTestId("answer-references")).toContainText("NCG Guidelines for Breast Cancer, National Cancer Grid, 2023, p. 14");
      await expect(item.getByTestId("sources-line")).toHaveText("Sources are on the screen.");
      await expect(item.getByTestId("answer-footer")).toContainText("AI agent, support only. From the records and guidelines only. Check the source. Gemma-4-31B (non-medical).");
      // Speaking somewhere: the coordinator's Stop stops the voice for everyone (on the answer and on the tile's menu).
      live.push({ type: "agent_state", role: "nuclear_medicine", state: "speaking", by: "mdt@vxh.example", by_name: "Priya Nair", question: q.id });
      await expect(nm).toHaveAttribute("data-agent-state", "speaking");
      await item.scrollIntoViewIfNeeded();
      await shot(page, "answer");
      await expect(item.getByTestId("answer-stop")).toBeVisible();
      const stop = page.waitForRequest((r) => r.method() === "POST" && r.url().endsWith(`/meetings/${MID}/agents/nuclear_medicine/stop`));
      if (size.width > 1000) {
        // The laptop: Stop from the tile's menu.
        await nm.getByTestId("agent-tile-menu").click();
        await expect(page.getByTestId("agent-stop")).toHaveText("Stop for everyone");
        await page.getByTestId("agent-stop").click();
      } else await item.getByTestId("answer-stop").click();
      expect((await stop).postDataJSON()).toEqual({ question: q.id });
      expect(real(errors)).toEqual([]);
    });
  }

  test("the queue line, a refusal with the quick questions, and the @mention", async ({ page }) => {
    const errors = watchConsole(page);
    await page.setViewportSize(SIZES[0]);
    await open(page, `/meetings/${MID}`, { wait: "control-view", state: meetingState("in_session") });
    // Pathology is still answering Thomas Joseph: a second question waits.
    await page.locator("[data-testid=agent-tile][data-role=pathology]").getByRole("button").first().click();
    const card = page.getByTestId("agents-panel").locator("[data-testid=agent-card][data-role=pathology]");
    await page.locator("#agent-q-pathology").fill("And the PR score?");
    await page.getByTestId("send-agent-q-pathology").click();
    await expect(card.getByTestId("queue-line")).toHaveText("Pathology is answering Thomas Joseph. Yours is next.");
    // The Questions tab: "@nuclear medicine" picks that agent's chip; the mention is stripped on send.
    await page.getByTestId("panel-chat").click();
    const tab = page.getByTestId("questions-panel");
    await expect(tab.getByTestId("mention-hint")).toHaveText("Type @ and a department to ask one agent, for example @Radiology");
    const box = page.locator("#member-q");
    await box.fill("@nuclear medicine what would you do here?");
    await expect(tab.locator("[data-testid=ask-chip][data-role=nuclear_medicine]")).toHaveAttribute("aria-pressed", "true");
    const sent = page.waitForRequest((r) => r.method() === "POST" && r.url().endsWith(`/meetings/${MID}/questions`));
    await page.getByTestId("send-question").click();
    expect((await sent).postDataJSON()).toEqual({ text: "what would you do here?", role: "nuclear_medicine" });
    const refusal = tab.locator("[data-testid=question-item][data-status=out_of_scope]");
    await expect(refusal.getByTestId("answer-refusal")).toContainText("I can't recommend or choose treatment.");
    await expect(refusal.getByTestId("quick-question")).toHaveText(["What do the records document?", "What is pending?"]);
    await refusal.scrollIntoViewIfNeeded();
    await shot(page, "refusal");
    await refusal.getByTestId("quick-question").nth(1).click();
    await expect(box).toHaveValue("What is pending?");
    await expect(box).toBeFocused();
    // An agent that is not in this meeting: the reason beside the box, the text kept.
    await box.fill("@Radiology what does the mammogram record?");
    await page.getByTestId("send-question").click();
    await expect(tab.getByTestId("ask-error")).toHaveText("That agent is not in this meeting. The coordinator can add it.");
    await expect(box).toHaveValue("@Radiology what does the mammogram record?");
    expect(real(errors)).toEqual([]);
  });

  test("member: questions to the agents closed by the coordinator", async ({ page }) => {
    const errors = watchConsole(page);
    await page.setViewportSize(SIZES[0]);
    const st = memberState() as unknown as { can: Record<string, unknown> };
    st.can = { ...st.can, ask_agents: false };
    await open(page, `/meetings/${MID}/member`, { role: "treating", wait: "member-view", state: st });
    await page.getByTestId("panel-chat").click();
    const tab = page.getByTestId("questions-panel");
    await expect(tab.locator("[data-testid=ask-chip][data-role=pathology]")).toBeDisabled();
    await expect(tab.getByTestId("mention-hint")).toHaveText("The MDT Coordinator has closed questions to the agents for now.");
    await page.locator("#member-q").fill("@Pathology what is the grade?");
    await page.getByTestId("send-question").click();
    await expect(tab.getByTestId("ask-error")).toHaveText("The MDT Coordinator has closed questions to the agents for now.");
    expect(real(errors)).toEqual([]);
  });

  test("member: the rows in words, no switches", async ({ page }) => {
    const errors = watchConsole(page);
    await page.setViewportSize(SIZES[0]);
    await open(page, `/meetings/${MID}/member`, { role: "treating", wait: "member-view", state: memberState() });
    const tile = page.locator("[data-testid=agent-tile][data-role=pathology]");
    await tile.getByTestId("agent-tile-menu").click();
    await expect(page.getByTestId("agent-ask")).toBeVisible();
    await expect(page.getByTestId("agent-remove")).toHaveCount(0);
    await page.getByTestId("agent-ask").click();
    const panel = page.getByTestId("agents-panel");
    await expect(panel.getByRole("switch")).toHaveCount(0);
    await expect(panel.locator("[data-testid=agent-roster-row][data-role=pathology] [data-testid=agent-reason]")).toHaveText("In this meeting: Head absent");
    await shot(page, "panel-member");
    expect(real(errors)).toEqual([]);
  });
});
