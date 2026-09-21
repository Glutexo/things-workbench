# Experimental copy-only wording adapter

The ordinary `--db` inspection commands remain read-only and unchanged. The
additional commands are a **bounded copy-only experiment**, not a general
Things synchronization writer or a live-publication route. Independent release
review remains separate from implementation and local acceptance.

## Local verification scope

An installed wheel, outside the checkout, was exercised against pinned Things
3.24 / build 32400506 / arm64 frameworks using a supplied detached snapshot.
These cases completed the public prepare → exact preview → test-authorized
digest approval → apply-copy flow:

* title only;
* notes only, including emoji, combining characters, CRLF, LF and whitespace;
* both title and notes;
* explicit empty notes on a target whose original notes were nonempty;
* 39,999 UTF-16 code units, including astral and combining characters;
* a different-target notes edit inheriting the first accepted notes output.

Fresh SQLite readback matched the complete requested strings. Full schema,
headers, tables, task fields and metadata were validated. Every output's logical
fingerprint matched its approved candidate. Apply did not replay the native
setter/save. Repeated apply refused. These are isolated local results, not
live changes, user-interface results, synchronization or cloud acknowledgments.

## Conservative note-history support

A second same-target notes-only edit can account for exactly one missing **new
intermediate `nt` base**, only when it derives from a fully verified completed
first output using the same pinned runtime. The first edit must start with an
empty original note and no earlier same-target note history, and each edit must
have a single whole-text replacement. Original bases and both timeline
operations remain preserved; this is not general operation coalescing.

The product's own supervised native save constructs a fresh witness over its
actual maps: native normalization, left-biased state extension, reconstruction
of the intermediate base and equivalent second composition. The resulting
serialized text can retain a deferred patch. An independent, narrow UTF-8 byte
range/CRC32 evaluator corroborates the exact original/intermediate/final text
chain. CRC or final-text equality alone is never permission. This is not a new
whole-store native receiver replay. Audit or caller-supplied witness JSON is
not an authorization input.

Full metadata/index/stage/encoder, raw carrier, old-atom, new-change, schema and
task-scope checks still apply. Nonempty original roots, multiple prior
same-target edits, partial/multiple patches, unsupported text types, missing
completed ancestry and other unproved representations refuse. Frozen earlier
refusals retain their original markers; support does not retroactively approve
them. General notes history remains unsupported beyond these checks.

The formerly unidentified scalar is now narrowly checked as the native local
history index: actual qualified getter/setter keys, native encoder identifiers,
exact typed +1, one observed stage and one matching inserted timeline map.
Every unrelated scalar/raw carrier stays unchanged. There is no blanket counter
exception. Metadata identifiers are preserved verbatim; task-ID width is not
imposed on native metadata identifiers. Unknown coalescing still refuses.

The framework reports `maxNotesLength=40000`. Public preflight conservatively
refuses 40,000 and 40,001 UTF-16 units before native execution. Title has a
separate 1–1,000-unit policy. No text normalization, trimming or truncation is
performed. NUL, unpaired surrogates and controls other than CR/LF/tab are refused.
An empty change to already-empty notes is a no-op, not an empty-notes positive.

## Explicit commands

Paths are examples, not defaults. Parent directories must be private and owned.
No command discovers or captures live data.

```sh
things-workbench copies import --snapshot /private-owned/input.sqlite \
  --workspace /private-owned/import \
  --declare detached-stable-resolved
things-workbench native build --app /Applications/Things3.app \
  --output /private-owned/runtime
things-workbench wording prepare --copy /private-owned/import \
  --plan /private-owned/plan.json --packet /private-owned/packet \
  --runtime /private-owned/runtime
things-workbench wording preview --packet /private-owned/packet
things-workbench wording apply-copy --packet /private-owned/packet \
  --approve EXACT_64_HEX_DIGEST_FROM_REVIEWED_PREVIEW
```

The strict plan contains `version: 1`, an existing 22-character
ASCII-alphanumeric `task` identifier, and nonempty `changes` containing only
string-valued `title` and/or `notes`. Duplicate/unknown keys, invalid IDs,
no-ops and unsupported states refuse. Only open, untrashed type-0,
nonrecurring tasks with `start=1`, null `startDate` and null `stopDate` are in
scope. Projects, headings, recurring templates/instances, dates, status,
activation, checklists and creation are excluded.

Prepare mutates only its disposable candidate. Preview revalidates all bindings
and displays complete escaped JSON, not a truncated summary. Apply creates a
new owned backup of the approved candidate; there is no arbitrary target option.
Failed, interrupted or consumed packets refuse instead of replaying a mutation.
A test harness's recorded digest approval is test authorization, not evidence
that a person reviewed a particular private preview or authorized live import.

## Ownership, compatibility and isolation

* `detached-stable-resolved` is the supplier's declaration, not autonomous cloud
  or recovery verification. Known owned lifecycle state overrides it, both at
  import and every continued verification. Interrupted import/prepare/apply,
  failed ancestors and candidate/BEFORE sources refuse. A completed output
  requires its exact complete/output identity, logical fingerprint, approval,
  packet artifacts, runtime and recursive supplier bindings, not just a marker.
  Retained `applying.json` is permitted only with this complete proof. Cycles
  and lineage beyond sixteen verification nodes fail closed. There is no
  private recovery-registry dependency or route back to live publication.
* SQLite backup creates exclusively owned files. Source and BEFORE never become
  writable native targets. For a WAL-mode source, backup uses exclusive locking
  and DELETE journal mode on the **new destination only** to produce detached
  storage. It does not checkpoint the source or delete foreign sidecars.
* Paths, physical identities, exact private modes, ACLs, links and sidecars are
  checked. Files are 0600 and owned roots 0700. Case aliases of forbidden
  locations are refused. Descriptor-bound ancestor checks and advisory locks
  are not isolation against root or an arbitrary malicious same-UID process.
* A packaged, independently pinned schema descriptor checks exact known DDL and
  selected headers. The Python gate precedes helper start; the sandbox precedes
  dyld; the native gate precedes explicit dlopen/store open, not the loading of
  already-linked frameworks before main. The database-version plist may be
  stored as XML TEXT or BLOB; its decoded value
  must still be integer 29, never boolean, real or string. SQLite rootpages and
  schema cookies are not Things format identifiers.
* Runtime v2 requires the full package/resource inventory and all helper,
  interposer and canary artifacts. It binds interpreter, compiler/SDK receipts,
  app resources and recursive Mach-O load-command resolution. System libraries
  are an explicit OS trust boundary. A pinned app-layout fallback is accepted
  only while its external directory is absent, never as a read/load grant.
* The sandbox is active before framework loading. Writable scope is the current
  native work/scratch subtree. Socket networking, fork and AppleEvent sends are
  denied, as are the specifically named credential/app service endpoints in
  the policy. This is not proof that all OS broker paths have been tested.
  Environment is rebuilt and inherited FDs closed. There is no unsandboxed
  fallback and no automatic build on import/help.

## Verification and limits

Source and installed-wheel suites passed on Python 3.11 and 3.14 with both
umask 022 and 077. Installed tests had no `src` directory and no `PYTHONPATH`;
imports resolved to site-packages. Both distribution archives were inspected
for the required schema JSON and absence of databases/native binaries.

Synthetic tests cover strict packet/runtime envelopes, dependency/header/source
binding, schema/ABI refusals, ACL/mode/alias checks, sidecar injection,
post-preview tamper, crash/restart, concurrent apply and injected I/O failures.
Separate genuine native packets exercised artifact/manifest tamper after preview,
wrong approval, fresh-process apply, two-process contention, five reached crash
points, and injected output/complete ENOSPC. Source/BEFORE remained unchanged;
no apply reran the native helper. These are reached software injection points,
not power-loss or physical disk-exhaustion certification.

Offline copies of six genuine history proofs passed positive retention, then
93 controls removed **all** carriers of each distinct old/new/base atom and
required refusal. Dropping a single identical duplicate is not evidence of
losing a distinct value; unsupported carrier changes remain a separate refusal.
No actual database history was edited for these controls.

Harmless sandbox canaries passed out-of-work read/write, TCP/UDP loopback and
fork denials, permitted work writes, environment sanitization and inherited-FD
closure. AppleEvent and credential checks are policy queries, not actual event
or credential requests. DNS and actual app/service requests were not exercised.
Full native timeout/signal-during-save and physical power-loss coverage are not
claimed. The conservative note subset above is not general history support.

Default tests explicitly skip genuine fixture-dependent native lanes and the
opt-in sandbox lanes. A skip is not acceptance. Full private receipts, native
maps/bases, output databases and quarantines stay outside the public repository.
No Things app launch/kill, live database access, cloud, credentials, predecessor
helper execution or scheduler changes were performed by this integration.
