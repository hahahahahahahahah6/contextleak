# contextleak

Your `.gitignore` won't save your Docker image. `contextleak` checks whether the
`sensitive files sitting in your build context` — `.env`, private keys,
credentials, cloud configs — would actually be `COPY`'d/`ADD`'d into your image,
by simulating `.dockerignore` matching against every `COPY`/`ADD` instruction in
your Dockerfile.

```bash
pip install contextleak
cd your-project
contextleak
```

```
Scanned 214 files in build context (12 excluded by .dockerignore), 4 COPY/ADD instruction(s).

LEAK: 2 instruction(s) would copy sensitive files:

  [COPY line 8] COPY . /app  (stage: stage-1)
    - .env  (environment file, usually holds secrets)
    - certs/server.key  (private key material)

  [ADD line 11] ADD config/ /etc/myapp/
    - config/credentials.json  (file name suggests stored credentials)
```

Exit code `1` when a leak is found, `0` when clean — drop it into CI.

## Install

```bash
pip install contextleak
```

Requires Python 3.9+. Zero dependencies (stdlib only).

## Usage

```bash
contextleak [context] [-f DOCKERFILE] [--ignore-file IGNORE] [--json]
```

- `context` — build context directory (default: current directory).
- `-f, --dockerfile` — Dockerfile path (default: `<context>/Dockerfile`).
- `--ignore-file` — ignore file path (default: `<context>/.dockerignore`).
- `--json` — machine-readable output for CI pipelines.

What it does:

1. Parses the Dockerfile's `COPY`/`ADD` instructions (multi-stage aware;
   `COPY --from=<stage>` copies come from another stage, not the context, so
   they are skipped).
2. Simulates `.dockerignore` matching with Docker's own semantics — patterns
   anchored to the context root, `**` crossing directories, `!` negation with
   last-match-wins, directory patterns excluding their contents.
3. Expands each `COPY`/`ADD` source glob against the files that would actually
   be sent to the daemon.
4. Flags sensitive names: `.env`/`.env.*`, `*.pem`, `*.key`, SSH private keys,
   `*credential*`, `*secret*`, `*token*`, `.npmrc`, `.pypirc`, Terraform state
   and `*.tfvars`, kubeconfigs, service-account files, and the `.git` directory.

It also warns when an instruction references files that `.dockerignore` (or
absence) removed — that's a build that fails or silently copies nothing.

## Differentiation

Tools like Trivy scan the **finished image** for known vulnerabilities (CVEs in
packages). `contextleak` checks a different, earlier layer: the **build
context**. A secret doesn't need a CVE to hurt you — if your `.env` is
`COPY`'d into the image at build time, it ships with every push of that image,
and no vulnerability scanner will flag it because it's your own file, not a
known-vulnerable package. One cut, one job: does your build context leak
secrets into the image? Nothing else.

## License

MIT — see [LICENSE](LICENSE).
