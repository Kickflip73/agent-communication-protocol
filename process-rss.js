const fs = require('fs');

// Read rss-sent.json
const sentPath = '/root/.openclaw/rss-sent.json';
let sentUrls = [];
try {
  sentUrls = JSON.parse(fs.readFileSync(sentPath, 'utf8'));
} catch (e) {
  sentUrls = [];
}

// Today's articles from rss-agent-viewer output
const rssOutput = `
1. ACXD
   https://chadnauseam.com/reference/ACXD
   Published: 6/8/2026  ○

2. Astral Codex Ten
   https://chadnauseam.com/reference/Astral+Codex+Ten
   Published: 6/8/2026  ○

3. Rust
   https://chadnauseam.com/reference/Rust
   Published: 6/8/2026  ○

4. a-better-lerp-for-smooth-movement
   https://chadnauseam.com/coding/gamedev/a-better-lerp-for-smooth-movement
   Published: 6/8/2026  ○

5. a-hackers-case-for-crypto
   https://chadnauseam.com/coding/cryptocurrency/a-hackers-case-for-crypto
   Published: 6/8/2026  ○

6. anime-recommendations
   https://chadnauseam.com/anime/anime-recommendations
   Published: 6/8/2026  ○

7. automated-testing-in-bevy
   https://chadnauseam.com/coding/gamedev/automated-testing-in-bevy
   Published: 6/8/2026  ○

8. calculator-app
   https://chadnauseam.com/coding/random/calculator-app
   Published: 6/8/2026  ○

9. chewier-foods-for-children
   https://chadnauseam.com/random/chewier-foods-for-children
   Published: 6/8/2026  ○

10. cool-people
   https://chadnauseam.com/random/cool/cool-people
   Published: 6/8/2026  ○

11. cool-stickers
   https://chadnauseam.com/random/cool/cool-stickers
   Published: 6/8/2026  ○

12. error-driven-development
   https://chadnauseam.com/coding/tips/error-driven-development
   Published: 6/8/2026  ○

13. faq
   https://chadnauseam.com/faq
   Published: 6/8/2026  ○

14. floating-points-between-zero-and-one
   https://chadnauseam.com/coding/random/floating-points-between-zero-and-one
   Published: 6/8/2026  ○

15. four-issues-facing-fp
   https://chadnauseam.com/coding/pltd/four-issues-facing-fp
   Published: 6/8/2026  ○

16. git-collapse-commits
   https://chadnauseam.com/coding/tips/git-collapse-commits
   Published: 6/8/2026  ○

17. how-i-think-of-the-expression-problem
   https://chadnauseam.com/coding/pltd/how-i-think-of-the-expression-problem
   Published: 6/8/2026  ○

18. how-side-effects-work-in-fp
   https://chadnauseam.com/coding/random/how-side-effects-work-in-fp
   Published: 6/8/2026  ○

19. impro-by-keith-johnstone
   https://chadnauseam.com/books/impro-by-keith-johnstone
   Published: 6/8/2026  ○

20. levers-in-the-brain
   https://chadnauseam.com/coding/random/levers-in-the-brain
   Published: 6/8/2026  ○

21. my-new-rust-binary-search
   https://chadnauseam.com/coding/random/my-new-rust-binary-search
   Published: 6/8/2026  ○

22. my-rustfmt-toml
   https://chadnauseam.com/coding/tips/my-rustfmt-toml
   Published: 6/8/2026  ○

23. openai-structured-outputs-are-really-useful
   https://chadnauseam.com/coding/ai/openai-structured-outputs-are-really-useful
   Published: 6/8/2026  ○

24. semaglutide-has-changed-the-world
   https://chadnauseam.com/random/semaglutide-has-changed-the-world
   Published: 6/8/2026  ○

25. setting-up-a-media-server
   https://chadnauseam.com/coding/random/setting-up-a-media-server
   Published: 6/8/2026  ○

26. solving-macro
   https://chadnauseam.com/economics/solving-macro
   Published: 6/8/2026  ○

27. the-game-design-of-math-academy
   https://chadnauseam.com/coding/gamedev/the-game-design-of-math-academy
   Published: 6/8/2026  ○

28. the-good-and-bad-of-cpp-as-a-rust-dev
   https://chadnauseam.com/coding/pltd/the-good-and-bad-of-cpp-as-a-rust-dev
   Published: 6/8/2026  ○

29. whats-wrong-with-a-for-loop
   https://chadnauseam.com/coding/tips/whats-wrong-with-a-for-loop
   Published: 6/8/2026  ○

30. writing-advice
   https://chadnauseam.com/advice/writing-advice
   Published: 6/8/2026  ○

31. Mux — Video for Developers
   https://www.mux.com/?utm_campaign=fireball&utm_source=DF
   Published: 6/8/2026  ○

32. ★ SwiftUI Only Makes It Easy to Develop Bad Apps
   https://daringfireball.net/2026/06/swiftui_only_makes_it_easy_to_develop_bad_apps
   Published: 6/8/2026  ○

33. Alberto Romero on Apple's AI Spending
   https://www.thealgorithmicbridge.com/p/what-apple-knows-about-ai-that-silicon
   Published: 6/8/2026  ○

34. Doing nothing at work
   https://seangoedecke.com/doing-nothing-at-work/
   Published: 6/8/2026  ○
`;

// Parse articles
const lines = rssOutput.trim().split('\n');
const articles = [];
let currentArticle = null;

for (const line of lines) {
  const numMatch = line.match(/^(\d+)\.\s+(.+)/);
  if (numMatch) {
    if (currentArticle) articles.push(currentArticle);
    currentArticle = {
      num: parseInt(numMatch[1]),
      title: numMatch[2].trim()
    };
  } else if (line.trim().startsWith('https://')) {
    if (currentArticle) currentArticle.url = line.trim();
  }
}
if (currentArticle) articles.push(currentArticle);

// Filter out sent URLs
const newArticles = articles.filter(a => !sentUrls.includes(a.url));

console.log(`Total articles today: ${articles.length}`);
console.log(`Already sent: ${articles.length - newArticles.length}`);
console.log(`New articles: ${newArticles.length}`);

if (newArticles.length === 0) {
  console.log('No new articles to send.');
  process.exit(0);
}

// Get domain from URL
function getDomain(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch (e) {
    return url;
  }
}

// Output article info for message generation
newArticles.forEach(a => {
  console.log(`\n--- Article ${a.num} ---`);
  console.log(`Title: ${a.title}`);
  console.log(`URL: ${a.url}`);
  console.log(`Domain: ${getDomain(a.url)}`);
});

// Save new articles URLs for later
fs.writeFileSync('/tmp/new-articles.json', JSON.stringify(newArticles, null, 2));
