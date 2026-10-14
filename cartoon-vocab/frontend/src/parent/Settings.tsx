import { useEffect, useState } from "react";

import { api } from "../lib/api";

export default function Settings() {
  const [nickname, setNickname] = useState("");
  const [accent, setAccent] = useState("en-GB");
  const [saved, setSaved] = useState(false);
  useEffect(() => {
    api.child().then((c) => {
      setNickname(c.nickname);
      setAccent(c.accent_pref);
    });
  }, []);
  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    await api.updateChild({ nickname, accent_pref: accent });
    setSaved(true);
  };
  return (
    <form className="panel stack" onSubmit={save}>
      <h2>设置</h2>
      <label>孩子昵称（仅家长端显示）<input value={nickname} onChange={(e) => { setNickname(e.target.value); setSaved(false); }} /></label>
      <label>发音口音
        <select value={accent} onChange={(e) => { setAccent(e.target.value); setSaved(false); }}>
          <option value="en-GB">英音（Peppa Pig 默认）</option>
          <option value="en-US">美音</option>
        </select>
      </label>
      <p className="muted">口音只影响之后新生成的剧集。孩子端所有语音均为英文。</p>
      <button className="primary">保存</button>
      {saved && <p className="ok">已保存</p>}
    </form>
  );
}
