# Things Workbench

An independent toolkit for understanding and working with Things databases without launching the app.

**Status: project bootstrap.** The first milestone is a read-only database inspector, a Python library and command-line interface, and versioned documentation of the database structure. No supported write or cloud-sync API is published here yet.

## Goals

- Document tables, columns, relationships and version-specific behavior.
- Separate verified semantics from observations, hypotheses and unknowns.
- Provide deterministic schema inspection without exporting task records.
- Add tested read APIs before introducing carefully reviewed mutation adapters.
- Keep local publication, synchronization acknowledgement and independent readback distinct.

## Safety and privacy

Never commit a Things database, database sidecars, account settings, authentication material, raw synchronization payloads, personal task content or private execution records. Schema output also needs review before publication: defaults and SQL definitions can contain sensitive literals.

This repository is not a database repair recipe. Do not edit a live Things database based on incomplete schema observations. Future mutation support must include compatibility checks, previews, concurrency protection, verified publication and recovery procedures.

Development is separate from any existing installation. No app launch, database mutation, cloud operation or scheduler change is required to work on this initial milestone.

## Independence

This is an unofficial project, not affiliated with or endorsed by Cultured Code. Things is the product being studied, not software distributed by this repository.

## License

No open-source license has been selected yet. Public visibility does not grant a reuse license.
