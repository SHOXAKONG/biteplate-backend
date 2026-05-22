# Manifest templates

Files in this directory are **not applied by CI/CD**. They're reference templates.

Real Secrets in production are created out-of-band via `kubectl create secret generic ...`
with values from your password manager / 1Password / etc. — never committed to git.

See [secret.example.yaml](secret.example.yaml) for the schema (which keys are expected
in the `biteplate-secrets` Secret).
