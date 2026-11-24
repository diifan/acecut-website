# AceCut incremental tennis SEO executor

This adds pages to the existing `diifan/acecut-website` repository and Vercel project
`prj_7RDDXImL9f7HgQtFmZ1TsPMG6CLC`, https://acecut.goswie.com. It does not rebuild the
brand, create another project, or touch the live `website-tracer` inference worktree.
The source implementation is versioned here; runtime data and credentials are not.

## Ownership and runtime

The controller owns `Acecut/production/keyword-expansion` and the MAC UI/API. This
executor only reads its fixed keywords.csv/manifest.json and writes the agreed
capacity.json. See INPUT-CONTRACT.md. It does not scrape Semrush itself, open browser
tabs, invoke paid exports or send messages. Semrush quota recovery belongs to the
producer's six-hour cooldown.

Only mutable daily configuration:
`/data/swi-algo/Swi-IP-Config/swie-app-mac/data/tracer-daily-acecut/config.json`.
Fields: enabled,target,hour,minute,prepare_hour,prepare_minute,timezone. Every invocation
rereads them. State/heartbeat, runs, dated receipts, SQLite consumer state and source
cache share that runtime directory. The 2026-11-24 receipt/progress also mirrors to
`reports/seo-expansion-20261124/acecut-{receipt.json,progress.md}`.

## Input and quality gates

Bind once with `executor.py bind --pool PATH --manifest PATH`. Binding stores paths,
not an immutable first-file checksum. Every preparation reads a fresh consistent
snapshot, verifies all original export hashes, and proves each accepted record's
keyword, metrics, evidence_url and date against an original row. NFKC/whitespace/
casefold deduplication, finite metrics, KD<30 and volume>100 are mandatory. Existing
published/reserved consumer states survive imports; externally occupied words are
never recycled. Candidate words are not publishable pages.

Evidence URLs are fetched in eight threads, shared per URL, with HTTPS/public-address
validation, bounded redirects/time/bytes and durable caches. Evidence must contain
explicit tennis context, align with the keyword and an actual supported video/tracer
workflow. Unrelated intent, duplicate source intent, duplicate slug and failed fetches
are separate outcomes. capacity.json excludes occupied and unverified candidates.
When supply is insufficient, receipts distinguish candidate shortfall from pending
fetches. The empty initial pool remains insufficient_keywords, never prepared.

Pages cite a verified source, quote at most 24 source words, supply a tennis-specific
clip-review workflow and a working local clip-plan worksheet. They link to the
existing 25-style Tracer. They do not invent player facts, scores, measurements,
source-video analysis or line-call capabilities. There are no per-keyword model calls.
Video-title datasets from the superseded approach are archived outside public/ and
cannot satisfy either the input boundary or the publication source-kind check.

## Prepare and publish

`executor.py prepare --day YYYY-MM-DD` reserves a complete batch, renders with atomic
progress every 50 pages, runs the existing Bun build, validates source hashes,
thresholds, unique titles/routes, internal links, canonicals, all new sitemap entries
and preservation of baseline assets/API/privacy. It commits locally and stages a
production-environment Vercel deployment with `--skip-domain`, verifying the live
alias remains unchanged. No partial batch is uploaded.

`executor.py publish --day YYYY-MM-DD` checks configured release time, matching target,
manifest/page/source hashes, READY production deployment, project/commit provenance
and unchanged main. It fast-forwards GitHub, promotes the validated deployment and
verifies domain binding, complete live sitemap batch coverage and byte-identical
sample pages. Failures remain visible; no force pushes or destructive resets occur.
GitHub auto-deployment can build the same published commit separately.

`tick` wakes every minute, updates heartbeat and reads config. It prepares tomorrow
at prepare_hour:prepare_minute, retries incomplete preparation every five minutes,
and at hour:minute only publishes an already validated version. It can retry today's
missing preparation before that cutoff. Only 2026-11-24 has the user's explicit
prepare-and-publish-immediately exception after the cutoff. An exclusive lock prevents
overlap. Disabled config suppresses work, while heartbeat remains observable.

## Operations and tests

Service/timer: `swie-acecut-tracer-daily.{service,timer}`. Service user swi-codex;
installation uses the authorized ubuntu operator. No timing/quantity is hardcoded in
the timer. Its one-minute wake checks the shared configuration. Code entry is this
worktree's executor.py; App production/tracer-daily contains a thin entry wrapper.

`python3 production/tracer-daily/test_keyword_input.py` tests import boundaries,
empty→append without rebind, occupied-state preservation, invalid metrics, hash
mutation, unproven records, cross-sport exclusion, empty-pool no-build/no-publish and
video-batch rejection.
`python3 production/tracer-daily/test_full_pipeline.py` uses explicitly synthetic
2000-keyword fixtures, isolated temporary Git origin/runtime, real Bun generation and
build, and mocked Vercel/online HTTP. Synthetic numbers never enter production state.
The test also checks disabled scheduling and early-publication refusal. Real keyword
collection and live batch publication remain separate acceptance requirements.
