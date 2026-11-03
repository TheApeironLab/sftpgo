# sftpgo application chart

This repository owns this chart and publishes it independently. The application is
installed as one Helm release (Apeiron application ID `files`). Vasi imports
the packaged chart; platform IAM, database and object storage are external services.
The imported templates originated in Chentu; `files/origin.json` records the exact source.

## Deployment inputs

Use site-specific values; `charts/sftpgo/values-vasi.example.yaml` is a rendering fixture containing
reserved example addresses and is not a ready-to-run installation configuration.
Supply a reviewed application image, domain, registry and storage class. Create the
namespace-local `registry-pull` image Secret and `chentu-ca` ConfigMap (`ca.crt`) as
required by the deployment, plus the following runtime Secrets:

| Secret | Contents |
|---|---|
| `files-admin` | password |
| `files-oidc` | issuer, client-id, client-secret |

SFTPGo WebClient uses the OIDC sub as its account name. Provision personal/team buckets and user mappings before granting access. The management API remains loopback-only.

Chart rendering does not create Keycloak clients, grant users application roles,
create database accounts or populate object storage. The installer must prepare
these inputs before Helm apply. No IAM administrator credential belongs in values
or application Pods. The SSO/application provisioning adapter is a separate integration.

## Validation and release

```sh
helm lint charts/sftpgo --values charts/sftpgo/values-vasi.example.yaml
helm template files charts/sftpgo --namespace files --values charts/sftpgo/values-vasi.example.yaml
python3 release/package.py --output /absolute/path/outside/this/repository
```

The `Application chart` workflow uploads `sftpgo-charts`: the standard `.tgz` and
`sftpgo-chart-release.json` with archive SHA-256, size and source commit. Packaging
requires clean committed sources. Use `--development` for local validation only;
development provenance must not be promoted to a published release. Every published
chart version is immutable; bump `Chart.yaml` before publishing changed material.

A successful render or package is not evidence of a deployed application or working
SSO. Verify real login, app authorization, readiness and persistent data on the target
architecture. Helm rollback does not restore databases, object storage or IAM state.
