# Initial public release

[日本語](release-scope.ja.md)

This repository starts with one reviewed current-file snapshot, not the previous private
repository's commit history, branches, pull requests, issues or Actions logs.

Included: service/runtime code and self-contained tests, Simulator scenarios, protocol
schemas, participant guides, public architecture/safety summary, printable markers, and
GPL-covered firmware source with upstream notices. No compiled firmware is provided.

Not included: internal plans, detailed integration/experiment timelines, pilot evaluation
materials, raw recordings, local credentials/configuration, private flash backups, diagnostic
motor scripts and the separate PhysiCode provider contract bundle/supervisor.
The public guides summarize known safety limits and unverified behavior instead of publishing
private trial histories. Existing technical settings and firmware identifiers remain unchanged.

Future code contributions belong here. Private planning and individual evaluation records
remain separate. This release does not change APRISRC's rules or determine official/mandatory
status; see [Purpose and scope](positioning.md). Check [Licensing](../LICENSING.md) before reuse.

## Verification

The independent public checkout passed 122 PWA tests, 112 server tests, typecheck,
production build and Ruff. The three separate provider-contract tests are intentionally
not shipped with their omitted bundle. npm audit reported zero findings after compatible
dependency updates and the Vitest 4.1.11 migration. This is not a comprehensive security
audit, and no new physical rover or firmware-build qualification was performed.
