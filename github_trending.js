(function(){
const repos = Array.from(document.querySelectorAll('article.Box-row')).map(article => {
  const h2 = article.querySelector('h2 a');
  const name = h2 ? h2.textContent.trim().replace(/\s+/g, ' ') : '';
  const href = h2 ? 'https://github.com' + h2.getAttribute('href') : '';
  const descEl = article.querySelector('p');
  const desc = descEl ? descEl.textContent.trim() : '';
  const starsEl = article.querySelector('[href$="/stargazers"]');
  const starsText = starsEl ? starsEl.textContent.trim() : '';
  const stars = starsText ? parseInt(starsText.replace(/[^0-9]/g, ''), 10) : 0;
  const langEl = article.querySelector('[itemprop="programmingLanguage"]');
  const lang = langEl ? langEl.textContent.trim() : '';
  const todayEl = article.querySelector('.d-inline-block.float-sm-right');
  const todayStars = todayEl ? todayEl.textContent.trim() : '';
  return { name, href, desc, stars, lang, todayStars };
});
return JSON.stringify(repos, null, 2);
})();