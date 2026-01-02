// popup.js
document.getElementById('scanBtn').addEventListener('click', async () => {
  const status = document.getElementById('status');
  status.innerText = "正在截图并发送至 AI...";

  // 截取当前标签页
  chrome.tabs.captureVisibleTab(null, {format: 'png'}, async (dataUrl) => {
    try {
      // ⚠️ 替换下方的 URL 为你刚从 GCP 获取的 URL
      // 注意：一定要保留后面的 /analyze
      const response = await fetch('https://stock-scanner-service-faxxxlu5da-uc.a.run.app/analyze', {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json'，
          'X-Internal-Key': 'my_private_stock_key_2026'
        },
        body: JSON.stringify({ image: dataUrl })
      });

      const res = await response.json();
      
      if (res.status === "success") {
        status.innerText = "分析成功！结果已存入数据库。";
        console.log(res.result);
      } else {
        status.innerText = "AI 分析失败: " + res.message;
      }
    } catch (e) {
      status.innerText = "网络请求错误: " + e.message;
    }
  });
});