const fs = require("fs");

const sentPath = "/root/.openclaw/rss-sent.json";
let sent = [];
try {
  sent = JSON.parse(fs.readFileSync(sentPath, "utf-8"));
} catch(e) {}

// Articles from rss-agent-viewer output with Published: 8/15/2026 (items 1-32 in the output)
const todayArticles = [
  { title: "ACXD", link: "https://chadnauseam.com/reference/ACXD" },
  { title: "Astral Codex Ten", link: "https://chadnauseam.com/reference/Astral+Codex+Ten" },
  { title: "Rust", link: "https://chadnauseam.com/reference/Rust" },
  { title: "a-better-lerp-for-smooth-movement", link: "https://chadnauseam.com/coding/gamedev/a-better-lerp-for-smooth-movement" },
  { title: "a-hackers-case-for-crypto", link: "https://chadnauseam.com/coding/cryptocurrency/a-hackers-case-for-crypto" },
  { title: "anime-recommendations", link: "https://chadnauseam.com/anime/anime-recommendations" },
  { title: "automated-testing-in-bevy", link: "https://chadnauseam.com/coding/gamedev/automated-testing-in-bevy" },
  { title: "calculator-app", link: "https://chadnauseam.com/coding/random/calculator-app" },
  { title: "chewier-foods-for-children", link: "https://chadnauseam.com/random/chewier-foods-for-children" },
  { title: "cool-people", link: "https://chadnauseam.com/random/cool/cool-people" },
  { title: "cool-stickers", link: "https://chadnauseam.com/random/cool/cool-stickers" },
  { title: "error-driven-development", link: "https://chadnauseam.com/coding/tips/error-driven-development" },
  { title: "faq", link: "https://chadnauseam.com/faq" },
  { title: "floating-points-between-zero-and-one", link: "https://chadnauseam.com/coding/random/floating-points-between-zero-and-one" },
  { title: "four-issues-facing-fp", link: "https://chadnauseam.com/coding/pltd/four-issues-facing-fp" },
  { title: "git-collapse-commits", link: "https://chadnauseam.com/coding/tips/git-collapse-commits" },
  { title: "how-i-think-of-the-expression-problem", link: "https://chadnauseam.com/coding/pltd/how-i-think-of-the-expression-problem" },
  { title: "how-side-effects-work-in-fp", link: "https://chadnauseam.com/coding/random/how-side-effects-work-in-fp" },
  { title: "impro-by-keith-johnstone", link: "https://chadnauseam.com/books/impro-by-keith-johnstone" },
  { title: "levers-in-the-brain", link: "https://chadnauseam.com/coding/random/levers-in-the-brain" },
  { title: "my-new-rust-binary-search", link: "https://chadnauseam.com/coding/random/my-new-rust-binary-search" },
  { title: "my-rustfmt-toml", link: "https://chadnauseam.com/coding/tips/my-rustfmt-toml" },
  { title: "openai-structured-outputs-are-really-useful", link: "https://chadnauseam.com/coding/ai/openai-structured-outputs-are-really-useful" },
  { title: "semaglutide-has-changed-the-world", link: "https://chadnauseam.com/random/semaglutide-has-changed-the-world" },
  { title: "setting-up-a-media-server", link: "https://chadnauseam.com/coding/random/setting-up-a-media-server" },
  { title: "solving-macro", link: "https://chadnauseam.com/economics/solving-macro" },
  { title: "the-game-design-of-math-academy", link: "https://chadnauseam.com/coding/gamedev/the-game-design-of-math-academy" },
  { title: "the-good-and-bad-of-cpp-as-a-rust-dev", link: "https://chadnauseam.com/coding/pltd/the-good-and-bad-of-cpp-as-a-rust-dev" },
  { title: "whats-wrong-with-a-for-loop", link: "https://chadnauseam.com/coding/tips/whats-wrong-with-a-for-loop" },
  { title: "writing-advice", link: "https://chadnauseam.com/advice/writing-advice" },
  { title: "Northern Gannet", link: "https://simonwillison.net/2026/Aug/15/sighting-391300422/" },
  { title: "Training a Reinforcement Learning Model to Play Bonk.io", link: "https://blog.pixelmelt.dev/training-a-reinforcement-learning-model-to-play-bonk-io/" },
];

const newArticles = todayArticles.filter(a => !sent.includes(a.link));
console.log(JSON.stringify({
  totalToday: todayArticles.length,
  sentCount: todayArticles.length - newArticles.length,
  newCount: newArticles.length,
  newArticles
}, null, 2));
