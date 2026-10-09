// 在视频画面下方盖一块黑条遮住字幕。
// 遮挡条可上下拖动调整位置，鼠标滚轮调整高度；位置和高度会被记住。
(() => {
  let enabled = false;
  let top = 0.78;    // 遮挡条上边缘在视频高度中的比例
  let height = 0.14; // 遮挡条高度占视频高度的比例

  const mask = document.createElement('div');
  mask.title = '拖动调整位置，滚轮调整高度';
  Object.assign(mask.style, {
    position: 'fixed',
    zIndex: 2147483647,
    background: 'rgba(0,0,0,0.92)',
    cursor: 'ns-resize',
    display: 'none',
  });

  // 找到页面上最大的正在显示的视频
  function findVideo() {
    let best = null, bestArea = 0;
    for (const v of document.querySelectorAll('video')) {
      const r = v.getBoundingClientRect();
      const area = r.width * r.height;
      if (area > bestArea) { best = v; bestArea = area; }
    }
    return best;
  }

  function update() {
    const video = enabled && findVideo();
    if (!video) { mask.style.display = 'none'; return; }
    // 全屏时必须挂在全屏元素里才能显示
    const host = document.fullscreenElement || document.body;
    if (mask.parentNode !== host) host.appendChild(mask);
    const r = video.getBoundingClientRect();
    Object.assign(mask.style, {
      display: 'block',
      left: r.left + 'px',
      width: r.width + 'px',
      top: r.top + r.height * top + 'px',
      height: r.height * height + 'px',
    });
  }

  function loop() {
    update();
    requestAnimationFrame(loop);
  }

  // 拖动：上下移动遮挡条
  mask.addEventListener('mousedown', (e) => {
    e.preventDefault();
    e.stopPropagation();
    const video = findVideo();
    if (!video) return;
    const h = video.getBoundingClientRect().height;
    const startY = e.clientY, startTop = top;
    const move = (ev) => {
      top = Math.min(1 - height, Math.max(0, startTop + (ev.clientY - startY) / h));
    };
    const up = () => {
      removeEventListener('mousemove', move, true);
      removeEventListener('mouseup', up, true);
      chrome.storage.local.set({ top });
    };
    addEventListener('mousemove', move, true);
    addEventListener('mouseup', up, true);
  });
  // 阻止点击穿透到播放器（避免误触暂停）
  mask.addEventListener('click', (e) => e.stopPropagation());
  mask.addEventListener('dblclick', (e) => e.stopPropagation());

  // 滚轮：调整高度
  mask.addEventListener('wheel', (e) => {
    e.preventDefault();
    e.stopPropagation();
    height = Math.min(0.6, Math.max(0.03, height + (e.deltaY < 0 ? 0.01 : -0.01)));
    top = Math.min(top, 1 - height);
    chrome.storage.local.set({ height, top });
  }, { passive: false });

  chrome.storage.local.get(['enabled', 'top', 'height'], (s) => {
    enabled = !!s.enabled;
    if (typeof s.top === 'number') top = s.top;
    if (typeof s.height === 'number') height = s.height;
    loop();
  });

  chrome.storage.onChanged.addListener((c) => {
    if (c.enabled) enabled = !!c.enabled.newValue;
    if (c.top) top = c.top.newValue;
    if (c.height) height = c.height.newValue;
  });
})();
