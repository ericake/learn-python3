// 一节课的进度与判题逻辑（技术文档 7.2），与界面无关，便于单元测试。

import type { Attempt, ChoiceStep, LessonPackage, Step } from "../lib/api";

export type Outcome = "correct" | "tryAgain" | "reveal";

export function uid(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID().replace(/-/g, "");
  return Math.random().toString(16).slice(2) + Date.now().toString(16);
}

export function isChoice(step: Step): step is ChoiceStep {
  return "options" in step;
}

/** 错题回炉：为答错的条目生成二选一，干扰项取本节其他条目。 */
export function retrySteps(pkg: LessonPackage, wrongIds: string[], rand: () => number = Math.random): ChoiceStep[] {
  const ids = Object.keys(pkg.items);
  const out: ChoiceStep[] = [];
  for (const id of wrongIds) {
    const it = pkg.items[id];
    if (!it) continue;
    const others = ids.filter((o) => o !== id && pkg.items[o].image !== it.image);
    if (!others.length) continue;
    const d = pkg.items[others[Math.floor(rand() * others.length)]];
    const options = rand() < 0.5 ? [it.image, d.image] : [d.image, it.image];
    out.push({ type: "Q2", item: id, prompt: ["sys:where_is", it.audio], options, answer: it.image });
  }
  return out;
}

export class LessonRun {
  steps: Step[];
  index = 0;
  attempts: Attempt[] = [];
  private wrong = new Set<string>();
  private triesOnStep = 0;
  private stepStartedAt = Date.now();
  private retriesAdded = false;

  constructor(public pkg: LessonPackage, private rand: () => number = Math.random) {
    this.steps = [...pkg.steps];
  }

  get step(): Step | undefined {
    return this.steps[this.index];
  }

  get progress(): number {
    return this.steps.length ? this.index / this.steps.length : 0;
  }

  get done(): boolean {
    return this.index >= this.steps.length;
  }

  startStep() {
    this.triesOnStep = 0;
    this.stepStartedAt = Date.now();
  }

  /** 记录一次点选并返回反馈类型。第一次答错允许再选一次，第二次答错直接揭晓答案。 */
  answer(chosen: string): Outcome {
    const step = this.step;
    if (!step || !isChoice(step)) throw new Error("not a choice step");
    const correct = chosen === step.answer;
    const first = this.triesOnStep === 0;
    this.triesOnStep++;
    this.attempts.push({
      client_attempt_id: uid(),
      vocab_item_id: step.item,
      question_type: step.type,
      option_ids: step.options,
      chosen_id: chosen,
      is_correct: correct,
      is_first_try: first,
      latency_ms: Date.now() - this.stepStartedAt,
    });
    if (correct) return "correct";
    this.wrong.add(step.item);
    return this.triesOnStep >= 2 ? "reveal" : "tryAgain";
  }

  next() {
    this.index++;
    // 主体题目做完、到结束页之前，插入错题回炉（只插一次）
    const s = this.step;
    if (!this.retriesAdded && s && s.type === "outro") {
      this.retriesAdded = true;
      const extra = retrySteps(this.pkg, [...this.wrong], this.rand);
      this.steps.splice(this.index, 0, ...extra);
    }
    this.startStep();
  }
}
