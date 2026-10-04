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
| `release-rust.yaml` | the same, for maturin projects: wheel matrix, PyPI + crates.io, optional binary archives |
| `pre-commit.yaml` | run `.pre-commit-config.yaml` verbatim |
| `pytest.yaml` | run the test suite over a Python matrix |

### release

```yaml
name: release
on:
  push: {branches: [main], tags: ['v*.*.*']}
jobs:
  release:
    # required. a reusable workflow cannot hold more permission than its caller,
    # and this one pushes tags and creates releases. without it the run fails at
    # startup on any repo whose default workflow token is read-only.
    permissions:
      contents: write
    uses: nmichlo/.github/.github/workflows/release.yaml@main

  # every project that publishes owns this job. omit it for applications, and
  # pass `publish: false` above instead.
  python-publish:
    needs: [release]
    if: needs.release.outputs.version != ''
    runs-on: ubuntu-latest
    environment: {name: pypi, url: 'https://pypi.org/p/my-package'}
    permissions:
      id-token: write   # trusted publishing
      contents: write   # undrafting the release
    steps:
      - uses: nmichlo/.github/actions/build-dist@main
        with: {ref: '${{ needs.release.outputs.version }}'}
      - uses: pypa/gh-action-pypi-publish@release/v1
      - uses: nmichlo/.github/actions/undraft-release@main
        with: {tag: '${{ needs.release.outputs.version }}'}
```

#### Why publishing lives in the caller

**There are no PyPI tokens in any of these repos.** Publishing is trusted
publishing (OIDC) everywhere, and that is what forces this shape.

PyPI matches the `job_workflow_ref` claim, which names the file a job is
**written in** -- not the workflow the event triggered:

```
workflow_ref      nmichlo/doorway/.github/workflows/release.yaml
                  ^ the caller

job_workflow_ref  nmichlo/.github/.github/workflows/release.yaml
                  ^ what PyPI checks. it can never name the calling repo.
```

No configuration fixes it: PyPI builds the expected `job_workflow_ref` out of
the publisher's own `repository` claim and verifies that separately, so both
must name the same repo. Reusable workflows are unsupported on PyPI's side --
[pypa/gh-action-pypi-publish#166](https://github.com/pypa/gh-action-pypi-publish/issues/166).
Owning the job in the caller is upstream's own recommended workaround.

`pypa/gh-action-pypi-publish` is called directly rather than wrapped in a
composite action here, because it does not support being invoked from one.

**Each project needs a trusted publisher on PyPI**: the calling repo, the
workflow filename, and environment `pypi`.

#### Draft, publish, undraft

`release.yaml` creates the release as a **draft** whenever `publish` is true, and
the caller's last step undrafts it. A failed upload therefore leaves a draft
rather than a visible release advertising a version nobody can install -- fix the
cause and re-run. With `publish: false` there is nothing to wait for, so the
release is finished immediately.

The caller must pass **both** triggers. Tags pushed with `GITHUB_TOKEN` do not
trigger other workflows, so a split bump-then-publish pair can never publish on
a merge. One workflow owning both triggers is what makes it work without a PAT.

Version comes from the PR title keyword (`#major`, `#minor`, `#patch`), and only
from there: `actions/version-bump` finds the pull request the pushed commit
merged and reads its title, so squash, rebase and merge commits all release the
same version, and commit messages never count. Without a keyword nothing is
released, the same as `#none`, and neither does a direct push to `main` with no
pull request, which no test has gated. A `v*` tag pushed by hand releases as is.

The trigger is `push` to `main`, not a closed pull request. GitHub gives a
`pull_request` run from a **fork** a read-only token, even after the merge, so
the tag push fails with a 403 and nothing is released.

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

## Composite actions

Shared **steps**, as opposed to the shared **jobs** above. A composite action
runs inside the caller's own job, which is what makes `actions/gate` possible at
all.

| action | does |
|---|---|
| `actions/gate` | fail a job unless every job it `needs` succeeded |
| `actions/workflow-lint` | run actionlint and zizmor over `.github/workflows` |
| `actions/build-dist` | check out a tag and build sdist + wheel into `dist/` |
| `actions/undraft-release` | turn a draft GitHub release into a published one |
| `actions/version-bump` | read the `#bump` keyword from the merged PR's title and push the next tag, or pass a pushed tag through |
| `actions/stamp-cargo-version` | write a release version into `Cargo.toml` before a build |

### actions/gate

Branch protection matches a required status check **by name**, and every name a
workflow produces naturally is unstable:

```
reusable job   ->  "lint / pre-commit"              renaming a job breaks the rule
matrix job     ->  "test (3.12)", "test (3.13)"     changing the matrix breaks it
```

When the required name stops being reported, the rule waits for it forever and
every PR deadlocks on a check that will never arrive.

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
      - uses: nmichlo/.github/actions/gate@main
        with:
          needs: ${{ toJSON(needs) }}
```

`if: always()` is required. Without it the gate is **skipped** whenever what it
guards fails, and a skipped required check counts as success -- a gate that is
green precisely when it should not be.

The gate has to be a composite action rather than a reusable workflow: a
reusable job's check would be named `lint / gate`, which is the unstable shape
the gate exists to avoid.

`toJSON(needs)` rather than `needs.*.result` because it keeps the job names, so
the log says *which* job failed. The `needs` context is not readable from inside
an action, so the caller passes it in.

### actions/workflow-lint

Called by `pre-commit.yaml`, so no repo lists actionlint or zizmor in its own
`.pre-commit-config.yaml` and bumping either is one commit here.

The trade-off is deliberate and worth knowing: `pre-commit run --all-files` on a
laptop does **not** cover workflow files. Only CI does.

zizmor's policy comes from `actions/workflow-lint/zizmor.yml` unless a repo
commits its own `zizmor.yml`, which then wins.

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

For maturin projects. Cannot use `release.yaml`: wheels need a per-platform matrix, and
publishing can go to two indexes over OIDC.

```yaml
name: release
on:
  push: {branches: [main], tags: ['v*']}
jobs:
  release:
    # a reusable workflow cannot hold more permission than its caller. this one
    # needs `contents` to tag and release, and `id-token` for trusted publishing
    # to crates.io. omitting either fails the run at startup.
    permissions:
      contents: write
      id-token: write
    uses: nmichlo/.github/.github/workflows/release-rust.yaml@main
    with:
      package-name: my-package   # for the PyPI deployment environment URL
      crates-io: true            # false for python-only distributions

  # this job cannot live in the reusable workflow -- see below.
  python-publish:
    needs: [release]
    if: needs.release.outputs.version != ''
    runs-on: ubuntu-latest
    environment: {name: pypi, url: 'https://pypi.org/p/my-package'}
    permissions: {id-token: write}
    steps:
      - uses: actions/download-artifact@v4
        with: {pattern: 'wheels-*', merge-multiple: true, path: dist}
      - uses: pypa/gh-action-pypi-publish@release/v1
```

#### Optional inputs

| input | default | does |
|---|---|---|
| `python-version` | `3.12` | Python the wheels are built for |
| `crates-io` | `true` | also publish the crate to crates.io |
| `targets` | 5 entries, below | JSON array of build matrix entries |
| `bindings` | `''` | `bin` for a binary-only crate: drops `-i python<ver>` from the build |
| `bin-archives` | `false` | attach `<bin-name>-<version>-<triple>.tar.gz` to the release, for `cargo binstall` |
| `bin-name` | `package-name` | the binary `bin-archives` packages |

`targets` defaults to the matrix every caller had before it was an input:

```json
[
  {"runs-on": "ubuntu-latest", "target": "x86_64"},
  {"runs-on": "ubuntu-latest", "target": "aarch64"},
  {"runs-on": "windows-latest", "target": "x86_64"},
  {"runs-on": "macos-15-intel", "target": "x86_64"},
  {"runs-on": "macos-15", "target": "aarch64"}
]
```

An entry may also set `python-version`, which otherwise comes from the input.
`target` goes to maturin as-is: a short arch, or a full Rust target triple.

crates.io is published only once every wheel and the sdist have built. A crate
version can never be re-uploaded, so a failed build must stop it.

#### Binary-only crates

A maturin `bindings = "bin"` crate ships its CLI as a `py3-none-<platform>`
wheel. It has no Python extension, so `-i python<ver>` means nothing there, and
maturin fails if that interpreter is missing. `bindings: bin` drops it.

`bin-archives: true` also packages the binary for `cargo binstall`:

```
wheel  my_cli-1.2.3-py3-none-manylinux_2_17_x86_64.whl
         my_cli-1.2.3.data/scripts/my-cli    <- unzipped, not rebuilt
  ->
release asset  my-cli-1.2.3-x86_64-unknown-linux-gnu.tar.gz
                 my-cli, LICENSE*, THIRD_PARTY_LICENSES*, README.md
```

The binary comes out of the wheel rather than a second `cargo build`. It is
then the same file `pip install` puts on PATH, built in the same manylinux
container and cross toolchain. It needs `bindings: bin`, since only a bin wheel
holds a binary.

```yaml
    uses: nmichlo/.github/.github/workflows/release-rust.yaml@main
    with:
      package-name: my-cli
      bindings: bin
      bin-archives: true
      # no Windows entry: the crate does not build there
      targets: >-
        [
          {"runs-on": "ubuntu-latest", "target": "x86_64"},
          {"runs-on": "ubuntu-latest", "target": "aarch64"},
          {"runs-on": "macos-15-intel", "target": "x86_64"},
          {"runs-on": "macos-15", "target": "aarch64"}
        ]
```

`cargo binstall` finds the archive by **crate** name. If the binary is named
differently from the crate, add `[package.metadata.binstall]` to `Cargo.toml`.

#### Why the PyPI publish job lives in the caller

PyPI matches the `job_workflow_ref` claim, which names the file a job is
**written in** -- not the workflow the event triggered:

```
workflow_ref      nmichlo/norfair-rs/.github/workflows/release.yml
                  ^ the caller. what crates.io checks, so crates.io is fine.

job_workflow_ref  nmichlo/.github/.github/workflows/release-rust.yaml
                  ^ what PyPI checks. it can never name the calling repo.
```

There is no configuration that satisfies it, because PyPI builds the expected
`job_workflow_ref` out of the publisher's own `repository`, and checks that
separately -- so both have to name the same repo. Reusable workflows are
unsupported on PyPI's side: see
[pypa/gh-action-pypi-publish#166](https://github.com/pypa/gh-action-pypi-publish/issues/166).

The reusable workflow uploads the wheels as `wheels-*` artifacts and the
caller's own job downloads and publishes them, which is upstream's recommended
workaround. Name the caller's file whatever the PyPI publisher is configured
with -- the filename is part of the claim.

#### Where the version comes from

**The tag is the only version.** Cargo has no setuptools_scm: `version` must be a literal
in `Cargo.toml`. So the committed file says `0.0.0`, and every job that builds or publishes
writes the tag's version in first, with `actions/stamp-cargo-version`. Nothing is committed.

```
committed:    version = "0.0.0"
tag v1.2.4 -> version = "1.2.4"   (in the build job only) -> wheels, sdist, crates.io
```

A plain `cargo build` from a git checkout therefore reports `0.0.0`.

Publishing uses trusted publishing (OIDC) for both indexes, so no tokens are needed --
but the PyPI project and the crate must each have a trusted publisher configured.
