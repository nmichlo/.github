# .github

Shared GitHub configuration for my repos.

## Default community health files

`.github/ISSUE_TEMPLATE/` and `.github/pull_request_template.md` are picked up
automatically by every public repo on this account that does not define its own.

## Reusable workflows

Called from a repo's own `.github/workflows/`, so each repo carries a few lines
instead of a copy of the logic.

| workflow | does |
|---|---|
| `release.yaml` | bump the tag on merge to `main`, draft a release, publish, undraft |
| `release-rust.yaml` | the same, for maturin projects: wheel matrix, PyPI + crates.io |
| `pre-commit.yaml` | run `.pre-commit-config.yaml` verbatim |
| `pytest.yaml` | run the test suite over a Python matrix |

### release

```yaml
name: release
on:
  pull_request: {types: [closed], branches: [main]}
  push: {tags: ['v*.*.*']}
jobs:
  release:
    # required. a reusable workflow cannot hold more permission than its caller,
    # and this one pushes tags and creates releases. without it the run fails at
    # startup on any repo whose default workflow token is read-only.
    permissions:
      contents: write
    uses: nmichlo/.github/.github/workflows/release.yaml@main
    with:
      publish: true          # false for apps that are not published packages
    secrets: inherit
```

The caller must pass **both** triggers. Tags pushed with `GITHUB_TOKEN` do not
trigger other workflows, so a split bump-then-publish pair can never publish on
a merge. One workflow owning both triggers is what makes it work without a PAT.

Version comes from the PR title keyword (`#major`, `#minor`, `#patch`, `#none`),
defaulting to a patch bump.

### pre-commit

```yaml
name: lint
on: [pull_request]
jobs:
  pre-commit:
    uses: nmichlo/.github/.github/workflows/pre-commit.yaml@main
    with:
      install-extras: "convert,raw,test"   # the `ty` hook needs deps resolvable
```

## Gate jobs

Branch protection matches a required status check **by name**, and both of the
names CI produces naturally are unstable:

```
reusable job   ->  "lint / pre-commit"        renaming a job breaks the rule
matrix job     ->  "test (3.12)", "test (3.13)"   changing the matrix breaks it
```

When the name a rule requires stops being reported, the rule waits for it
forever and every PR deadlocks on a check that will never arrive.

So each repo adds one plain job whose name is fixed, and protects that instead:

```yaml
jobs:
  pre-commit:
    uses: nmichlo/.github/.github/workflows/pre-commit.yaml@main

  # the required check. always exactly "lint", whatever the jobs above are called.
  lint:
    needs: [pre-commit]
    if: always()
    runs-on: ubuntu-latest
    steps:
      - env: {PRE_COMMIT: "${{ needs.pre-commit.result }}"}
        run: '[ "${PRE_COMMIT}" = "success" ]'
```

`if: always()` is required, or the gate is skipped when what it guards fails --
and a skipped check reports success. The same shape in `test.yaml` gives `test`.

Every repo therefore reports the same two checks, `lint` and `test`, regardless
of what it runs underneath.

### pytest

```yaml
name: test
on:
  pull_request: {branches: ["main", "dev*", "feature*", "fix*"]}
jobs:
  test:
    uses: nmichlo/.github/.github/workflows/pytest.yaml@main
    with:
      python-versions: '["3.12", "3.13"]'
      install-extras: "test"
```

### release-rust

For maturin projects. Cannot use `release.yaml`: wheels need a per-platform matrix, the
version lives in `Cargo.toml` rather than being derived from the tag, and publishing can
go to two indexes over OIDC.

```yaml
name: release
on:
  pull_request: {types: [closed], branches: [main]}
  push: {tags: ['v*']}
jobs:
  release:
    # a reusable workflow cannot hold more permission than its caller. this one
    # needs `contents` to tag and release, and `id-token` for trusted publishing
    # to PyPI and crates.io. omitting either fails the run at startup.
    permissions:
      contents: write
      id-token: write
    uses: nmichlo/.github/.github/workflows/release-rust.yaml@main
    with:
      package-name: my-package   # for the PyPI deployment environment URL
      crates-io: true            # false for python-only distributions
    secrets: inherit
```

On merge it rewrites `Cargo.toml` to the next version, commits it, and tags **that**
commit, so the `version-check` guard holds on both the merge and manual-tag paths. No more
hand-editing `Cargo.toml` before a release.

Publishing uses trusted publishing (OIDC) for both indexes, so no tokens are needed --
but the PyPI project and the crate must each have a trusted publisher configured.
