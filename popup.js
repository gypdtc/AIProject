async function captureAndAnalyze() {
  // 1. 截取当前标签页的图片
  chrome.tabs.captureVisibleTab(null, {format: 'png'}, async (dataUrl) => {
    // 2. 将图片发送到你的 GCP 后端
    const response = await fetch('https://你的-gcp-cloud-run-url/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ image: dataUrl })
    });
    const result = await response.json();
    alert("AI 分析完成: " + JSON.stringify(result));
  });
}