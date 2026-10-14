import { describe, expect, it } from "vitest";

import type { LessonPackage } from "../lib/api";
import { LessonRun, retrySteps } from "./lessonRun";

const pkg: LessonPackage = {
  lesson_id: "l",
  episode_id: "e",
  mode: "preview",
  accent: "en-GB",
  theme: { color: "#fff", sticker_key: "star" },
  praise: [],
  items: {
    a: { image: "ia", audio: "aa", type: "noun" },
    b: { image: "ib", audio: "ab", type: "noun" },
  },
  assets: {},
  steps: [
    { type: "intro", voice: [] },
    { type: "Q3", item: "a", prompt: ["aa"], options: ["ib", "ia"], answer: "ia" },
    { type: "Q3", item: "b", prompt: ["ab"], options: ["ib", "ia"], answer: "ib" },
    { type: "outro", voice: [], sticker: true },
  ],
};

describe("LessonRun", () => {
  it("records first-try correctness and reveals after two misses", () => {
    const run = new LessonRun(pkg, () => 0.1);
    run.next(); // -> Q3 a
    expect(run.answer("ib")).toBe("tryAgain");
    expect(run.answer("ib")).toBe("reveal");
    run.next(); // -> Q3 b
    expect(run.answer("ib")).toBe("correct");
    expect(run.attempts.map((a) => [a.vocab_item_id, a.is_first_try, a.is_correct])).toEqual([
      ["a", true, false],
      ["a", false, false],
      ["b", true, true],
    ]);
  });

  it("inserts a retry question for wrong items before the outro", () => {
    const run = new LessonRun(pkg, () => 0.1);
    run.next();
    run.answer("ib");
    run.next();
    run.answer("ib");
    run.next();
    expect(run.step?.type).toBe("Q2");
    expect(run.step && "item" in run.step && run.step.item).toBe("a");
    run.answer("ia");
    run.next();
    expect(run.step?.type).toBe("outro");
    run.next();
    expect(run.done).toBe(true);
  });

  it("retry steps need a distractor", () => {
    const single = { ...pkg, items: { a: pkg.items.a } };
    expect(retrySteps(single, ["a"])).toEqual([]);
  });
});
