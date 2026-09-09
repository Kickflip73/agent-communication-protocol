const fs = require('fs');
const path = require('path');

const articles = [
  {
    title: "Gurman on OpenAI's Device: 'A Doughnut-Shaped Speaker That Costs Over $300'",
    link: "https://www.bloomberg.com/news/articles/2026-08-06/what-is-openai-s-device-a-doughnut-shaped-speaker-that-costs-over-300",
    content: `OpenAI 希望用户全天依赖这款智能音箱。它将类似 ChatGPT 手机端的语音模式，但采用更先进的模型实现类人的交互体验。设备会随时间学习用户习惯，从而定制对话内容并执行个性化操作。`,
    source: "bloomberg.com"
  },
  {
    title: "OpenAI Files 28-Page Motion to Dismiss Apple's Lawsuit (PDF Link)",
    link: "https://storage.courtlistener.com/recap/gov.uscourts.cand.474095/gov.uscourts.cand.474095.59.0.pdf",
    content: `OpenAI 提交了长达 28 页的动议，强硬驳斥苹果的商业机密诉讼。核心论点：苹果没有任何实质证据，其投诉无法对被告 Tan 构成任何盗用指控。措辞强硬，毫不含糊。`,
    source: "courtlistener.com"
  },
  {
    title: "Brendan Leonard: 'Do It 14,000 Times Slower With This One Trick'",
    link: "https://semi-rad.com/2026/08/do-it-14000-times-slower-with-this-one-trick/",
    content: `这篇漫画提醒我们反思：AI 究竟是在帮我们专注于热爱之事，还是在剥夺我们作为人类的本质体验？连"做三明治"这种日常小事也引发了深刻共鸣。`,
    source: "semi-rad.com"
  },
  {
    title: "datasette 1.0a38",
    link: "https://simonwillison.net/2026/Aug/6/datasette/",
    content: `Datasette 紧急发布安全更新，修复了 SQL 注入漏洞。该漏洞影响在同一数据库中同时提供公共和私有表、并通过 Datasette 权限系统控制访问的实例。管理员建议立即禁用相关权限或升级。`,
    source: "simonwillison.net"
  },
  {
    title: "datasette 0.65.3",
    link: "https://simonwillison.net/2026/Aug/6/datasette-2/",
    content: `Datasette 0.65.3 版本将 1.0a38 中的 SQL 注入安全修复向后移植到稳定分支。建议仍在使用旧版本的用户尽快升级。`,
    source: "simonwillison.net"
  },
  {
    title: "The Earnest Era Ends",
    link: "https://feed.tedium.co/link/15204/17404612/glen-hansard-passing-reflection",
    content: `Glen Hansard 上周离世，他的作品依然鲜活。这提醒我们，世界变化的速度远超我们的感知，一个时代的真诚与热忱正在悄然退场。`,
    source: "tedium.co"
  },
  {
    title: "Simon Willison on Technical Blogging",
    link: "https://simonwillison.net/2026/Aug/6/simon-willison-on-technical-blogging/",
    content: `知名开发者 Simon Willison 分享了他对技术博客的见解：为何开始写博客、持续写作的动力、以及写作带来的最意想不到的积极影响。对于想建立技术影响力的开发者值得一看。`,
    source: "simonwillison.net"
  },
  {
    title: "Add a Shortcut to Control Center to Open the Current App's Preferences in the Settings App",
    link: "https://x.com/SnazzyLabs/status/1969247088488624253",
    content: `Quinn Nelson 分享了一个 iOS 快捷指令：添加到控制中心后，可一键打开当前应用的设置偏好页面。解决了在 iOS 设置中层层翻找应用设置的痛点，实用小技巧。`,
    source: "x.com"
  },
  {
    title: "Canadian Man Pleads Guilty in Snowflake Extortions",
    link: "https://krebsonsecurity.com/2026/08/canadian-man-pleads-guilty-in-snowflake-extortions/",
    content: `26 岁的加拿大男子 Moucka 就 Snowflake 数据泄露案认罪。他被认为是 2024 年最具影响力的网络犯罪威胁者之一，承认入侵并勒索了 165 多家使用 Snowflake 的组织，还窃取了通话和短信记录。`,
    source: "krebsonsecurity.com"
  },
  {
    title: "BMW Executive in 2023: No Plans to Sell in-Vehicle Ads",
    link: "https://www.mediapost.com/publications/article/391876/bmw-exec-no-plans-to-sell-in-vehicle-ads.html",
    content: `2023 年宝马高级副总裁明确表示：尽管车内屏幕越来越大，但不会在车内投放广告，"广播广告已经够烦人了"。然而近日宝马车主却在仪表盘上看到了蜘蛛侠广告——打脸来得猝不及防。`,
    source: "mediapost.com"
  }
];

let msg = `🦞 RSS 日报

📅 2026-08-07 ⏰ 更新于 11:00

━━━━━━━━━━━━━━━━━━━━━━\n`;

articles.forEach((a, i) => {
  msg += `\n${i + 1}. 【${translateTitle(a.title)}】\n`;
  msg += `来源：${a.source}\n`;
  msg += `🔗 ${a.link}\n`;
  msg += `💡 要点：${a.content}\n`;
  msg += `━━━━━━━━━━━━━━━━━━━━━━\n`;
});

msg += `\n共 ${articles.length} 篇新文章`;

console.log(msg);

function translateTitle(title) {
  const translations = {
    "Gurman on OpenAI's Device: 'A Doughnut-Shaped Speaker That Costs Over $300'": "Gurman 爆料 OpenAI 硬件：一款售价超 300 美元的甜甜圈形音箱",
    "OpenAI Files 28-Page Motion to Dismiss Apple's Lawsuit (PDF Link)": "OpenAI 提交 28 页动议驳回苹果诉讼",
    "Brendan Leonard: 'Do It 14,000 Times Slower With This One Trick'": "Brendan Leonard：用这个小技巧，把速度放慢 14000 倍",
    "datasette 1.0a38": "Datasette 发布 1.0a38 版本",
    "datasette 0.65.3": "Datasette 发布 0.65.3 安全修复版",
    "The Earnest Era Ends": "真诚的时代结束了",
    "Simon Willison on Technical Blogging": "Simon Willison 谈技术博客写作",
    "Add a Shortcut to Control Center to Open the Current App's Preferences in the Settings App": "控制中心快捷指令：一键打开当前应用的设置偏好",
    "Canadian Man Pleads Guilty in Snowflake Extortions": "加拿大男子就 Snowflake 勒索案认罪",
    "BMW Executive in 2023: No Plans to Sell in-Vehicle Ads": "宝马 2023 年高管：无计划在车内投放广告"
  };
  return translations[title] || title;
}
