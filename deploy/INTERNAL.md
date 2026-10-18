# The internal port

Each visdom instance serves `/_activity`, `/_metrics`, `/_evict`, `/_retire`
and `/_drop` on a second port,
`VISDOM_INTERNAL_PORT` (8098). nginx never forwards it and compose does not
publish it, so only containers on the stack's network can reach it. On top of
that, every request is signed and the port only speaks TLS.

## Signing

The gateway signs each call with `VISDOM_INTERNAL_READ_KEY`. Visdom accepts the
keys in `VISDOM_INTERNAL_READ_KEYS`, which compose fills with the current key
and `VISDOM_INTERNAL_READ_KEY_PREVIOUS`. A signature is good for 60 seconds.

Make a key with `openssl rand -hex 32`. Compose refuses to start without one,
and the gateway sends nothing until both the key and `internal-ca.pem` are in
place; `/api/v1/health/components` names what is missing. To replace it:

1. Copy the current key into `VISDOM_INTERNAL_READ_KEY_PREVIOUS` and put a new
   one in `VISDOM_INTERNAL_READ_KEY`.
2. `docker compose up -d` recreates the instances and the gateway with both.
3. Clear `VISDOM_INTERNAL_READ_KEY_PREVIOUS` and run `docker compose up -d` again.

The calls that change something, closing a workspace's tabs, removing old
environments and removing a deleted workspace's files, are signed with
`VISDOM_INTERNAL_ADMIN_KEY` instead, which visdom checks against
`VISDOM_INTERNAL_ADMIN_KEYS`. It is a separate key so the read key alone cannot
remove anything. Make and replace it the same way, with
`VISDOM_INTERNAL_ADMIN_KEY_PREVIOUS`. Without it, nothing is removed: a
workspace or account deletion answers that it could not be done right now.

## TLS

The instances share one self-signed certificate, and the gateway trusts only
that certificate. Make it before the first `docker compose up`:

```bash
deploy/internal-cert.sh new
```

It writes `deploy/internal-tls/`, which is not in git: the certificate and key
the instances serve, and `internal-ca.pem`, the certificates the gateway
trusts. The certificate is good for two years. `/api/v1/health/components`
reports the days left and turns degraded 30 days before the end.

To replace it:

1. `deploy/internal-cert.sh new`. The old certificate moves to
   `internal.previous.crt` and stays in `internal-ca.pem`, so the gateway trusts
   both. The gateway reads that file on every call, so it needs no restart.
2. `docker compose up -d --force-recreate visdom-1 visdom-2 visdom-3`, so the
   instances serve the new one.
3. `deploy/internal-cert.sh drop-previous`.
