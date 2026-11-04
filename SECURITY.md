# Security

The local development server binds to loopback. Do not expose Vite, the robotd Unix socket, or the offline ASR worker to the internet. For the hosted demo, use the documented HTTPS gateway and independent DuckKing services; see [deployment](deploy/README.md).

Dynamic rooms isolate voice sessions and simulation state, but are public demo rooms, not authenticated private accounts. The defaults are ten rooms and four simultaneously loaded physics worlds; capacity is configurable. Same-origin and Host checks reject cross-origin requests; they do not provide user authentication. Keep access restrictions at the HTTPS entry point if the demo must be private.

Keep Linx credentials and device identities in private configuration outside the repository. Never include tokens, user recordings, browser profiles, or private account screenshots in issues or pull requests. Runtime speech audio stays in memory; bounded diagnostic files may contain redacted recognition text. Redaction is a fixed rule set, not a general personal-information detector. Restrict access to diagnostics and statistics when hosting externally.

Release packages are built from committed files and fixed model assets, checked with SHA-256, and verified before activation. A staged deployment does not imply public or real cloud voice acceptance. Release metadata and coverage reports use field allowlists; credentials and device identities must never appear in public APIs.

Report vulnerabilities through the repository's private security reporting feature when enabled, or contact the maintainer without publishing credentials or exploit details.
