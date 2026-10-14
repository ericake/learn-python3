import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

const KEY = "cwp.parentUnlockedAt";
const TTL_MS = 30 * 60 * 1000;

export function isParentUnlocked(): boolean {
  try {
    return Date.now() - Number(sessionStorage.getItem(KEY) || 0) < TTL_MS;
  } catch {
    return false;
  }
}

// 家长锁：两位数加法（孩子不识字，无法独立通过）
export default function ParentGate({ onPass }: { onPass: () => void }) {
  const nav = useNavigate();
  const [a, b] = useMemo(() => [11 + Math.floor(Math.random() * 30), 11 + Math.floor(Math.random() * 30)], []);
  const [val, setVal] = useState("");
  const [err, setErr] = useState(false);
  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (Number(val) === a + b) {
      try {
        sessionStorage.setItem(KEY, String(Date.now()));
      } catch {
        /* 忽略 */
      }
      onPass();
    } else {
      setErr(true);
      setVal("");
    }
  };
  return (
    <div className="parent gate">
      <form className="panel" onSubmit={submit}>
        <h2>家长验证</h2>
        <p>请计算：{a} + {b} = ?</p>
        <input inputMode="numeric" autoFocus value={val} onChange={(e) => setVal(e.target.value)} />
        {err && <p className="error">答案不对，请再试一次</p>}
        <div className="row">
          <button type="button" className="ghost" onClick={() => nav("/")}>返回</button>
          <button type="submit" className="primary">进入</button>
        </div>
      </form>
    </div>
  );
}
