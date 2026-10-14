import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { api, type ChoiceStep, type LessonPackage, type Step } from "../lib/api";
import { audio, chime, sleep } from "../lib/audio";
import { flushPending, queueAttempts, queueFinish } from "../lib/offline";
import { stickerEmoji } from "../lib/stickers";
import { useLongPress } from "../lib/useLongPress";
import { isChoice, LessonRun } from "../player/lessonRun";

type Feedback = { kind: "correct" | "wrong" | "reveal"; option: string } | null;

const IDLE_REPLAY_MS = 10_000;
const IDLE_HINT_MS = 30_000;

// 课程播放器（PRD F7/F8/F10/F11，技术文档 7.2）。孩子端不出现任何文字。
export default function Player() {
  const { episodeId = "", mode = "preview" } = useParams();
  const nav = useNavigate();
  const run = useRef<LessonRun | null>(null);
  const sessionId = useRef<string | null>(null);
  const [pkg, setPkg] = useState<LessonPackage | null>(null);
  const [step, setStep] = useState<Step | undefined>();
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [feedback, setFeedback] = useState<Feedback>(null);
  const [locked, setLocked] = useState(false);
  const [hint, setHint] = useState(false);
  const [canNext, setCanNext] = useState(false);
  const [warmupIdx, setWarmupIdx] = useState(0);
  const [sticker, setSticker] = useState<string | null>(null);
  const idleTimers = useRef<number[]>([]);

  // ---------- 加载 ----------
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const p = mode === "spaced" ? await api.spacedLesson() : await api.lesson(episodeId, mode as "preview" | "review");
        if (cancelled) return;
        audio.accent = p.accent;
        audio.register(p.assets);
        await audio.preload(Object.keys(p.assets).filter((k) => p.assets[k].kind === "audio"));
        // 预加载图片
        await Promise.all(Object.values(p.assets).filter((a) => a.kind === "image" && a.url).map((a) =>
          new Promise<void>((r) => { const img = new Image(); img.onload = img.onerror = () => r(); img.src = a.url!; })));
        try {
          sessionId.current = (await api.startSession(p.episode_id, p.mode)).id;
        } catch {
          sessionId.current = null; // 离线：照常上课，只是不记录
        }
        run.current = new LessonRun(p);
        run.current.startStep();
        setPkg(p);
        setStep(run.current.step);
        setLoading(false);
      } catch {
        if (!cancelled) setFailed(true);
      }
    })();
    return () => {
      cancelled = true;
      audio.stop();
    };
  }, [episodeId, mode]);

  const clearIdle = () => {
    idleTimers.current.forEach((t) => window.clearTimeout(t));
    idleTimers.current = [];
  };

  const saveAttempts = useCallback(() => {
    const r = run.current;
    if (!r || !sessionId.current) return;
    queueAttempts(sessionId.current, r.attempts.splice(0));
  }, []);

  const exit = useCallback(() => {
    clearIdle();
    audio.stop();
    saveAttempts();
    flushPending();
    nav("/");
  }, [nav, saveAttempts]);

  const advance = useCallback(() => {
    const r = run.current;
    if (!r) return;
    clearIdle();
    setFeedback(null);
    setLocked(false);
    setHint(false);
    setCanNext(false);
    setWarmupIdx(0);
    r.next();
    setStep(r.step);
  }, []);

  const armIdle = useCallback((prompt: string[]) => {
    clearIdle();
    idleTimers.current.push(window.setTimeout(() => audio.play(prompt), IDLE_REPLAY_MS));
    idleTimers.current.push(window.setTimeout(() => setHint(true), IDLE_HINT_MS));
  }, []);

  // ---------- 每一步进入时 ----------
  useEffect(() => {
    if (!step || !pkg) return;
    let alive = true;
    (async () => {
      switch (step.type) {
        case "intro": {
          await sleep(400);
          await audio.play(step.voice);
          if (alive) { await sleep(500); advance(); }
          break;
        }
        case "Q1": {
          await sleep(300);
          await audio.play(step.audio, 600);
          if (alive) setCanNext(true);
          break;
        }
        case "warmup": {
          for (let i = 0; i < step.items.length && alive; i++) {
            setWarmupIdx(i);
            await audio.play([step.items[i].audio]);
            await sleep(1200);
          }
          if (alive) advance();
          break;
        }
        case "outro": {
          saveAttempts();
          const sid = sessionId.current;
          let key = pkg.theme.sticker_key;
          if (sid) {
            await flushPending([sid]);
            try {
              key = (await api.finish(sid)).sticker_key;
            } catch {
              queueFinish(sid);
            }
          }
          if (!alive) return;
          setSticker(key);
          chime("good");
          await audio.play(step.voice);
          break;
        }
        default: {
          await sleep(300);
          await audio.play(step.prompt);
          if (alive) armIdle(step.prompt);
        }
      }
    })();
    return () => {
      alive = false;
      clearIdle();
    };
  }, [step, pkg, advance, armIdle, saveAttempts]);

  // ---------- 点选 ----------
  const choose = async (s: ChoiceStep, option: string) => {
    const r = run.current;
    if (!r || locked || !pkg) return;
    clearIdle();
    setHint(false);
    const outcome = r.answer(option);
    const itemAudio = pkg.items[s.item]?.audio;
    setLocked(true);
    if (outcome === "correct") {
      setFeedback({ kind: "correct", option });
      chime("good");
      const praise = pkg.praise[Math.floor(Math.random() * pkg.praise.length)];
      await audio.play([praise, itemAudio].filter(Boolean) as string[]);
      await sleep(500);
      advance();
    } else if (outcome === "tryAgain") {
      setFeedback({ kind: "wrong", option });
      chime("soft");
      await sleep(700);
      setFeedback(null);
      setLocked(false);
      await audio.play(s.prompt);
      armIdle(s.prompt);
    } else {
      setFeedback({ kind: "reveal", option: s.answer });
      chime("soft");
      await audio.play([itemAudio, itemAudio].filter(Boolean) as string[], 500);
      await sleep(500);
      advance();
    }
  };

  const home = useLongPress(exit, 2000);
  const imgUrl = (id: string) => pkg?.assets[id]?.url;

  if (failed) {
    return (
      <div className="child-screen center">
        <button className="waiting" aria-label="back" onClick={() => nav("/")}>📡</button>
      </div>
    );
  }
  if (loading || !pkg) {
    return <div className="child-screen center"><div className="loader">🐷</div></div>;
  }

  const r = run.current!;
  return (
    <div className="child-screen player" style={{ ["--theme" as string]: pkg.theme.color }}>
      <button className="corner-btn left" aria-label="home" {...home.bind}>
        <span className={home.pressing ? "hold-ring active" : "hold-ring"} />🏠
      </button>
      <div className="progress"><div style={{ width: `${Math.round(r.progress * 100)}%` }} /></div>

      {step?.type === "intro" && <div className="hero bounce-in">🎬</div>}

      {step?.type === "Q1" && (
        <div className="q1">
          <button className="card big pop-in" aria-label="picture" onClick={() => audio.play(step.audio, 600)}>
            <img src={imgUrl(step.image)} alt="" draggable={false} />
          </button>
          <button className={canNext ? "next-btn show" : "next-btn"} aria-label="next" onClick={advance}>➡️</button>
        </div>
      )}

      {step?.type === "warmup" && step.items[warmupIdx] && (
        <div className="q1">
          <div className="card big flash" key={warmupIdx}>
            <img src={imgUrl(step.items[warmupIdx].image)} alt="" draggable={false} />
          </div>
        </div>
      )}

      {step && isChoice(step) && (
        <div className="choice">
          <button className="speaker" aria-label="listen again" onClick={() => audio.play(step.prompt)}>
            {step.type === "Q4" ? "💬" : "🔊"}
          </button>
          <div className={`options n${step.options.length}`}>
            {step.options.map((o) => {
              const fb = feedback?.option === o ? feedback.kind : null;
              const glow = (feedback?.kind === "reveal" && o === step.answer) || (hint && o === step.answer);
              return (
                <button
                  key={o}
                  className={`card option ${fb === "correct" ? "bounce" : ""} ${fb === "wrong" ? "shake" : ""} ${glow ? "glow" : ""}`}
                  aria-label="choice"
                  onClick={() => choose(step, o)}
                >
                  <img src={imgUrl(o)} alt="" draggable={false} />
                </button>
              );
            })}
          </div>
        </div>
      )}

      {step?.type === "outro" && (
        <div className="outro">
          <div className="sticker-award bounce-in">{sticker ? stickerEmoji(sticker) : "⭐"}</div>
          <div className="confetti" aria-hidden>🎉 ✨ 🎊 ✨ 🎉</div>
          <button className="next-btn show" aria-label="home" onClick={() => { advance(); nav("/"); }}>🏠</button>
        </div>
      )}
    </div>
  );
}
