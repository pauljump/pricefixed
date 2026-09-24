# NYBits Deep Dive

Research date: 2026-08-08.

The useful question is not just “does NYBits have a feed?” It is:

> Which manager or leasing system supplied each listing, and by what transport?

The public evidence supports a private, manager-specific import system. NYBits
does not publish a manager-to-feed registry or a master listing API.

## What NYBits Says

NYBits's [feed instructions](https://www.nybits.com/add.html) say that a
manager can supply:

- its website;
- a weekly Excel spreadsheet; or
- a full XML feed.

NYBits says its programmers inspect the source and usually implement the import
in two or three days. The same page says that brokers may submit open listings
by XML, while manual accounts are reserved for exclusives. This sounds like a
custom importer configured per account, not a public feed directory.

The [contact page](https://www.nybits.com/contact.html) confirms that feed and
manual delivery are both supported, but it does not expose which manager uses
which method.

## What The Public Site Reveals

The current public site has these fingerprints:

- Apache on Fedora with server-rendered HTML.
- A Java servlet-style session flow using `JSESSIONID` and `jsessionid` URLs.
- Internal application names visible in HTML comments, including
  `com.gromco.nybits` and `BuildingUtils$PostedByInfo`.
- Search and account actions routed through `/nyc/nyb` with internal
  `_ust_todo_` action identifiers.
- Search, building, manager, and listing pages rendered as HTML rather than a
  documented JSON or XML API.

The public [robots.txt](https://www.nybits.com/robots.txt) disallows several
internal paths, including `/cgi/brx`, `/listings`, `/apartmentlistings`, and
parameterized search URLs. It does not advertise a feed or API path. The usual
`sitemap.xml`, `sitemap_index.xml`, `security.txt`, and `humans.txt` paths were
also absent during this check.

The manager pages do expose useful identity data: manager name, building count,
managed-rental count, website text, and building portfolio. They do **not**
expose the delivery method or original feed URL. A listing's visible page is
therefore an observation of what NYBits published, not proof of how NYBits
received it.

## Public GitHub Search

No official NYBits or Gromco source repository was found in GitHub's public
repository search. The relevant results are third-party artifacts:

| Repository | What it is | Feed evidence |
|---|---|---|
| [Demerak/NYBits](https://github.com/Demerak/NYBits) | A 2021 Python scraper | Scrapes neighborhood building indexes and detail pages; it does not contain manager feeds or NYBits importer code |
| [SkyWaet/nybits](https://github.com/SkyWaet/nybits) | A saved-page/design experiment from around 2020 | Contains copied NYBits HTML and styling; no backend or feed configuration |
| [nythepegasus/nybits](https://github.com/nythepegasus/nybits) | An unrelated Swift utility package | Not connected to NYBits.com |

The Demerak scraper is still useful because it records the public page shape:
neighborhood index -> building page -> summary table. It does not reveal the
source of the listing data behind those pages.

## What We Can Infer Safely

1. NYBits has an ingestion process for manager feeds, but the configuration is
   probably held inside Gromco's application or operations process.
2. The input can be a manager's public website, a private weekly spreadsheet,
   or XML. Therefore “feed” does not always mean a discoverable URL.
3. The public manager directory is the best available index of who to map, but
   it cannot tell us whether a manager is feed-backed or manually posting.
4. The most promising public substitutes are the manager's own leasing system
   and its vendor portals: RentCafe/SecureCafe, AppFolio, MRI, and custom JSON
   endpoints.
5. A public listing page can be collected and provenance-preserved without
   claiming that it is the private NYBits feed.

## What We Should Not Do

- Do not guess hidden feed URLs from session parameters.
- Do not crawl paths that NYBits disallows in `robots.txt`.
- Do not treat HTML comments or internal action identifiers as an API contract.
- Do not claim a manager sends NYBits a feed unless the manager, NYBits, or a
  reproducible public source confirms it.

## Next Research Pass

Build a manager-level evidence table from the [NYBits manager directory](https://www.nybits.com/managers/residential_property_managers.html):

`manager -> buildings -> official website -> vendor -> public availability URL -> observed fields -> transport confidence`

Start with managers that have both a large building portfolio and a public
leasing system: Brodsky, Bozzuto, Rockrose, Rose, Greystar, Two Trees, 9300
Realty, and the managers already covered by SecureCafe, MRI, AppFolio, or JSON
adapters. This gives us the exhaustive provider inventory even when NYBits's
private import configuration remains unknowable.
