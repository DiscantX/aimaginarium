# SRD data source

The JSON files in `2024/` are copied unmodified from the English 2024 data in the
`5e-bits/5e-srd-api` repository, path `packages/5e-database/src/2024/en`.

- Upstream commit: `05c109ea1f6b5445960b645ded48ad9c6a8df7b0` (2026-10-03)
- Content: System Reference Document 5.2 by Wizards of the Coast LLC (CC-BY-4.0); see `NOTICE` at the repository root.
- Packaging and structure: 5e-bits (MIT); see `LICENSE-5e-database.md`.

To refresh, copy the files again and update the commit above. The loader (`python -m aimaginarium.srd build`) reads them as-is.
