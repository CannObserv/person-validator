# Local Development

## Auth Header Injection

When running the Django dev server locally (outside the exe.dev proxy),
the `X-ExeDev-Email` and `X-ExeDev-UserID` headers are not present.
You need to inject them manually to test authenticated flows.

### Option 1: mitmdump reverse proxy

Run the Django dev server on port 8000, then use
[mitmproxy](https://mitmproxy.org/) to proxy port 3000 → 8000 with
injected headers:

```bash
# Terminal 1 — Django
DJANGO_SETTINGS_MODULE=src.web.config.settings uv run python -m django runserver 0.0.0.0:8000

# Terminal 2 — mitmdump proxy with header injection
mitmdump \
  --mode reverse:http://localhost:8000 \
  --listen-port 3000 \
  --set modify_headers='/~q/X-Exedev-Email/you@example.com' \
  --set modify_headers='/~q/X-Exedev-Userid/usr_local'
```

Then access the app at `http://localhost:3000/`.

### Option 2: curl with headers

For quick API or admin checks without a browser:

```bash
curl -H "X-ExeDev-Email: you@example.com" \
     -H "X-ExeDev-UserID: usr_local" \
     http://localhost:8000/admin/
```

### Option 3: Use the exe.dev proxy

If the service is running on the VM, access it through the proxy at
`https://person-validator.exe.xyz:8000/` — headers are injected
automatically for authenticated exe.dev users.

## Running Services

See [AGENTS.md](../AGENTS.md) for Django management and systemd commands.
