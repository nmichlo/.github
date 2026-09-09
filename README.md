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
