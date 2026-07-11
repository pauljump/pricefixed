---
name: Broken feed
about: A source stopped returning listings
title: "[broken] <source name>"
labels: broken-feed
---

**Which source?**
(the adapter name, e.g. `avalonbay` — see `python3 scrape.py --list`)

**What happened?**
Paste the output of:

```
python3 scrape.py --source <name>
```

or

```
python3 healthcheck.py
```

**Anything else?**
(e.g. the landlord relaunched their site, the URL 404s now, etc.)
