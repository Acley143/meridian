# Contributing

Meridian is a five-person team project. This file is the short version of
`CLAUDE.md` and `docs/test-strategy.md`, for humans making the same PRs an
agent would.

## Before opening a PR

1. Read the `PLAN.md` in the directory you're changing. It defines scope,
   boundaries, and definition of done. No `PLAN.md` in scope means stop and
   ask, not proceed.
2. Check `docs/adr/` for a decision covering what you're about to do.
3. If your change touches a type in `docs/domain-model.md`, update that
   document first — schemas are derived from it, not the other way around.

## PR requirements

- Name the ADR your change follows, or state that none governs it (the PR
  template asks this explicitly).
- Tests in the same PR as the change, per `docs/test-strategy.md`. A PR with
  no tests needs a one-sentence reason.
- No `Co-Authored-By` trailer and no "Generated with Claude Code" line on any
  commit, ever — see `.claude/settings.json` and `CLAUDE.md`.
- Conventional Commits, scoped to your workstream:
  `feat(pricer): add SABR volatility surface`.
- Branch naming: `<workstream>/<short-slug>`.

## ADRs

ADRs (`docs/adr/`) are immutable once merged. A decision that changes gets a
new ADR that supersedes the old one; the old file gets a single
`Superseded by ADR-00NN` line appended and nothing else is edited.

**Editorial amendments.** The decision text itself is immutable, but a
non-substantive correction — a rename, a broken link, a typo — doesn't
change what was decided or why, and doesn't warrant superseding two ADRs
over (say) a topic rename. Fix it in place, then append an `## Editorial
amendments` section at the foot of the ADR recording, dated: what changed,
and why it's non-substantive (the decision is unchanged). Use this only for
corrections that leave the decision and its reasoning intact. If a change
alters what was decided, or why, it is substantive — write a superseding
ADR instead, don't reach for this mechanism to avoid one.

## Generated code

Never hand-edit generated bindings under any language's build output for
`contracts/`. Fix the source schema and run `make gen`.

## CI is green from the first commit

`.github/workflows/ci.yml` must pass on every commit, including the one that
introduces a new job. A check that cannot pass yet — because the thing it
verifies doesn't exist yet at this stage of the project — is **skipped, with
a printed reason**, never left red and never deleted to hide the gap. When
the underlying capability lands (e.g. `tools/codegen` gets implemented), the
job's skip branch is replaced with the real check in the same PR, not left
skipping indefinitely.
