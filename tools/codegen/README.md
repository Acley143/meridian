# codegen

Generates Python and Java bindings from `contracts/avro/*.avsc`. Invoked via
`make gen` (`tools/codegen/generate.py`). See `contracts/README.md` for the
full regeneration procedure and `docs/adr/0015-contracts-build-topology.md`
for why Java codegen goes through a standalone Maven helper module
(`avro-java-codegen/`) rather than running inside the module that ships the
generated code.

- `generate.py` — the single entry point. Regenerates Python dataclasses
  (`avro_to_python.py`) and, unless `--skip-java`, Java POJOs (via
  `avro-java-codegen/`'s pinned `avro-maven-plugin`), deterministically:
  same schemas in, byte-identical files out.
- `avro_to_python.py` — the Python-side generator. Not a general
  Avro-to-Python compiler; covers exactly the type shapes used in
  `contracts/avro/*.avsc`.
- `avro-java-codegen/` — a standalone Maven project (not a reactor member)
  whose only job is running `avro-maven-plugin` into a throwaway `target/`
  directory for `generate.py` to copy from. TypeScript is not generated —
  `apps/dashboard` consumes the OpenAPI surface, not Avro.

Output must never be hand-edited (`contracts/README.md`) — regenerating
from the schema is always the fix. The CI `gen-check` job enforces this by
regenerating into a temp directory and diffing against what's committed.
