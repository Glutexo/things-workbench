# Architecture and boundaries

Things Workbench is initially a **read-only inspection project**, not a replacement Things client. The checked-in database catalog is an observed physical layout, not permission to mutate a store. Public CLI behavior must be established by the package's own tests; private predecessor results do not establish it.

## Separation of responsibilities

1. **SQLite inspection:** open an explicitly selected existing database read-only; own a short, explicit snapshot transaction; enumerate all structural objects and close the transaction on every exit. Never hide an unsupported object by filtering it out.
2. **Physical catalog:** retain raw declarations separately from interpretations. Export no records, row counts, account data, file paths or collection timestamps. A format-version integer is the only allowlisted application metadata value in the documented inspection.
3. **Interpretation:** report an unknown enum/encoding as unknown. Distinguish tasks, projects, headings, templates and occurrences without asserting every combination is supported. See [database index](database/index.md).
4. **Future mutation adapters:** out of scope for the initial public package. An eventual adapter must independently establish native model/history behavior, authorization, concurrency protection, complete change scope and recovery. A generic SQL update layer is not an equivalent substitute.
5. **Future synchronization adapters:** also out of scope. Local staging, remote acceptance, local publication and another device's view are separate claims.

## Dependency boundary

The public project must not depend on a private predecessor checkout, its credentials, installed native binaries, private frameworks copied into the repository, account snapshots, standing permissions or archived runtime seals. Prior private work informs risks and narrowly labeled semantic notes only. It is not packaged or executed by the catalog recipe.

The database's Things format version, installed application build, SQLite engine version, SQLite schema cookie and catalog format version are separate identities. A matching application version alone does not establish matching DDL or API/ABI compatibility.

## Evidence flow

```text
explicit local input
  -> bounded read-only structural snapshot
  -> private raw evidence and privacy audit
  -> reviewed, deterministic physical catalog
  -> confidence-labeled public documentation
```

No stage implies app launch, credentials, cloud traffic, migrations, a scheduler, or write authorization. See [support matrix](support-matrix.md) and [safety](safety.md).
