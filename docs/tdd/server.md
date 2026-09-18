# Server

> **Status: proposal, the first slice built.** The brick exists at
> `components/server/`: the `server/dependencies`,
> `server/uvicorn-adapter` and `server/http-url` kinds; `AppCtx` and
> `app`, with the dependencies as providers, the problem-details
> plugin, `default_exception_handlers` and `problem`, and Litestar's
> logging off; `bind`, the request log, `serve`, `shutdown` and
> `http_local_url` in `adapter.py`; the test YAML; `test_system.py`
> and `test_adapter.py`; and the entries in the workspace
> `pyproject.toml`. Not yet built: `health_routes`,
> `require_idempotency_key`, the CORS config from `AppCtx.cors`, the
> brick's OpenAPI default with the Scalar page, `test_interface.py`,
> the entry in `projects/bricks/pyproject.toml`, the readme row and the
> tag. What the design reuses — the `system` brick's `Component`,
> `REQUIRED`, `constant` and `register_components`, `env`'s tags and
> resource path, `log`'s `get_logger`, `test_system`'s
> `with_test_system` — is named in Background. Everything under
> Proposed Solution is the build list, and "The first slice" says what
> came first and what follows.

## Objective

A workspace built on these bricks serves an HTTP API: routes a base
declares, each handler reaching the started instances it needs — a
database client, a signer, a dispatcher — without any of them being
global; request and response bodies validated against a schema; an
OpenAPI document generated from that schema and served with a page;
every failure answered as an RFC 9457 problem-details body; and the
listener started and stopped with the rest of the system. This TDD
says which library carries that in Python and why, how the config keys
mono's interceptors turned into request keys become named dependencies
here, the shape of the three components, the error bodies, the health,
CORS and idempotency-key helpers, how the server runs beside a
synchronous lifecycle, and what the tests prove.

In scope: the `server` brick — its interface, the `app` assembly, the
`server/dependencies`, `server/uvicorn-adapter` and `server/http-url`
components and their config, the default exception handlers and the
problem-details bodies, `health_routes`, `require_idempotency_key`,
the CORS config, the OpenAPI document and its page, and the socket the
adapter binds; registration in both `pyproject.toml` files and the
readme; and the tests.

Out of scope: a workspace's routes and handlers, which follow under
that workspace's own design; authentication — mono's `auth` brick,
whose token interceptor a route layers over the system's, ports under
its own TDD, see
[auth](https://github.com/repldriven/mono/tree/main/components/auth);
an HTTP client brick, see
[http-client](https://github.com/repldriven/mono/tree/main/components/http-client);
TLS, which a proxy in front of the service terminates; WebSockets and
server-sent events.

## Background

What exists, and what the design carries over.

- **The mono brick.** `server` in mono, at
  [components/server](https://github.com/repldriven/mono/tree/main/components/server):
  reitit routes as data with malli coercion, sieppari interceptors,
  muuntaja for JSON, Jetty, and a Scalar page over the generated
  OpenAPI document. Its `system.clj` registers three component kinds —
  `server/interceptors`, `server/jetty-adapter` and `server/http-url` —
  and the adapter's config is `handler` (required), `interceptors`,
  `ready-fn`, `cors` and `options`, defaulting to `:join? false` and
  `:port 0`. Its interface gives a base the standard router data, the
  default handler for unmatched routes, the OpenAPI and page handlers,
  `health-routes`, `wrap-cors`, `require-idempotency-key` and
  `http-local-url`. The port keeps the three kinds and their config
  keys, the app as a function of a context the adapter builds, the
  error bodies and their `type` strings, the health paths, the CORS
  semantics, the idempotency-key rule, the exclusive bind on port 0,
  and the URL component.
- **What the interceptor did.** Each config key of `server/interceptors`
  became an `:enter` step that put the started instance onto the Ring
  request under that key: the YAML says `store: !system/ref
  realworld.store` and a handler reads `(:store request)`. The step
  exists because a Ring handler takes one opaque map. A base supplies
  its handler as a function of a context — `{:interceptors :ready-fn
  :cors}` — patched into the definitions before start, and lists
  `(:interceptors ctx)` on the routes the chain should reach.
- **The `system` brick.** `components/system/src/mono_bricks/system/`:
  a `Component` is `start`, `stop`, default `config`, a `config_schema`
  pydantic validates and an `instance_schema`; `REQUIRED` marks config
  a component cannot start without; `register_components` registers a
  brick's kinds under a namespace; `constant` wraps a value YAML cannot
  carry, such as a function, for a test patch or a base to supply. Refs
  are resolved to started instances before `start` is called, and
  `Ctx` hands it the config and, on stop, the instance. The reader
  registers `!system/component`, `!system/ref`, `!system/local-ref` and
  `!system/required-component`.
- **The wrapper brick shape.** `clickhouse`: `__init__.py` is the
  interface and registers the brick's kinds on import; `core.py` alone
  imports the library; config is a `TypedDict` the system validates;
  `test-resources/clickhouse/application-test.yml` includes the brick's
  own `client-test.yml`. The readme's table gives every brick its
  library and purpose in a line.
- **Test lifecycle.** `with_test_system(config_file, patch,
  component_ids, profile)` loads the test profile, applies a patch to
  the definitions, and starts the system for the block. The workspace
  `conftest.py` puts every brick's `test-resources` on the resource
  path and configures logging; the `docker` marker skips a test when no
  daemon answers.
- **Logging.** `get_logger(__name__)` with an event and key-value
  context, through stdlib logging, so a library's records and a brick's
  events share one config.
- **Registration.** A brick's `src` is listed in `dev-mode-dirs` and
  `[tool.polylith.bricks]` in the workspace `pyproject.toml`, and in
  `projects/bricks/pyproject.toml`, whose dependencies stay in step
  with the workspace's. A consumer pins a tag.

## Proposed Solution

### The library

Litestar, served by uvicorn: `litestar` and `uvicorn` in both
`pyproject.toml` files, and imported in the brick alone.

Litestar was chosen because the one thing mono's interceptor did —
carry a started instance to a handler — is what its dependency
injection does, by name and with a type: `dependencies` is a map of
name to `Provide` on any of four layers, app, router, controller and
handler, a lower layer overriding a higher by key, and a handler
declares the name as a keyword argument. That is the shape of
`:interceptors` in reitit's route data, and it comes with the rest of
what the brick needs: a generator dependency whose code after `yield`
runs after the handler and before the response is sent; an exception
raised in a dependency short-circuiting the handler; a
`ProblemDetailsPlugin` that renders RFC 9457 bodies and converts any
exception through a map; `exception_handlers` as a map; `CORSConfig`
below the router, so a preflight is answered on a path with no OPTIONS
handler; and an OpenAPI document generated from handler signatures,
with a `ScalarRenderPlugin` for the page. A handler may be
synchronous, run in a thread pool when it says `sync_to_thread=True`.
Both libraries classify Python 3.14. FastAPI and Connexion, the
candidates it was chosen over, are in Alternatives Considered.

The brick is a curated wrapper: it exposes `app`, which assembles a
`Litestar` from a base's route handlers and the adapter's context, the
three components, and the helpers a base composes into its routes. A
base that wants more of Litestar imports it directly.

### The brick

`components/server/`, in the workspace's shape:

```
src/mono_bricks/server/__init__.py
src/mono_bricks/server/core.py
src/mono_bricks/server/adapter.py
src/mono_bricks/server/system.py
test/mono_bricks/server/test_interface.py
test/mono_bricks/server/test_system.py
test/mono_bricks/server/test_adapter.py
test-resources/server/application-test.yml
test-resources/server/server-test.yml
```

`__init__.py` carries the module docstring — what the brick wraps,
which kinds it registers, how a handler names a dependency — registers
the three kinds with `system.register_components("server", ...)`, and
exports:

- `AppCtx` — what the adapter hands the app function: `dependencies`,
  a mapping of name to started instance; `ready_fn`, a zero-argument
  callable; `cors`, the adapter's `cors` config or `None`.
- `app(ctx, route_handlers, *, exception_handlers=None,
  openapi_config=None, **litestar_kwargs)` — the standard assembly,
  returning a `Litestar`.
- `require_idempotency_key` — a dependency provider for a route that
  needs the header.
- `health_routes(ready_fn)` — the actuator handlers.
- `http_local_url(server)` — the URL of a started adapter.
- `default_exception_handlers` and `problem(status, title, type,
  detail)` — the bodies, for a base that overrides one.

`core.py` is the only module that imports `litestar`; `adapter.py` the
only one that imports `uvicorn`; `system.py` defines the components
over both, as mono's `system.clj` does.

### The dependencies component

`server/dependencies` replaces `server/interceptors`. Its config is
whatever the YAML names — each key a ref to a started instance,
resolved by the system brick before start — and its instance is that
mapping, `dict(ctx.config)`, with `dict` as the instance schema. `app`
turns each entry into `Provide(provide, sync_to_thread=False)` on the
application layer, `provide` a closure of no arguments returning the
instance, so a handler declares the name and the type. The closure
takes no argument because Litestar reads a provider's parameters as
request parameters: `lambda v=v: v` fails when the `Litestar` is
constructed, `v` having no type annotation. Which brick the instance
comes from is the YAML's business, not the brick's: a group called
`store` holding whatever client the workspace chose is

```yaml
dependencies: !system/component
  system/component-kind: server/dependencies
  store: !system/ref store.client
```

and the handler that names it is

```python
@get("/pets", sync_to_thread=True)
def list_pets(store: Store) -> list[Pet]:
    return store.pets()
```

What the interceptor chain did beyond carrying instances maps onto
the layers:

- An `:enter` that reads the request and continues — a token
  interceptor — is a provider taking `request: Request`, declared in a
  router's or handler's `dependencies`, returning what the handler
  names.
- An `:enter` that terminates — `require-idempotency-key` — raises
  `ProblemDetailsException` from the provider, which the plugin renders
  and the handler never sees; the validated value is returned to the
  handler that names it.
- A `:leave` that releases what `:enter` acquired is a generator
  provider, whose cleanup runs after the handler and before the
  response is sent.
- A `:leave` that changes the response is an `after_request` hook on
  the same layers.
- A concern that wraps the whole request — the request log — is
  middleware, which short-circuits by not awaiting the next app.

### The uvicorn adapter component

`server/uvicorn-adapter` replaces `server/jetty-adapter`. Config:

- `app` — `REQUIRED`. A callable of `AppCtx` returning an ASGI app,
  which a base supplies as `system.constant(app)` on the group's `app`
  key before start, as mono's base does with `handler`.
- `dependencies` — `None`; a local ref to the dependencies component.
- `ready_fn` — `None`, read as always ready. A callable, or a
  `threading.Event`, whose `is_set` is the thunk.
- `cors` — `None`; see CORS below.
- `options` — `{"host": "0.0.0.0", "port": 0}`, mono's `:port 0` and
  wildcard host, merged into `uvicorn.Config`.

Start builds the `AppCtx`, calls `app`, binds the socket itself and
serves on a thread:

1. `adapter.bind(host, port)` opens the listening socket. On port 0 it
   leaves `SO_REUSEADDR` off, so the kernel refuses a port any process
   holds — mono's `exclusive-ephemeral-ports!`, which uvicorn's own
   bind cannot give since it sets the option whatever the port. On a
   fixed port it sets the option, so a restart reclaims the port from
   `TIME_WAIT`.
2. A `uvicorn.Server` over `uvicorn.Config(app, log_config=None,
   access_log=False, **options)` runs `serve(sockets=[sock])` under
   `asyncio.run` on a daemon thread. uvicorn installs no signal
   handlers off the main thread, so the process's own stay in place;
   the two logging arguments are Logging's.
3. Start waits for `server.started`, or for the thread to die, with a
   timeout, and raises if the server did not come up; the system brick
   turns that into a `StartError` and stops what started before it.

The instance is a `Server` dataclass — the uvicorn server, the thread
and the socket — and `http_local_url` reads `getsockname()` from the
socket, rendering a wildcard host as `localhost`, as mono renders a
`nil` one. Stop sets `should_exit`, which lets in-flight requests
finish, and joins the thread. `server/http-url` is unchanged: config
`uvicorn-adapter` required, instance the URL string.

### The app assembly

`app(ctx, route_handlers, ...)` is mono's `router-data`,
`standard-default-handler`, OpenAPI handlers and `wrap-cors` in one
call. It builds a `Litestar` with:

- `dependencies` from `ctx.dependencies`, one `Provide` per name.
- `plugins=[ProblemDetailsPlugin(ProblemDetailsConfig(
  enable_for_all_http_exceptions=True))]`, so every `HTTPException`
  Litestar raises leaves as `application/problem+json`.
- `exception_handlers`: the brick's defaults, a base's merged over
  them, as `router-data` merges.
- `cors_config` from `ctx.cors`, or none.
- `openapi_config`: the caller's, or the brick's default with
  `render_plugins=[ScalarRenderPlugin()]`; the document at
  `/schema/openapi.json` and the page at `/schema`, Litestar's paths.
- `route_handlers`: the base's, plus `health_routes(ctx.ready_fn)`.
- `logging_config=None`, under Logging.

Anything else the base passes reaches the `Litestar` constructor as
given, `middleware` included. The request log is the adapter's, under
Logging.

### The error bodies

Every failure the framework raises is answered in mono's shape —
`title`, `type`, `status`, `detail` — through `problem`, as a
`ProblemDetailsException`. `default_exception_handlers` maps:

- `ValidationException` — 400, `REJECTED`, `mono/bad-request`, the
  detail Litestar's exception carries about which field failed.
- A body that does not parse — 400, `REJECTED`, `mono/malformed-body`.
- `NotFoundException` — 404, `NOT_FOUND`, `server/not-found`.
- `MethodNotAllowedException` — 405, `METHOD_NOT_ALLOWED`,
  `server/method-not-allowed`.
- A return value that does not match the handler's annotation, which
  Litestar refuses to serialise — 500, `FAILED`, `mono/bad-response`.
- Anything else — 500, `FAILED`, `server/internal-error`, and the one
  case that logs, at error with the traceback, the method and the path.
  The client-triggered cases log nothing, as mono's do.

A base overrides one by passing its own map to `app`, as the mono base
does for the two failures its conformance suite words differently.

### Logging

The log brick's configuration is the only one in the process. Each
library that would install its own is told not to:

- uvicorn: `log_config=None`, so constructing a `Config` leaves stdlib
  logging as `log.configure` set it, and `access_log=False`, so its
  access line gives way to the brick's. Its `uvicorn.error` records —
  startup, shutdown, a connection it refused — reach stdlib logging as
  every library's do, and the log brick's formatters render them.
- Litestar: `logging_config=None`, so the app configures nothing and
  logs no exception itself; the `server/internal-error` handler is the
  one place an exception is logged, through `get_logger`.

The request log is the brick's own ASGI middleware, mono's
`request-log` interceptor. The adapter serves the app wrapped in it,
since Litestar applies app-level middleware per route, after routing,
and a request answered 404 or 405 would not reach it there. It notes
the time on the way in, reads the status from the response's start
message on the way out, and logs one line per request at info through
`get_logger`, the event in the access-log shape —
`GET /api/pets 200 1.2ms` — with `method`, `path`, `status` and `ms`
as context, so the console formatter reads like an access log and the
JSON formatter carries the fields. It excludes nothing.

The adapter logs its start and, once up, `Listening on <url>`, as
mono's does.

### Health routes

`health_routes(ready_fn)` returns three handlers, each
`include_in_schema=False`, on mono's paths: `/actuator/health/liveness`
always `{"status": "UP"}` and 200; `/actuator/health/readiness` `UP`
and 200 or `DOWN` and 503 by `ready_fn()`; `/actuator/health` the
aggregate with both under `components`. `app` adds them from
`ctx.ready_fn`.

### The idempotency key

`require_idempotency_key` is a provider taking `request: Request` and
returning the `Idempotency-Key` header once it matches
`^[A-Za-z0-9_-]{16,255}$`. A missing header raises 400 `REJECTED`
`mono/missing-idempotency-key`; a malformed one 400 `REJECTED`
`mono/invalid-idempotency-key`. A route that needs it declares
`dependencies={"idempotency_key": Provide(require_idempotency_key)}`
and names `idempotency_key` in its handler, where mono's route listed
the interceptor and the handler read the header again.

### CORS

The adapter's `cors` config is mono's: `origins`, one string or a
list, blanks dropped; `methods`, `request_headers`, `max_age` and
`credentials`, defaulting as `cors.clj` does. `app` turns it into
`CORSConfig(allow_origins, allow_methods, allow_headers, max_age,
allow_credentials)`. No origins, no config, so nothing is permitted.
Litestar's CORS middleware runs before routing, so the preflight a
route declares no OPTIONS handler for is answered rather than 404ed —
the reason mono's had to be middleware, which here is the only place
it can be.

### Synchronous handlers

The workspace is synchronous: `system.start` and `stop` are plain
calls, as is every operation a brick exposes. A handler is a plain
function too, declared `sync_to_thread=True` so Litestar runs it in
its thread pool off the event loop. What it names is whatever the
system started, shared across those threads; whether that instance
blocks is its own affair, not the server's. A provider for a started
instance is `sync_to_thread=False`: it returns an object and blocks on
nothing. An async handler is Litestar's ordinary case and needs no
declaration.

### A system

```yaml
system:
  server:
    app: !system/required-component

    dependencies: !system/component
      system/component-kind: server/dependencies
      store: !system/ref store.client

    uvicorn-adapter: !system/component
      system/component-kind: server/uvicorn-adapter
      app: !system/local-ref app
      dependencies: !system/local-ref dependencies
      cors:
        origins:
          - http://localhost:3000

    http-url: !system/component
      system/component-kind: server/http-url
      uvicorn-adapter: !system/local-ref uvicorn-adapter
```

The base's `app` is a function of the context, and start patches it
in:

```python
def app(ctx: server.AppCtx) -> Litestar:
    return server.app(ctx, route_handlers=[list_pets])


defs = system.defs(env.config("pets/application.yml", profile))
defs["server"]["app"] = system.constant(app)
system.start(defs)
```

The brick's `test-resources/server/server-test.yml` is the same group
with `got: "me"` and `this: "time"` as the dependencies, mono's test
values, and `application-test.yml` includes it under `server`.

A modular monolith declares a group per listener — `api` and `admin`,
say — each with the same four keys and its own port in `options`,
each `app` patched in by its group's name, and the instances both
serve reffed from both `dependencies`. Every adapter binds its own
socket and runs its own server on its own thread, and neither app
sees the other. One listener serving several modules is the other
shape: each module a Litestar `Router` with its own path and its own
`dependencies`, layered by key so a module's names stay its own, all
passed to one `app`.

### Registration and release

- Both `pyproject.toml` files: `litestar` and `uvicorn` in
  `dependencies`, at the versions current when the brick lands.
- The workspace `pyproject.toml`: `components/server/src` in
  `dev-mode-dirs`, and the brick in `[tool.polylith.bricks]`; the same
  entry in `projects/bricks/pyproject.toml`.
- `README.md`: a row in the components table — `server`, `litestar`
  and `uvicorn`, HTTP API with dependencies from the system, problem
  details and OpenAPI.
- A tag, since a consumer pins one.

### The first slice

1. The three components, `AppCtx`, `app` with the dependencies, the
   problem-details plugin, the default exception handlers and the
   request log, the socket and the thread, `http_local_url`, the test
   YAML, and the tests for the lifecycle, the port, a dependency
   reaching a handler and each error body.
2. `health_routes`, `require_idempotency_key` and CORS, with their
   tests.
3. The OpenAPI document and the Scalar page, with their test.
4. Registration in both `pyproject.toml` files and the readme, with
   `just test` and `just check` green, and the tag.

A workspace's routes follow under its own design, against the pinned
tag.

### Tests

Over TCP to the URL `server/http-url` reports, with the standard
library's `urllib.request`, since what the brick proves is the
listener; no test needs Docker.

- **`test_system.py`**: the system starts with a constant `app`
  patched in and stops; the adapter's socket is bound on port 0 with
  reuse-address off and `http-url` names a positive port; the port
  refuses a connection after stop; a `dependencies` component of
  `got` and `this` reaches a handler that declares both, as a JSON
  body of `{"got": "me", "this": "time"}`; a valid body is 200; an
  invalid body is 400 `REJECTED` `mono/bad-request` with a `detail`; a
  handler returning the wrong shape is 500 `FAILED`
  `mono/bad-response`; a body that is not JSON is 400
  `mono/malformed-body`; an unknown path is 404 `server/not-found`; a
  wrong method is 405 `server/method-not-allowed`; a handler that
  raises is 500 `server/internal-error` and one error line is logged;
  every request logs one info line through the log brick, its event in
  the access-log shape and `method`, `path` and `status` in its
  context.
- **`test_interface.py`**: liveness is `UP`; readiness is `DOWN` and
  503 when `ready_fn` says so, and the aggregate follows it; the
  idempotency key missing, malformed and valid, the last reaching the
  handler; an allowed origin is echoed, an unlisted one gets no CORS
  headers, a preflight is 204 without reaching the handler, and no
  origins configured adds nothing; the OpenAPI document lists the
  route and not the health paths, and the page is served.
- **`test_adapter.py`**: `bind` on port 0 leaves reuse-address off and
  on a fixed port sets it; `http_local_url` renders a wildcard host as
  `localhost` and a named one as given.

## Alternatives Considered

- **FastAPI.** Rejected: a `dependencies=[Depends(...)]` list on its
  app or router runs for effect and injects nothing by name, so a
  handler imports the provider of what it needs rather than declaring
  the name the YAML gave it; problem details and the Scalar page would
  be the brick's own code.
- **Connexion.** Rejected: spec-first — the OpenAPI document written by
  hand and handlers resolved from it — where reitit derives the
  document from typed route data, as Litestar does from handler
  signatures. Taken in part: its middleware stack is the shape a
  whole-request concern takes here, as ASGI middleware.
- **Starlette, Flask, Django and aiohttp.** Rejected: none injects by
  name at the application layer or generates an OpenAPI document from
  types without a further library.
- **Porting sieppari as an enter/leave executor over a list of
  dicts.** Rejected: it would forfeit the OpenAPI, typing and layering
  the framework gives the same chain, for a list that can be reordered
  at runtime, which nothing here does.
- **Keeping the kind `server/interceptors`.** Rejected: the instance is
  a mapping of names to instances handed to the injector, and the old
  name would send a reader looking for a chain.
- **Reading the port back from uvicorn's `servers`.** Rejected:
  uvicorn's bind sets reuse-address whatever the port, and `started`
  must be awaited before the socket exists; binding in the brick gives
  the exclusive ephemeral port, and the port, before serve begins.
- **Serving on the main thread.** Rejected: `system.start` returns and
  a test holds the system in a block, so the server runs on a thread
  with its own event loop, as `:join? false` ran Jetty.
- **Async handlers throughout.** Rejected for now: the workspace is
  synchronous, so a handler is a plain function in the thread pool,
  and the choice is per handler; nothing here stops a workspace
  writing async ones.
- **Content negotiation.** Rejected: JSON only, as mono's muuntaja
  instance selects.
- **The document at `/openapi.json` and the page at `/`.** Rejected:
  Litestar mounts both under one path, `/schema` by default; a
  workspace that wants them elsewhere sets the config's `path`.
- **Litestar's `TestClient` for the brick's tests.** Rejected: the
  tests prove the adapter and the port, so they go over TCP to the URL
  the system reports; a workspace's route tests may use it.

## Known Limitations

Gaps between this design and the first slice as built:

- **A `cors` block does nothing yet.** The adapter carries it into
  `AppCtx.cors` and `app` never turns it into a `CORSConfig`, so a
  YAML that names origins permits nothing, silently.
- **The OpenAPI page is Litestar's.** `app` sets no `openapi_config` of
  its own, so the document and the page are the library's defaults
  until the brick's, with the Scalar plugin, is added.
- **Health, the idempotency key, CORS and OpenAPI are unproved.**
  `health_routes` and `require_idempotency_key` are not exported and
  `test_interface.py` does not exist: the second and third slices.
- **The brick does not ship.** It is registered in the workspace
  `pyproject.toml` alone, not in `projects/bricks/pyproject.toml` or
  the readme's table, so a consumer pinning a tag does not receive it.
- **The handler example and the code disagree.** The brick's docstring
  and its tests annotate a dependency `NamedDependency[Store]`, where
  "The dependencies component" shows a bare `Store`; the docstring's
  form is the one the tests exercise, and the example should say so.

What the design leaves undone or unproved:

- **Interceptors are not data.** The chain is Litestar's layers, set
  in code; a workspace cannot reorder it from YAML.
- **A `:leave` is two things.** A cleanup is a generator provider and
  a change to the response is an `after_request` hook; nothing here is
  one object with both.
- **`type` is not a URI.** Kept as mono's bare strings,
  `mono/bad-request` and the rest, where RFC 9457 wants a URI.
- **The 405 carries no `Allow` header** until Litestar's exception
  says which methods a path has.
- **A request uvicorn refuses** before the app is reached — a
  malformed request line — gets uvicorn's plain 400, where Jetty's
  error handler gave a JSON body.
- **An injected instance is shared across handler threads.** Its
  thread-safety is its own.
- **No TLS.** As mono: a proxy terminates it.
- **Readiness is a thunk.** No component flips it; a base that
  registers a webhook at start passes a `threading.Event` and sets it.

## References

- [server](https://github.com/repldriven/mono/tree/main/components/server) —
  mono's server brick, the design this ports.
- [README](../../README.md) — the components table, the brick layout
  and how a consumer depends on the bricks.
- [Dependency injection](https://docs.litestar.dev/2/usage/dependency-injection.html) —
  `Provide`, the layers, overrides, generator dependencies and their
  cleanup timing.
- [Life cycle hooks](https://docs.litestar.dev/2/usage/lifecycle-hooks.html) —
  `before_request`, `after_request` and `after_response`.
- [Problem details](https://docs.litestar.dev/2/usage/plugins/problem_details.html) —
  the plugin, `ProblemDetailsException` and the exception map.
- [OpenAPI UI plugins](https://docs.litestar.dev/2/usage/openapi/ui_plugins.html) —
  `ScalarRenderPlugin` in `OpenAPIConfig`.
- [Built-in middleware](https://docs.litestar.dev/2/usage/middleware/builtin-middleware.html) —
  `CORSConfig` and the logging middleware.
- [Applications](https://docs.litestar.dev/2/usage/applications.html) —
  the four layers and the startup hooks.
- [Route handlers](https://docs.litestar.dev/2/usage/routing/handlers.html) —
  `sync_to_thread`.
- [uvicorn](https://www.uvicorn.org/) — `Config` and `Server`; `serve`
  takes bound sockets.
- [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457) — Problem Details
  for HTTP APIs.
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html) —
  the document the brick serves.
- [Scalar](https://github.com/scalar/scalar) — the API reference page.
- [Fetch: CORS protocol](https://fetch.spec.whatwg.org/#http-cors-protocol) —
  what the preflight and the headers mean.
- [Idempotency-Key header](https://datatracker.ietf.org/doc/draft-ietf-httpapi-idempotency-key-header/) —
  the header the provider validates.
