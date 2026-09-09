import json

today_articles = [
    {"title": "Potential session/cache leakage between workspace instances or consumer accounts", "url": "https://github.com/anthropics/claude-code/issues/74066", "source": "github.com"},
    {"title": "In Britain, July 4 Is Mostly Just a Saturday", "url": "https://www.nytimes.com/2026/07/04/world/europe/uk-july-fourth-us-independence.html", "source": "nytimes.com"},
    {"title": "Explanation of everything you can see in htop/top on Linux", "url": "https://peteris.rocks/blog/htop/", "source": "peteris.rocks"},
    {"title": "For Cape Verde, There's Victory in Their World Cup Defeat", "url": "https://www.nytimes.com/2026/07/04/world/africa/cape-verde-world-cup.html", "source": "nytimes.com"},
    {"title": "Will Iran's New Supreme Leader, Mojtaba Khamenei, Attend His Father's Funeral?", "url": "https://www.nytimes.com/2026/07/04/world/middleeast/iran-supreme-leader-khamenei-son.html", "source": "nytimes.com"},
    {"title": "When the ability to smell goes away", "url": "https://arstechnica.com/science/2026/07/when-the-ability-to-smell-goes-away/", "source": "arstechnica.com"},
    {"title": "A martian rock has lots of carbon on it, and it's not clear why", "url": "https://arstechnica.com/science/2026/07/a-martian-rock-has-lots-of-carbon-on-it-and-its-not-clear-why/", "source": "arstechnica.com"},
    {"title": "Trump's Travel Crackdown Has a Winner: Mexican Tourism", "url": "https://www.nytimes.com/2026/07/04/world/americas/world-cup-mexico-tourism-trump.html", "source": "nytimes.com"},
    {"title": "Iran Projects Unity to the World While Pursuing a Crackdown at Home", "url": "https://www.nytimes.com/2026/07/04/world/middleeast/iran-dissidents-crackdown.html", "source": "nytimes.com"},
    {"title": "What to Know About Ayatollah Ali Khamenei as His Funeral Services Begin in Iran", "url": "https://www.nytimes.com/2026/07/04/world/middleeast/iran-funeral-supreme-leader-ali-khamenei.html", "source": "nytimes.com"},
    {"title": "Mexico's Secret 12th Man in the World Cup: Baby Jesus", "url": "https://www.nytimes.com/2026/07/04/world/americas/mexicos-secret-12th-man-in-the-world-cup-baby-jesus.html", "source": "nytimes.com"},
    {"title": "Astrophysicists Puzzle over Webb's New Universe", "url": "https://www.quantamagazine.org/astrophysicists-puzzle-over-webbs-new-universe-20260702/", "source": "quantamagazine.org"},
    {"title": "In Rwanda, July 4 Is Liberation Day From Genocide", "url": "https://www.nytimes.com/2026/07/04/world/africa/rwanda-july-4-liberation-day.html", "source": "nytimes.com"},
    {"title": "Momentary Unity at a Funeral Masks Deep Divisions Among Iran's Leaders", "url": "https://www.nytimes.com/2026/07/04/world/middleeast/iran-supreme-leader-funeral-divisions.html", "source": "nytimes.com"},
    {"title": "Funeral Procession for Khamenei Will Visit 5 Cities in Iran and Iraq", "url": "https://www.nytimes.com/2026/07/04/world/middleeast/khamenei-funeral-itineray-iran-iraq-shia.html", "source": "nytimes.com"},
    {"title": "Unearthing the Reality of Zombie Energy Systems in Africa's Energy Transition", "url": "https://www.catf.us/resource/unearthing-reality-zombie-energy-systems-africas-energy-transition/", "source": "catf.us"},
    {"title": "The bottleneck might be the air in the room", "url": "https://blog.mikebowler.ca/2026/07/03/co2-and-decision-making/", "source": "blog.mikebowler.ca"},
    {"title": "David Beazley - Programming Courses", "url": "https://www.dabeaz.com/courses.html", "source": "dabeaz.com"},
    {"title": "2026 Unslop AI-Written Fiction Contest Results", "url": "https://www.hyperstitionai.com/unslop-results", "source": "hyperstitionai.com"},
    {"title": "Agentic coding notes from Galapogos Island", "url": "https://danluu.com/ai-coding/#appendix-agentic-loops-and-writing-this-post", "source": "danluu.com"},
    {"title": "Australia Tried to Push Back on China. China Pushed Harder.", "url": "https://www.nytimes.com/2026/07/04/world/asia/australia-china-politics.html", "source": "nytimes.com"},
    {"title": "Maybe you should learn something", "url": "https://www.marginalia.nu/log/a_135_learn/", "source": "marginalia.nu"},
    {"title": "Synthesis is harder than analysis", "url": "https://surfingcomplexity.blog/2026/07/03/synthesis-is-harder-than-analysis/", "source": "surfingcomplexity.blog"},
    {"title": "MSI Center - How to gain SYSTEM privileges in seconds", "url": "https://mrbruh.com/msicenter/", "source": "mrbruh.com"},
    {"title": "Soatok's Informal Guide to Threat Models", "url": "https://soatok.blog/2026/06/30/soatoks-informal-guide-to-threat-models/", "source": "soatok.blog"},
    {"title": "Putin Visits Battlefield and Vows to Take More of Ukraine", "url": "https://www.nytimes.com/2026/07/03/world/europe/putin-ukraine-donbas-battlefield-visit.html", "source": "nytimes.com"},
    {"title": "What does privatization of the US Postal Service mean?", "url": "https://phenomenalworld.org/analysis/unstitching-america/", "source": "phenomenalworld.org"},
    {"title": "Scientists discover guidance system for migratory songbirds", "url": "https://news.exeter.ac.uk/faculty-of-environment-science-and-economy/scientists-discover-guidance-system-for-migratory-songbirds/", "source": "exeter.ac.uk"},
    {"title": "Odin, Wikipedia and engagement farming", "url": "https://katamari64.se/posts/2026/odin-wikipedia/", "source": "katamari64.se"},
    {"title": "The circuit that lets your brain think and see", "url": "https://www.engineering.columbia.edu/about/news/circuit-lets-your-brain-think-and-see", "source": "columbia.edu"},
    {"title": "Amsterdam invented the fire department", "url": "https://worksinprogress.co/issue/how-amsterdam-invented-the-fire-department/", "source": "worksinprogress.co"},
    {"title": "Giant trees have no trouble pumping water to top branches", "url": "https://news.exeter.ac.uk/faculty-of-environment-science-and-economy/giant-trees-have-no-trouble-pumping-water-to-top-branches/", "source": "exeter.ac.uk"},
    {"title": "Steam Controller Auto-Charge - pilot to magnetic charging puck using CV", "url": "https://github.com/FossPrime/Steam-Controller-Auto-Charge", "source": "github.com"},
    {"title": "Dispersion loss counteracts embedding condensation in small language models", "url": "https://chenliu-1996.github.io/projects/LM-Dispersion/", "source": "chenliu-1996.github.io"},
    {"title": "GitFut - Your GitHub stats turned into a World-Cup-style player card", "url": "https://gitfut.com", "source": "gitfut.com"},
    {"title": "Leanstral 1.5: Proof Abundance for All", "url": "https://mistral.ai/news/leanstral-1-5/", "source": "mistral.ai"},
    {"title": "GLM5.2 on AMD MI355X at 2626 tok/s/node at over 2x lower cost than Blackwell", "url": "https://www.wafer.ai/blog/glm52-amd", "source": "wafer.ai"},
    {"title": "Software, from First Principles", "url": "https://fazamhd.com/mental-models/software/", "source": "fazamhd.com"},
    {"title": "New serious vulnerabilities spiked around release of Claude Mythos Preview", "url": "https://epoch.ai/data-insights/cve-severity-spike", "source": "epoch.ai"},
    {"title": "Africans Are Turning to Starlink", "url": "https://www.economist.com/middle-east-and-africa/2026/07/02/africans-are-turning-to-starlink", "source": "economist.com"},
    {"title": "Espionage Against the European Parliament", "url": "https://citizenlab.ca/research/member-of-committee-investigating-spyware-hacked-with-pegasus/", "source": "citizenlab.ca"},
    {"title": "Enraptured by the World Cup, Countries Rewrite Rules for Fans", "url": "https://www.nytimes.com/2026/07/03/world/world-cup-countries-fans-holidays.html", "source": "nytimes.com"},
    {"title": "SearXNG: A free internet metasearch engine", "url": "https://github.com/searxng/searxng", "source": "github.com"},
    {"title": "FreeBSD ate my RAM", "url": "https://crocidb.com/post/freebsd-ate-my-ram/", "source": "crocidb.com"},
    {"title": "Tibetan Activist Sets Self on Fire Outside U.N. in Protest Against China", "url": "https://www.nytimes.com/2026/07/03/world/asia/tibet-self-immolation-united-nations-china.html", "source": "nytimes.com"},
    {"title": "U.S. Officials Believed Israel Was Plotting to Kill Iranian Negotiators", "url": "https://www.nytimes.com/2026/07/02/us/politics/israel-iran-negotiators-plot.html", "source": "nytimes.com"},
    {"title": "A Hitler Bunker Faces Demolition in Housing-Challenged Berlin", "url": "https://www.nytimes.com/2026/07/03/world/europe/hitler-bunker-berlin-germany.html", "source": "nytimes.com"},
    {"title": "International chess federation sanctions Kramnik", "url": "https://www.fide.com/fide-ethics-disciplinary-commission-issues-a-decision-in-case-involving-gm-vladimir-kramnik/", "source": "fide.com"},
    {"title": "How working memory could give rise to consciousness", "url": "https://www.scientificamerican.com/article/how-working-memory-could-give-rise-to-consciousness/", "source": "scientificamerican.com"},
    {"title": "Right to Local Intelligence", "url": "https://righttointelligence.org/", "source": "righttointelligence.org"},
    {"title": "An American Privacy Emergency", "url": "https://scottaaronson.blog/?p=9902", "source": "scottaaronson.blog"},
]

with open('/root/.openclaw/rss-sent.json', 'r') as f:
    sent_urls = set(json.load(f))

new_articles = [a for a in today_articles if a['url'] not in sent_urls]

for i, a in enumerate(new_articles, 1):
    print(f"{i}. {a['title']}")
    print(f"   {a['url']}")
    print()

print(f"Total new: {len(new_articles)}")
