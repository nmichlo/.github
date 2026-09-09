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
    permissions:
      contents: write
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
