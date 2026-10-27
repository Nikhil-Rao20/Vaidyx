// Node checks of the agents' voice queue and the agent-voice default (night-v3 6.1), the pure parts of agentSpeaker.ts with a fake
// speak, a fake report and fake timers. Run: node src/features/meetings/call/__tests__/agentSpeaker.check.ts (Node 22.6 or later
// strips the types). Exits 1 on the first failure.
import assert from "node:assert/strict";
import { AgentSpeaker, agentVoicesFor, isAutoplayBlock, onTheFloor, speechItem, type SpeakItem, type SpeakerTimers } from "../agentSpeaker.ts";
import type { SpeakHandlers } from "@/lib/voice";
import type { MeetingQuestion } from "@/lib/live";

type Call = { item: SpeakItem; h: SpeakHandlers; stopped: boolean };

function rig(opts: { busy?: () => boolean; reportThrows?: "throw" | "reject" } = {}) {
  const calls: Call[] = [];
  const reports: Array<[string, boolean]> = [];
  const intervals = new Map<number, () => void>();
  const timeouts = new Map<number, () => void>();
  let n = 0;
  const timers: SpeakerTimers = {
    setInterval: (fn) => { n += 1; intervals.set(n, fn); return n as unknown as ReturnType<typeof setTimeout>; },
    clearInterval: (id) => { intervals.delete(id as unknown as number); },
    setTimeout: (fn) => { n += 1; timeouts.set(n, fn); return n as unknown as ReturnType<typeof setTimeout>; },
    clearTimeout: (id) => { timeouts.delete(id as unknown as number); },
  };
  const sp = new AgentSpeaker({
    speak: (item, h) => {
      const c: Call = { item, h, stopped: false };
      calls.push(c);
      // like lib/voice.ts Session: stop() says onStop once
      return { stop: () => { if (c.stopped) return; c.stopped = true; h.onStop?.(); } };
    },
    report: (q, p) => {
      reports.push([q, p]);
      if (opts.reportThrows === "throw") throw new Error("offline");
      if (opts.reportThrows === "reject") return Promise.reject(new Error("offline"));
      return Promise.resolve();
    },
    busy: opts.busy,
    timers,
  });
  const last = () => calls[calls.length - 1];
  const played = () => calls.map((c) => `${c.item.question}#${c.item.index}`);
  const tickIntervals = () => { for (const fn of [...intervals.values()]) fn(); };
  const fireTimeouts = () => { const fns = [...timeouts.values()]; timeouts.clear(); for (const fn of fns) fn(); };
  return { sp, calls, reports, intervals, timeouts, last, played, tickIntervals, fireTimeouts };
}

let passed = 0;
function check(name: string, fn: () => void) {
  try { fn(); passed += 1; } catch (e) { console.error(`FAIL ${name}`); console.error(e); process.exit(1); }
}

// ---- the agent-voice default -------------------------------------------------------------------------------------------------
check("a stored choice wins everywhere", () => {
  assert.equal(agentVoicesFor("member", true, true), true);
  assert.equal(agentVoicesFor("member", false, false), false);
  assert.equal(agentVoicesFor("coordinator", false, false), false);
  assert.equal(agentVoicesFor("room", false, false), false); // the room screen's own choice on that page
});
check("no choice: a member in the room starts muted", () => assert.equal(agentVoicesFor("member", true, null), false));
check("no choice: a remote member hears the agents", () => assert.equal(agentVoicesFor("member", false, null), true));
check("no choice: the coordinator hears the agents, in the room or not", () => {
  assert.equal(agentVoicesFor("coordinator", true, null), true);
  assert.equal(agentVoicesFor("coordinator", false, null), true);
});
check("no choice: the room screen plays", () => assert.equal(agentVoicesFor("room", true, null), true));

// ---- reading the events ------------------------------------------------------------------------------------------------------
check("speechItem reads {role, question, index}", () => {
  assert.deepEqual(speechItem({ type: "agent_speech", role: "radiology", question: "q1", index: 2, final: false }), { question: "q1", index: 2, role: "radiology" });
  assert.deepEqual(speechItem({ question: "q1", index: 0 }), { question: "q1", index: 0 });
});
check("speechItem refuses an event without a question or a valid index (and never takes text)", () => {
  assert.equal(speechItem({ question: "", index: 0 }), null);
  assert.equal(speechItem({ question: "q1" }), null);
  assert.equal(speechItem({ question: "q1", index: -1 }), null);
  assert.equal(speechItem({ question: "q1", index: 1.5 }), null);
  assert.equal(speechItem({ question: "q1", index: "1" }), null);
  const it = speechItem({ question: "q1", index: 0, text: "Spoken words" });
  assert.ok(it && !("text" in it));
});
check("onTheFloor: the question's Case File must be the one on the floor", () => {
  const qs = [{ id: "q1", by_name: "A", text: "t", at: "", case_id: "TB-001" }, { id: "q2", by_name: "A", text: "t", at: "", case_id: "TB-002" }, { id: "q3", by_name: "A", text: "t", at: "" }] as MeetingQuestion[];
  assert.equal(onTheFloor(qs, "q1", "TB-001"), true);
  assert.equal(onTheFloor(qs, "q2", "TB-001"), false);
  assert.equal(onTheFloor(qs, "q3", "TB-001"), true);   // an older question without a case
  assert.equal(onTheFloor(qs, "q9", "TB-001"), true);   // not in the state yet: a new one
  assert.equal(onTheFloor(qs, "q1", null), false);      // nothing on the floor
});
check("isAutoplayBlock knows NotAllowedError only", () => {
  assert.equal(isAutoplayBlock({ name: "NotAllowedError" }), true);
  assert.equal(isAutoplayBlock(new Error("x")), false);
  assert.equal(isAutoplayBlock(null), false);
});

// ---- the queue ---------------------------------------------------------------------------------------------------------------
check("plays one sentence at a time, the next after the end", () => {
  const r = rig();
  r.sp.enqueue({ question: "q1", index: 0 });
  r.sp.enqueue({ question: "q1", index: 1 });
  assert.deepEqual(r.played(), ["q1#0"]);
  assert.equal(r.sp.snapshot().queued, 1);
  r.last().h.onSpeaking?.();
  assert.deepEqual(r.sp.snapshot().speakingNow, { question: "q1", index: 0 });
  r.last().h.onEnd?.();
  assert.deepEqual(r.played(), ["q1#0", "q1#1"]);
  assert.equal(r.sp.snapshot().speakingNow, null); // between sentences until the next one starts
  r.last().h.onSpeaking?.();
  r.last().h.onEnd?.();
  assert.equal(r.sp.snapshot().speakingNow, null);
  assert.equal(r.sp.snapshot().queued, 0);
});
check("reports true once at the first start and false when the question's queue drains", () => {
  const r = rig();
  r.sp.enqueue({ question: "q1", index: 0 });
  r.sp.enqueue({ question: "q1", index: 1 });
  assert.deepEqual(r.reports, []); // nothing before the sound starts
  r.last().h.onSpeaking?.();
  assert.deepEqual(r.reports, [["q1", true]]);
  r.last().h.onEnd?.();
  r.last().h.onSpeaking?.();
  assert.deepEqual(r.reports, [["q1", true]]); // still the same answer
  r.last().h.onEnd?.();
  assert.deepEqual(r.reports, [["q1", true], ["q1", false]]);
  assert.equal(r.intervals.size, 0);
});
check("renews every interval while playing, stops renewing after", () => {
  const r = rig();
  r.sp.enqueue({ question: "q1", index: 0 });
  r.last().h.onSpeaking?.();
  assert.equal(r.intervals.size, 1);
  r.tickIntervals();
  r.tickIntervals();
  assert.deepEqual(r.reports, [["q1", true], ["q1", true], ["q1", true]]);
  r.last().h.onEnd?.();
  assert.equal(r.intervals.size, 0);
});
check("a sentence is never played twice, a late one keeps its place in the answer", () => {
  const r = rig();
  assert.equal(r.sp.enqueue({ question: "q1", index: 0 }), true);
  assert.equal(r.sp.enqueue({ question: "q1", index: 0 }), false); // playing
  r.sp.enqueue({ question: "q1", index: 2 });
  r.sp.enqueue({ question: "q2", index: 0 });
  r.sp.enqueue({ question: "q1", index: 1 });                     // late: before q1#2
  assert.equal(r.sp.enqueue({ question: "q1", index: 2 }), false); // queued
  r.last().h.onEnd?.();
  r.last().h.onEnd?.();
  r.last().h.onEnd?.();
  r.last().h.onEnd?.();
  assert.deepEqual(r.played(), ["q1#0", "q1#1", "q1#2", "q2#0"]);
  assert.equal(r.sp.enqueue({ question: "q1", index: 1 }), false); // already played
});
check("agent_stop: the question's queue goes, the sentence playing stops, later ones are ignored, others carry on", () => {
  const r = rig();
  r.sp.enqueue({ question: "q1", index: 0 });
  r.sp.enqueue({ question: "q1", index: 1 });
  r.sp.enqueue({ question: "q2", index: 0 });
  r.last().h.onSpeaking?.();
  const first = r.last();
  r.sp.stopQuestion("q1");
  assert.equal(first.stopped, true);
  assert.deepEqual(r.reports, [["q1", true], ["q1", false]]);
  assert.deepEqual(r.played(), ["q1#0", "q2#0"]);
  assert.equal(r.sp.enqueue({ question: "q1", index: 2 }), false);
  r.last().h.onSpeaking?.();
  assert.deepEqual(r.sp.snapshot().speakingNow, { question: "q2", index: 0 });
});
check("stopping a question that is only queued leaves the one playing alone", () => {
  const r = rig();
  r.sp.enqueue({ question: "q1", index: 0 });
  r.sp.enqueue({ question: "q2", index: 0 });
  r.sp.stopQuestion("q2");
  assert.equal(r.last().stopped, false);
  r.last().h.onEnd?.();
  assert.deepEqual(r.played(), ["q1#0"]);
});
check("NotAllowedError: the queue is kept, the chip flag is set, nothing plays until resume", () => {
  const r = rig();
  r.sp.enqueue({ question: "q1", index: 0 });
  r.last().h.onError?.({ name: "NotAllowedError" });
  assert.equal(r.sp.snapshot().blocked, true);
  assert.equal(r.sp.snapshot().queued, 1);
  r.sp.enqueue({ question: "q1", index: 1 });
  assert.equal(r.calls.length, 1);
  assert.deepEqual(r.reports, []); // never played, never reported
  r.sp.resume();
  assert.equal(r.sp.snapshot().blocked, false);
  assert.deepEqual(r.played(), ["q1#0", "q1#0"]);
  r.last().h.onSpeaking?.();
  r.last().h.onEnd?.();
  assert.deepEqual(r.played(), ["q1#0", "q1#0", "q1#1"]);
});
check("another error skips the sentence and goes on; the report ends when nothing of the answer waits", () => {
  const r = rig();
  r.sp.enqueue({ question: "q1", index: 0 });
  r.last().h.onSpeaking?.();
  r.last().h.onEnd?.();
  r.sp.enqueue({ question: "q1", index: 1 });
  r.last().h.onError?.(new Error("voice down"));
  assert.equal(r.sp.snapshot().blocked, false);
  assert.deepEqual(r.reports, [["q1", true], ["q1", false]]);
  r.sp.enqueue({ question: "q2", index: 0 });
  assert.deepEqual(r.played(), ["q1#0", "q1#1", "q2#0"]);
});
check("while the person dictates nothing new starts; a sentence playing stops and is played again after", () => {
  const r = rig();
  r.sp.enqueue({ question: "q1", index: 0 });
  r.last().h.onSpeaking?.();
  r.sp.setHeld(true);
  assert.equal(r.calls[0].stopped, true);
  assert.deepEqual(r.reports, [["q1", true], ["q1", false]]); // not playing while the person speaks
  r.sp.enqueue({ question: "q1", index: 1 });
  assert.equal(r.calls.length, 1);
  assert.equal(r.sp.snapshot().speakingNow, null);
  r.sp.setHeld(false);
  assert.deepEqual(r.played(), ["q1#0", "q1#0"]);
  r.last().h.onSpeaking?.();
  r.last().h.onEnd?.();
  assert.deepEqual(r.played(), ["q1#0", "q1#0", "q1#1"]);
});
check("voices off stops everything and takes nothing new; on again takes new answers only", () => {
  const r = rig();
  r.sp.enqueue({ question: "q1", index: 0 });
  r.sp.enqueue({ question: "q1", index: 1 });
  r.last().h.onSpeaking?.();
  r.sp.setEnabled(false);
  assert.equal(r.calls[0].stopped, true);
  assert.equal(r.sp.snapshot().queued, 0);
  assert.deepEqual(r.reports.at(-1), ["q1", false]);
  assert.equal(r.sp.enqueue({ question: "q2", index: 0 }), false);
  r.sp.setEnabled(true);
  assert.equal(r.sp.enqueue({ question: "q1", index: 2 }), false); // the answer stopped here stays stopped
  assert.equal(r.sp.enqueue({ question: "q3", index: 0 }), true);
});
check("stopAll (Esc, Leave, the case changed) clears the chip and the queue", () => {
  const r = rig();
  r.sp.enqueue({ question: "q1", index: 0 });
  r.last().h.onError?.({ name: "NotAllowedError" });
  r.sp.stopAll();
  assert.equal(r.sp.snapshot().blocked, false);
  assert.equal(r.sp.snapshot().queued, 0);
  r.sp.resume();
  assert.equal(r.calls.length, 1);
});
check("another voice of the page reading aloud: wait and try again, never cut it off", () => {
  let busy = true;
  const r = rig({ busy: () => busy });
  r.sp.enqueue({ question: "q1", index: 0 });
  assert.equal(r.calls.length, 0);
  assert.equal(r.timeouts.size, 1);
  r.sp.enqueue({ question: "q1", index: 1 });
  assert.equal(r.timeouts.size, 1); // one retry at a time
  r.fireTimeouts();
  assert.equal(r.calls.length, 0);
  busy = false;
  r.fireTimeouts();
  assert.deepEqual(r.played(), ["q1#0"]);
});
check("stopped by someone else on the page: the rest of that answer is not read here, the next answer is", () => {
  const r = rig();
  r.sp.enqueue({ question: "q1", index: 0 });
  r.sp.enqueue({ question: "q1", index: 1 });
  r.sp.enqueue({ question: "q2", index: 0 });
  r.last().h.onSpeaking?.();
  r.last().h.onStop?.(); // a read-aloud button or the microphone called stopSpeaking()
  assert.deepEqual(r.played(), ["q1#0", "q2#0"]);
  assert.deepEqual(r.reports, [["q1", true], ["q1", false]]);
  assert.equal(r.sp.enqueue({ question: "q1", index: 2 }), false);
});
check("a failing report is swallowed (thrown or rejected)", () => {
  for (const mode of ["throw", "reject"] as const) {
    const r = rig({ reportThrows: mode });
    r.sp.enqueue({ question: "q1", index: 0 });
    r.last().h.onSpeaking?.();
    r.tickIntervals();
    r.last().h.onEnd?.();
    assert.equal(r.reports.length, 3);
  }
});
check("handlers of a sentence already stopped are ignored", () => {
  const r = rig();
  r.sp.enqueue({ question: "q1", index: 0 });
  const old = r.last();
  r.sp.stopQuestion("q1");
  r.sp.enqueue({ question: "q2", index: 0 });
  old.h.onSpeaking?.();
  old.h.onEnd?.();
  assert.equal(r.sp.snapshot().speakingNow, null);
  assert.deepEqual(r.played(), ["q1#0", "q2#0"]);
  assert.equal(r.last().stopped, false);
});
check("the snapshot is the same object until something changes, and listeners hear each change", () => {
  const r = rig();
  let heard = 0;
  const off = r.sp.subscribe(() => { heard += 1; });
  const s0 = r.sp.snapshot();
  r.sp.setHeld(false);
  assert.equal(r.sp.snapshot(), s0);
  r.sp.enqueue({ question: "q1", index: 0 });
  r.last().h.onSpeaking?.();
  assert.notEqual(r.sp.snapshot(), s0);
  assert.ok(heard >= 1);
  off();
  const h = heard;
  r.last().h.onEnd?.();
  assert.equal(heard, h);
});
check("closed: nothing is taken; open again (strict mode): it works", () => {
  const r = rig();
  r.sp.enqueue({ question: "q1", index: 0 });
  r.last().h.onSpeaking?.();
  r.sp.close();
  assert.equal(r.calls[0].stopped, true);
  assert.deepEqual(r.reports.at(-1), ["q1", false]);
  assert.equal(r.intervals.size, 0);
  assert.equal(r.sp.enqueue({ question: "q2", index: 0 }), false);
  r.sp.open();
  assert.equal(r.sp.enqueue({ question: "q2", index: 0 }), true);
});
check("a speak that throws counts as an error and the queue goes on", () => {
  let first = true;
  const seen: string[] = [];
  const sp = new AgentSpeaker({
    speak: (item) => { seen.push(`${item.question}#${item.index}`); if (first) { first = false; throw new Error("no audio element"); } return { stop: () => {} }; },
    report: () => undefined,
  });
  sp.enqueue({ question: "q1", index: 0 });
  sp.enqueue({ question: "q1", index: 1 });
  assert.deepEqual(seen, ["q1#0", "q1#1"]);
});

console.log(`agentSpeaker: ${passed} checks passed`);
