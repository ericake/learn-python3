// 点击工具栏图标（或按 Alt+S）切换开关，状态存在 storage 里，内容脚本自动响应
function showBadge(on) {
  chrome.action.setBadgeText({ text: on ? 'ON' : '' });
  chrome.action.setBadgeBackgroundColor({ color: '#d33' });
}

chrome.action.onClicked.addListener(async () => {
  const { enabled } = await chrome.storage.local.get('enabled');
  await chrome.storage.local.set({ enabled: !enabled });
  showBadge(!enabled);
});

chrome.runtime.onStartup.addListener(async () => {
  const { enabled } = await chrome.storage.local.get('enabled');
  showBadge(!!enabled);
});
