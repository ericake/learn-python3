import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";

import ParentGate, { isParentUnlocked } from "./ParentGate";

export default function ParentLayout() {
  const [ok, setOk] = useState(isParentUnlocked());
  if (!ok) return <ParentGate onPass={() => setOk(true)} />;
  return (
    <div className="parent">
      <header className="topbar">
        <strong>动画词卡 · 家长端</strong>
        <nav>
          <NavLink to="/parent" end>剧集</NavLink>
          <NavLink to="/parent/reports">学习报告</NavLink>
          <NavLink to="/parent/settings">设置</NavLink>
          <NavLink to="/">回到孩子端</NavLink>
        </nav>
      </header>
      <main><Outlet /></main>
    </div>
  );
}
