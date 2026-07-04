# Dogfooding Notes

## Round 1

Scenario: Run the installed CLI from `/tmp` as a first-time user.

Command:

```sh
site-capture --json crawl https://example.com --max-pages 1 --formats markdown --scroll-steps 0 --wait-ms 100
```

Observed friction:

- The simplest crawl failed because `--out` was required.
- Help output did not show default flag values, so timeout/session/format behavior required README lookup.

Changes made:

- Made `--out` optional for `capture` and `crawl`.
- Added a predictable default output path: `./captures/<host>-<command>-<timestamp>`.
- Switched argparse help to show default values.

## Round 2

Scenario: Rerun the first-time crawl path after Round 1 from `/tmp`.

Command:

```sh
site-capture --json crawl https://example.com --max-pages 1 --formats markdown --scroll-steps 0 --wait-ms 100
```

Observed friction:

- The new default output worked, but help displayed `--out` as defaulting to `None`.
- The JSON result pointed to `pages.jsonl`, but a human or agent still had to open the ledger to find page artifacts.

Changes made:

- Hid meaningless `None` defaults in help output.
- Added `index.md` to crawl outputs.
- Added artifact path maps to capture results and crawl ledger rows.

## Round 3

Scenario: Check help, one-page capture JSON, crawl JSON, `index.md`, and `pages.jsonl` from `/tmp`.

Commands:

```sh
site-capture crawl --help
site-capture --json capture https://example.com --out /tmp/site-capture-round3-capture --formats markdown --scroll-steps 0 --wait-ms 100
site-capture --json crawl https://example.com --out /tmp/site-capture-round3-crawl --max-pages 1 --formats markdown --scroll-steps 0 --wait-ms 100
```

Observed friction:

- Successful fallback crawls looked warning-heavy when a site had no `robots.txt` or `/sitemap.xml`.
- `pages.jsonl` artifact paths were absolute, so moving a capture folder would make the ledger stale.

Changes made:

- Split expected discovery fallback messages into `notices`.
- Kept `warnings` for unexpected discovery or capture problems.
- Made crawl ledger artifact paths relative to the capture root.

## Round 4

Scenario: Use `discover` as a human-facing read command from `/tmp`.

Commands:

```sh
site-capture discover https://example.com --max-pages 3
site-capture --json discover https://example.com --max-pages 3
site-capture discover --help
```

Observed friction:

- Human `discover` printed only `Discovered 1 URL(s).`, so the user had to rerun with `--json` to see the URL.

Changes made:

- Human `discover` now lists discovered URLs.
- Human `discover` now prints warnings and notices when present.

## Round 5

Scenario: Try the natural shorthand for Markdown output.

Command:

```sh
site-capture --json capture https://example.com --formats md --scroll-steps 0 --wait-ms 100
```

Observed friction:

- `md` failed as an unknown format even though it is an obvious shorthand for Markdown.
- The error did not list allowed formats.

Changes made:

- Added format aliases: `md`, `png`, `screen`, and `shot`.
- Added `all` to request every artifact format.
- Expanded unknown-format errors with the allowed values.

## Round 6

Scenario: Try a nonsensical crawl bound and run the development test command.

Commands:

```sh
site-capture --json crawl https://example.com --max-pages 0 --formats md --scroll-steps 0 --wait-ms 100
make test
```

Observed friction:

- `--max-pages 0` returned `ok: true` with zero captured pages.
- Running tests directly can import the installed package instead of local `src`, hiding or misreporting local changes.

Changes made:

- Added positive integer validation for page counts, timeouts, viewport dimensions, and Playwriter timeout.
- Added nonnegative integer validation for waits, scroll steps, and inter-page delay.
- Updated `make test` to force `PYTHONPATH=src`.

## Round 7

Scenario: Run the same crawl twice into the same output directory to test resume behavior.

Commands:

```sh
site-capture --json crawl https://example.com --out /tmp/site-capture-round7-seq --max-pages 1 --formats md --scroll-steps 0 --wait-ms 100
site-capture --json crawl https://example.com --out /tmp/site-capture-round7-seq --max-pages 1 --formats md --scroll-steps 0 --wait-ms 100
```

Observed friction:

- The second run reused the existing page but still reported `captured_count: 1`.
- The ledger and index did not show whether a row came from a fresh capture or a reused `meta.json`.

Changes made:

- Added `page_count`, fresh `captured_count`, and `reused_count` to crawl summaries.
- Added `source` to each `pages.jsonl` row.
- Added a `Source` column to `index.md`.

## Round 8

Scenario: Run a plain human crawl without `--json`.

Command:

```sh
site-capture crawl https://example.com --out /tmp/site-capture-round8 --max-pages 1 --formats md --scroll-steps 0 --wait-ms 100
```

Observed friction:

- The closeout reported only the output directory, not the files to open next.

Changes made:

- Human crawl output now prints `index_md`, `manifest`, and `pages_jsonl`.
- Human capture output now prints artifact paths for Markdown, screenshots, HTML, metadata, and links.
