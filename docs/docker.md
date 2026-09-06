# Running wallcal in Docker

wallcal is a stateless HTTP service. It renders a PNG wallpaper from the query
string and keeps nothing: no database, no volumes, no secrets, no accounts.
A URL is the wallpaper. That means the container needs no persistent storage
and no backup, and it can run with a read-only root filesystem.

## Build

```sh
docker build -t wallcal:0.1.0 .
```

The build is two stages. The first resolves and installs the dependencies with
[uv](https://docs.astral.sh/uv/) from the committed `uv.lock`; the second copies
only the finished virtualenv. uv, the lockfile, the build tools and the test
suite are not in the final image.

`uv sync --locked` fails the build if `uv.lock` has drifted out of step with
`pyproject.toml`, so the image is reproducible from the repository alone.
`--no-editable` matters: a plain `uv sync` installs the project as a `.pth` file
pointing at the source tree, which would produce an image whose package data
(the bundled fonts and the builder page) is not actually there.

Most of the image is the `python:3.12-slim-bookworm` base; the virtualenv on
top of it is small, and Pillow is the bulk of that. `docker images wallcal`
gives the number for your own build.

CI builds `linux/amd64` only. For another architecture, name it yourself —
anything other than the host's is built under emulation and is slow:

```sh
docker buildx build --platform linux/arm64 -t wallcal:0.1.0 .
```

## Run

No compose file is shipped. Nothing in the image assumes a hostname, a
published port, or a reverse-proxy path, so the deployment is entirely yours.

```sh
docker run -d \
  --name wallcal \
  --restart unless-stopped \
  -p 8000:8000 \
  -e WALLCAL_TZ=Europe/Moscow \
  -e WALLCAL_DOMAIN=wallcal.example.com \
  -e WALLCAL_TRUSTED_PROXY=172.16.0.0/12 \
  --log-opt max-size=10m \
  --log-opt max-file=3 \
  --read-only \
  --cap-drop ALL \
  --security-opt no-new-privileges \
  wallcal:0.1.0
```

The two `--log-opt` flags are the ones to keep. The service writes a line per
request to stdout and Docker's default `json-file` driver never truncates it,
so an unattended container eventually fills the host disk with its own log.
Ten megabytes across three files is a few weeks of a household's traffic and
bounds the total at 30 MB. They are runtime options, not image settings: the
Dockerfile cannot set them, which is why they belong in whatever compose file
or `docker run` you deploy with.

`--read-only`, `--cap-drop ALL` and `--security-opt no-new-privileges` are not
required, but the service writes nothing and needs no capabilities, so there is
no reason to grant them. The virtualenv is precompiled to bytecode at build
time and `PYTHONDONTWRITEBYTECODE=1` is set, so a read-only root filesystem
costs nothing at startup; add `--tmpfs /tmp` if a future dependency wants
scratch space.

Check it:

```sh
curl -fsS http://127.0.0.1:8000/healthz
curl -fsS -o wallpaper.png 'http://127.0.0.1:8000/w/span.png?f=2026-01-01&t=2026-12-31&d=i16&th=dark'
```

## Environment variables

| Variable       | Default   | Meaning |
| -------------- | --------- | ------- |
| `WALLCAL_HOST` | `0.0.0.0` | Address uvicorn binds inside the container. Leave it alone; restrict exposure with the port mapping or the network, not with the bind address. |
| `WALLCAL_PORT` | `8000`    | Port uvicorn binds inside the container. Change it only if you also change the right-hand side of `-p`. `EXPOSE 8000` in the image is documentation of the default and is not affected. |
| `WALLCAL_TZ`   | `UTC`     | IANA time zone that decides which day counts as "today" — which dot is highlighted and how the progress footer reads. Any request may override it per-URL with `?tz=`. |
| `WALLCAL_DOMAIN` | `*` (any) | The domain the service answers on, e.g. `wallcal.example.com`; a comma-separated list for several, and a leading dot (`.example.com`) covers subdomains. A request arriving with any other `Host` is refused with `400`. The default accepts anything, which is right on a laptop and wrong on the open internet: set it as soon as the container has a name. |
| `WALLCAL_TRUSTED_PROXY` | unset | Addresses whose `X-Forwarded-For` is believed, as a comma-separated list, or `*` when the container is only reachable through your proxy. Unset means the header is ignored and the log records the peer that actually connected — which behind a proxy is the proxy. Set it only for a proxy you control: anyone able to reach the port directly could otherwise claim any address in the log. |
| `WALLCAL_QUOTES` | unset   | Path to your own quote file, replacing the built-in rotation. One quote per line, `text \| author`, `#` comments and blank lines ignored, UTF-8. Mount it read-only. The file is read at startup: an unreadable or empty one stops the container rather than surfacing as a 500 days later. |

There are no other variables, no config file and no secrets.

The IANA time zone database ships in the base image at `/usr/share/zoneinfo`,
so `zoneinfo` resolves any valid name — `Europe/Moscow`, `Asia/Tokyo`,
`America/Sao_Paulo` — with no `tzdata` package to add. An unknown name is
answered with `400`.

`TZ` (the conventional Docker variable) is deliberately *not* read: the image
runs on UTC internally and `WALLCAL_TZ` decides only the calendar's notion of
today, which keeps the rendered image independent of the container clock.

## Endpoints

| Method + path   | Returns |
| --------------- | ------- |
| `GET /`         | `text/html` — the builder page: every knob of the URL API with a live preview. Open it, tune the wallpaper, copy the resulting URL. |
| `GET /w/{mode}.png` | `image/png` — the wallpaper. `span`, `year`, `quarter` and `month` are implemented; `life` is registered but answers `501`, and any other name answers `400`. |
| `GET /api/quotes` | `application/json` — the active rotation plus today's pick, so the builder page can shuffle without a round trip. |
| `GET /healthz`  | `application/json` — `{"status":"ok"}`. Used by the image's `HEALTHCHECK`. |
| `GET /docs`     | The generated OpenAPI page, listing every query parameter. |

`/w/span.png` takes the span as `f` (from) and `t` (to). Each is an absolute
date (`YYYY-MM-DD` or `YYYYMMDD`), the word `today`, or an offset from today
like `90d`, `-3m`, `2y` — the offsets are what keep a link from expiring the day
the span ends. `year`, `quarter` and `month` take no dates at all and roll over
on their own. Then comes the screen, as `d` (a device preset) or `w`/`h`, and a
long tail of appearance options — `th`, `bg`, `fg`, `a`, `s`, `ft`, `pv` and
more. Use `/` or `/docs` rather than a list here; the query string is the API
and it is documented there.

Responses carry an `ETag` and a `Cache-Control` that expires at midnight in the
requested zone, which is exactly as long as the image stays correct.

`w`/`h` are capped per side (320..4096) and by area (4.2 megapixels — above the
largest phone we know, 1320x2868). Two renders run at a time and eight more may
queue; past that a request is refused at once with `503` and a `Retry-After`
rather than left to pile up. A render takes about 140 ms, so a full queue clears
in well under a second. The image also sets `MALLOC_ARENA_MAX=2`, because glibc
hands each thread its own arena and never gives it back, which turns a burst of
requests into a resident high-water mark the container is then judged by.

Measured on a fresh container: 52 MB idle, 79 MB after ten sequential renders
(it levels off there — the working set is reused, nothing accumulates), and
153 MB peak under forty simultaneous requests, of which thirty are shed.

Together these bound the memory one client can ask for, but they are not a rate
limit. The endpoint is unauthenticated by design, so put a rate limit on the
proxy if the service faces the open internet.

## Logs

One JSON line per request, on stdout — `docker logs wallcal`, or whatever log
driver the host uses. Nothing is written to a file, so the read-only root
filesystem stays intact and there is nothing to rotate.

```json
{"ts":"2026-09-06T19:32:57Z","ip":"203.0.113.9","method":"GET","path":"/w/span.png",
 "status":200,"ms":123,"bytes":82299,"query":"f=2026-09-01&t=2027-01-06&d=i16&q=1",
 "ua":"Shortcuts/2660.7 CFNetwork/1568 Darwin/24.0.0"}
```

These lines are subject to whatever the log driver is told to keep — see the
`--log-opt` flags under **Run**; without them the file grows forever.

`ms` is the time spent rendering and `bytes` the size sent, so a slow or
oversized request is visible without instrumenting anything else. `query` is
truncated at 300 characters — a quote can be long, and the log is not the place
to keep it. Refused requests are logged too: a `400` is exactly the line worth
having, because it means someone is on a broken link.

Because these are objects rather than prose, counting is a one-liner:

```sh
# Who fetches wallpapers, and how often
docker logs wallcal | jq -r 'select(.path | startswith("/w/")) | .ip' | sort | uniq -c | sort -rn

# Phones (the Shortcut) as opposed to someone tuning a link in the builder
docker logs wallcal | jq -r 'select(.ua | test("Shortcuts")) | .ts + " " + .ip'

# Which links are actually in use
docker logs wallcal | jq -r 'select(.status == 200) | .query' | sort | uniq -c | sort -rn

# Anything refused
docker logs wallcal | jq -c 'select(.status >= 400)'
```

A phone refetching an unchanged wallpaper answers `304`, so a daily Shortcut
shows up as one `200` when the drawing changes and a `304` on the other
mornings — the two together are what a returning user looks like.

The `ip` field is the address uvicorn attributes to the caller. Behind a reverse
proxy that is the proxy unless `WALLCAL_TRUSTED_PROXY` names it; see the table
above. Note that these lines are personal data in most jurisdictions — they tie
an address to a time and a link. The container's log driver decides how long
they are kept, and that decision is yours.

## Health

The image has neither `curl` nor `wget`, and neither is worth a package just to
poll a local socket. The `HEALTHCHECK` uses the interpreter that is already
running the service:

```sh
docker inspect --format '{{.State.Health.Status}}' wallcal
```

It reads `WALLCAL_PORT` at check time, so it follows a changed port.

## User

The service runs as UID/GID `10001` — a fixed, unprivileged system account
created at build time. The container never starts as root and never drops
privileges, so there is no setuid helper and no root-owned entrypoint.

The virtualenv at `/app/.venv` stays root-owned and world-readable: the process
can read its own code but cannot rewrite it.

```sh
docker exec wallcal id
# uid=10001 gid=10001 groups=10001
```

There is no `PUID`/`PGID`. Those exist to reconcile ownership on a mounted host
volume, and wallcal mounts nothing. If you need a different UID anyway — to
satisfy a cluster policy, say — override it at run time; nothing in the image
depends on the account existing in `/etc/passwd`:

```sh
docker run --user 65534:65534 ...
```

## Behind a reverse proxy

The service generates no absolute URLs and has no base-path setting, so it never
needs to be told where it lives. Two things do depend on the proxy, and both are
environment variables:

- `WALLCAL_DOMAIN` — the public name, so a request with any other `Host` is
  refused.
- `WALLCAL_TRUSTED_PROXY` — whose `X-Forwarded-For` to believe. Without it the
  access log records the proxy's address for every request, which makes the log
  useless; with it, the caller's own address appears.

When the container is only reachable through the proxy — it publishes no port of
its own and sits on an internal network — `*` is the right value, because the
proxy is then the only thing that can connect at all:

```yaml
# The container has no `ports:`; Traefik reaches it over the shared network.
environment:
  WALLCAL_DOMAIN: wallcal.example.com
  WALLCAL_TRUSTED_PROXY: "*"
labels:
  traefik.enable: "true"
  traefik.http.routers.wallcal.rule: Host(`wallcal.example.com`)
  traefik.http.services.wallcal.loadbalancer.server.port: "8000"
```

`*` is only safe under that condition. If the container also publishes a port to
the host, anything that can reach it directly can claim any address it likes in
your log; name the proxy's network instead, e.g. `172.16.0.0/12`.

If you serve it under a sub-path, strip the prefix at the proxy — the image has
no `--root-path` setting.

Wallpapers are public images with no authentication of any kind. If the URL
should not be world-readable, put the authentication in the proxy.

## Upgrading

```sh
docker build -t wallcal:0.1.0 . && docker rm -f wallcal && docker run -d ...
```

There is no state, so there is no migration and no rollback procedure beyond
starting the previous tag.
