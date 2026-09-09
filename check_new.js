const fs = require('fs');
const sent = JSON.parse(fs.readFileSync('/root/.openclaw/rss-sent.json', 'utf8'));
const articles = [
  { title: "iOS 27 Introduces New 'iPhone Handoff' Feature", url: "https://www.macrumors.com/2026/09/02/ios-27-iphone-handoff-feature/" },
  { title: "llm-gemini 0.34", url: "https://simonwillison.net/2026/Sep/2/llm-gemini/" },
  { title: "Claude's new system prompt really doesn't want to reproduce song lyrics", url: "https://simonwillison.net/2026/Sep/2/claudes-new-system-prompt/" },
  { title: "Pluralistic: Unpermissioned research (02 Sep 2026)", url: "https://pluralistic.net/2026/09/02/scrape-scrope-scrap/" },
  { title: "Quoting Rick Brewster", url: "https://simonwillison.net/2026/Sep/2/rick-brewster/" },
  { title: "Static Allocation, Constant Work", url: "https://matklad.github.io/2026/09/02/static-allocation-constant-work.html" },
  { title: "VC isn't VC anymore — understanding the rise of Cancer Capital", url: "https://anildash.com/2026/09/02/cancer-capital/" },
  { title: "How to protect yourself from workslop", url: "https://seangoedecke.com/how-to-protect-yourself-from-workslop/" }
];

const newArticles = articles.filter(a => !sent.includes(a.url));
console.log('Total articles today:', articles.length);
console.log('New (not in sent):', newArticles.length);
newArticles.forEach(a => console.log('NEW:', a.title));
articles.filter(a => sent.includes(a.url)).forEach(a => console.log('ALREADY SENT:', a.title));
