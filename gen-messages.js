const fs = require('fs');
const articles = JSON.parse(fs.readFileSync('/root/.openclaw/workspace/articles.json', 'utf8'));

const newArticles = articles;

function getDomain(url) {
  try {
    const u = new URL(url);
    return u.hostname.replace(/^www\./, '');
  } catch { return url; }
}

function translateTitle(title) {
  return title
    .replace(/Show HN:/gi, 'Show HN：')
    .replace(/\[video\]/gi, '[视频]')
    .replace(/\[YouTube\]/gi, '[YouTube]');
}

function summarize(title) {
  const lower = title.toLowerCase();
  if (lower.includes('show hn')) return 'Hacker News社区用户分享的新项目或工具。';
  if (lower.includes('ai ') || lower.includes(' ai') || lower.includes('agent')) return '探讨AI技术在相关领域的最新应用与发展。';
  if (lower.includes('coding') || lower.includes('programming')) return '关于编程实践、工具或开发方法论的最新内容。';
  if (lower.includes('drone')) return '无人机技术及其在现代战争中的应用讨论。';
  if (lower.includes('bubble')) return '对AI经济泡沫和股市风险的深度分析。';
  if (lower.includes('nvidia')) return 'NVIDIA硬件产品的价格策略调整。';
  if (lower.includes('yubikey')) return 'YubiKey安全密钥的新版本发布与功能更新。';
  if (lower.includes('openai')) return 'OpenAI相关的最新动态或安全事件。';
  if (lower.includes('trump')) return '特朗普政府的政策声明或行政决策。';
  if (lower.includes('cloudflare')) return 'Cloudflare产品服务的正式发布。';
  if (lower.includes('postgres')) return 'PostgreSQL数据库性能优化的技术探讨。';
  if (lower.includes('redis')) return 'Redis客户端使用中发现的内存安全问题。';
  if (lower.includes('kubernetes')) return 'Kubernetes集群管理工具或平台介绍。';
  if (lower.includes('snowflake')) return 'Snowflake数据库的隐藏行为或技术细节。';
  if (lower.includes('kimi')) return 'Kimi K3大模型在基准测试中的表现。';
  if (lower.includes('github')) return 'GitHub相关工具或工作流的改进方案。';
  if (lower.includes('video')) return '视频形式的技术讲解或历史回顾。';
  if (lower.includes('wikipedia')) return 'Wikipedia上的知识条目或历史回顾。';
  if (lower.includes('china') || lower.includes('chinese')) return '关于中国科技或国际关系的讨论。';
  if (lower.includes('tariff')) return '关税政策对相关行业的影响分析。';
  if (lower.includes('security') || lower.includes('hack')) return '网络安全事件或漏洞披露。';
  if (lower.includes('nuclear')) return '核能技术在新能源领域的创新应用。';
  if (lower.includes('oracle')) return 'Oracle公司财务状况或信用评级变化。';
  if (lower.includes('tesla')) return '特斯拉新产品或商业动态。';
  if (lower.includes('film') || lower.includes('movie')) return 'AI在电影制作领域的应用探索。';
  if (lower.includes('architecture')) return '建筑设计与文化特征的分析讨论。';
  if (lower.includes('gravitational')) return '引力波发现历程的科学回顾。';
  if (lower.includes('voting')) return '选民登记系统的错误与选举安全问题。';
  if (lower.includes('anime')) return 'AI生成动画的创作流程与技术。';
  if (lower.includes('app store')) return 'AI生成应用涌入App Store的现象。';
  if (lower.includes('license plate')) return '自动车牌识别系统的位置追踪工具。';
  if (lower.includes('hydrogen')) return '核热制氢技术的全球首创突破。';
  if (lower.includes('genetics')) return '基因风险评分工具中的种族偏差问题。';
  if (lower.includes('3d environment')) return '可编辑3D环境生成用于机器人训练。';
  if (lower.includes('tokeniz')) return '高性能分词器的技术发布。';
  if (lower.includes('leetcode')) return 'LeetCode刷题的最佳实践方法。';
  if (lower.includes('counterfeit')) return '伪钞制造者的追踪报道。';
  if (lower.includes('reef')) return '大堡礁生态变化与UNESCO保护名单争议。';
  if (lower.includes('boeing') || lower.includes('airbus')) return '波音与空客的贸易争端升级。';
  if (lower.includes('prediction market')) return '预测市场内幕交易问题的深度分析。';
  if (lower.includes('erratabench')) return '大语言模型在错误纠正基准测试中的表现。';
  if (lower.includes('flaky test')) return '不稳定测试暴露的Redis客户端内存安全问题。';
  if (lower.includes('multi-agent')) return '多智能体编码工作空间的运行指南。';
  if (lower.includes('vibe') && lower.includes('coding')) return 'AI Vibe Coding应用大量涌入苹果App Store。';
  return '值得关注的技术或行业动态。';
}

const batches = [];
const batchSize = 10;
for (let i = 0; i < newArticles.length; i += batchSize) {
  batches.push(newArticles.slice(i, i + batchSize));
}

const messages = batches.map((batch, idx) => {
  let text = '';
  if (idx === 0) {
    text += '🦞 RSS 日报\n\n📅 2026-07-22 ⏰ 更新于 12:00\n\n━━━━━━━━━━━━━━━━━━━━━━\n\n';
  } else {
    text += '🦞 RSS 日报（续' + idx + '）\n\n━━━━━━━━━━━━━━━━━━━━━━\n\n';
  }

  batch.forEach((a, i) => {
    const num = idx * batchSize + i + 1;
    const title = translateTitle(a.title);
    const domain = getDomain(a.link);
    const summary = summarize(a.title);
    text += num + '. 【' + title + '】\n来源：' + domain + '\n🔗 ' + a.link + '\n💡 要点：' + summary + '\n\n━━━━━━━━━━━━━━━━━━━━━━\n\n';
  });

  if (idx === batches.length - 1) {
    text += '共 ' + newArticles.length + ' 篇新文章';
  }

  return text;
});

fs.writeFileSync('/root/.openclaw/workspace/messages.json', JSON.stringify(messages, null, 2));
console.log('Generated ' + messages.length + ' messages');
