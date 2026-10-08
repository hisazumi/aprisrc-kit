# Contributing

[日本語](CONTRIBUTING.ja.md)

Start with [the handoff guide](docs/handoff.md) and [purpose and scope](docs/positioning.md).
Create a feature branch and open a pull request against this repository's `main`.
Describe expected behavior, actual results, tested environments and remaining limitations.
Do not claim hardware verification from Simulator or mock tests.

For a service, prefer mission, config, tests and registration changes. Do not bypass control
ownership, expiry, speed limits, front safety, disconnect stop or E-stop. Read `AGENTS.md`
before changing the runtime. Run the standard checks listed in the root README.

Keep credentials, CA private keys, raw recordings, participant evaluation data and local
flash backups out of commits and issues. Check staged files before pushing. Use synthetic
observations for reproducible bug reports; include the sample, relevant scene/settings,
commit and redacted error/status information.

This public repository is the code-development home for APRISRC Kit. Private planning and
individual evaluation records are maintained separately; this is not a mirror of their Git
history. Contributions must be compatible with the applicable license for the changed path;
see [Licensing](LICENSING.md). Firmware changes retain the upstream GPL terms.
