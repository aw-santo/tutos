---
title: 13 - Resilience & Production Readiness
tags:
  - spring
  - spring-boot
  - resilience
  - resilience4j
  - production
  - senior
aliases:
  - Resilience
  - Circuit Breaker
  - Retry
  - Graceful Shutdown
  - Production Readiness
status: ready
created: 2026-07-09
---

# Resilience & Production Readiness

> [!abstract] Scope
> How a Spring Boot service *survives* the failure of its dependencies instead of amplifying it — the layered controls (timeouts, retries, circuit breakers, bulkheads, rate limiters, fallbacks), where they live now that **Spring Framework 7** ships `@Retryable`/`@ConcurrencyLimit` in the core, and how the process behaves under a rolling deploy (graceful shutdown, draining, readiness flip). The through-line is a single senior instinct: **make failure fast, bounded, and local.** For the async work these controls wrap, see [[10 - Messaging, Events & Async]]; for the probes and metrics that observe them, see [[12 - Actuator, Metrics & Observability]].

Related: [[00 - Spring Boot Index]], [[10 - Messaging, Events & Async]], [[12 - Actuator, Metrics & Observability]], [[05 - Web Layer & Embedded Servers - MVC vs WebFlux]]

![[circuit-breaker.gif|720]]

*Closed counts failures and lets calls through; past the threshold it trips open and fails fast; half-open lets a few trial calls decide whether to close the loop again.*

---

## 1. The concept: control failure, don't inherit it

Every remote call — a REST hop, a DB query, a queue publish — can be slow, wrong, or dead. Without controls, a *slow* dependency is the dangerous case: your threads block waiting on it, the pool fills, and a downstream problem becomes *your* outage that propagates further upstream. Resilience is the discipline of bounding that blast radius. Two postures sit at the ends of a spectrum:

- **Fail fast** — reject or error immediately when a dependency is unhealthy, freeing the caller's resources. Correct for internal, latency-sensitive paths where a wrong-but-fast answer beats a right-but-hung one.
- **Graceful degradation** — serve a reduced answer (a cached value, a default, a partial page) instead of an error. Correct where a degraded experience beats no experience (a product page that hides "recommendations" but still sells).

> [!tip] The framing interviewers want
> "Resilience isn't about never failing — it's about failing **fast, bounded, and locally**, and choosing per-call between failing fast and degrading gracefully. The controls stack: a **timeout** bounds one call, a **retry** rides out a blip, a **circuit breaker** stops hammering a dead dependency, a **bulkhead** stops one sick dependency from starving the rest, and a **fallback** decides what the user sees when all of that gives up."

---

## 2. Timeouts — the most important and most-forgotten control

A timeout is the only thing that turns an *unbounded* wait into a *bounded* failure. Every blocking client needs two: a **connect timeout** (how long to wait for a TCP/TLS connection) and a **read/response timeout** (how long to wait for bytes once connected). The JDK/HTTP-client defaults are usually *infinite* — which is the trap.

```java
@Bean
RestClient inventoryClient(RestClient.Builder builder) {
    var settings = ClientHttpRequestFactorySettings.defaults()
            .withConnectTimeout(Duration.ofSeconds(2))   // wait for the connection
            .withReadTimeout(Duration.ofSeconds(3));      // wait for the response
    return builder
            .baseUrl("https://inventory.internal")
            .requestFactory(ClientHttpRequestFactoryBuilder.detect().build(settings))
            .build();
}
```

For **WebClient** the equivalent lives on the reactive connector (`HttpClient.responseTimeout(...)` on Reactor Netty); reactive code should *also* wrap the call in `.timeout(Duration)` so a stalled stream is cancelled. Behind a blocking client sits a **connection pool** — size it deliberately (Apache HttpClient 5: max-total and max-per-route). A pool that is too small serialises calls; one that is too large lets a slow dependency consume every connection.

> [!warning] Gotcha #1 — no timeout → thread-pool exhaustion that cascades *upstream*
> A dependency slows from 50 ms to 30 s but doesn't error. With no read timeout, each request thread blocks for 30 s. Under load the Tomcat worker pool (default 200) fills; new requests queue, then time out at the *client's* client, and the slowness you inherited is now an outage you *emit* — to every caller upstream. The dead dependency took down healthy services.
> **Mitigation:** set a read timeout on **every** blocking client, shorter than the caller-facing SLA and shorter than your own request timeout budget. A timeout you didn't set is `Duration.INFINITE` — assume it and fix it.

> [!important] Timeouts are a *budget*, not a number
> If your endpoint must answer in 800 ms and it calls two services, those calls cannot each be given 3 s. Allocate a **latency budget** down the call tree so the sum of downstream timeouts is less than the caller's timeout. Otherwise the caller gives up first and your own timeout never fires — wasting the work and confusing the metrics.

---

## 3. Retries — exponential backoff, jitter, and idempotency

A retry re-issues a failed call in the hope the failure was **transient** (a dropped connection, a brief 503, a leader election). It is the most misused pattern because a naive retry *amplifies* the very outage it was meant to survive.

Three rules make retries safe:

1. **Only retry transient, retryable failures** — connection resets, timeouts, HTTP 429/503. Never retry a 400/404/422 (the answer won't change) or a business-rule rejection.
2. **Back off exponentially, with jitter** — space attempts out with a growing delay (`base · 2ⁿ`) and add **randomness** so a thousand clients that failed together don't retry in lockstep.
3. **Only retry idempotent operations** — a retry of a non-idempotent call risks executing the side-effect twice.

> [!warning] Gotcha #2 — retry *without backoff* → a retry storm that amplifies the outage
> A dependency hiccups; every client instantly retries 3×. You have just **tripled** the traffic to a service that was already struggling, guaranteeing it stays down. Fixed-interval retries across a fleet are worse — they synchronise into a thundering herd that hammers the recovering service in waves.
> **Mitigation:** exponential backoff **plus jitter**, a small `maxAttempts` (2–3, not 10), and a circuit breaker in front (§5) so retries stop entirely once the dependency is declared dead.

> [!warning] Gotcha #3 — retrying a NON-idempotent call → duplicate side-effects
> `POST /payments` times out. The response was lost, but the server *did* charge the card. Your retry charges it **again**. The same trap hits "send email", "publish event", and "insert order". A timeout tells you nothing about whether the work happened.
> **Mitigation:** make the operation idempotent *before* you make it retryable (see below). If you can't, don't retry it — fail fast and reconcile.

**Idempotency is the precondition for safe retries.** The standard technique is an **idempotency key**: the client sends a unique key per logical operation; the server records it and, on a duplicate, returns the original result instead of re-executing. This is the same de-duplication contract as at-least-once messaging — the consumer-side idempotency discussed in [[10 - Messaging, Events & Async]] is exactly what makes a producer-side retry safe. `GET`/`PUT`/`DELETE` are idempotent by HTTP contract; `POST` is not until you add a key.

---

## 4. Circuit breaker — closed / open / half-open

A retry survives a *blip*; a circuit breaker survives an *outage*. It is a state machine wrapped around a dependency that stops calls entirely once failures cross a threshold — letting the dependency recover and failing callers *instantly* instead of making them wait for a timeout.

| State | Behaviour | Transition |
|---|---|---|
| **Closed** | calls pass through; failures are counted in a sliding window | → Open when the failure rate exceeds the threshold |
| **Open** | calls are **rejected immediately** (no call made, fallback invoked) | → Half-open after `waitDurationInOpenState` elapses |
| **Half-open** | a limited number of trial calls are allowed through | → Closed if they succeed, → Open if they fail |

The payoff is the **Open** state: while the dependency is down, callers get an instant rejection (and their fallback) instead of blocking on a doomed call until the timeout — which is precisely what prevents the thread-pool exhaustion of §2 from ever starting.

> [!important] A breaker without a timeout is half a breaker
> A circuit breaker counts *failures*; a call that hangs forever never fails and never trips the breaker. Timeouts (§2) are what *produce* the failures the breaker measures. The two are a pair — always configure them together.

---

## 5. Bulkhead, rate limiter, load shedding & fallbacks

**Bulkhead — resource isolation.** Named after a ship's watertight compartments: give each dependency its own bounded pool (of threads or of concurrent permits) so that when one dependency goes slow and saturates *its* compartment, the threads serving *other* dependencies are untouched. Without bulkheads, one sick downstream drowns the whole shared pool — the cascade again.

**Rate limiter — protect the callee (and yourself).** Caps calls per unit time. Client-side it keeps you a polite consumer of a quota'd API; server-side it protects *you* from a caller (or a retry storm) that would otherwise overwhelm you.

**Load shedding — fail fast under overload.** When the process is past its safe capacity (queue depth, in-flight count), reject new work *immediately* with 503/429 rather than accepting it into a queue that only grows. Shedding a fraction of load keeps the rest healthy; accepting everything makes everything slow. `@ConcurrencyLimit` (§7) and a bulkhead are the mechanisms.

**Fallbacks — what the user sees when a control gives up.** A fallback is the graceful-degradation branch: a cached value, a sensible default, an empty list, or a fast error. Keep fallbacks **cheap and local** — a fallback that calls another remote service just moves the failure.

> [!warning] Gotcha #4 — a fallback that hides a systemic failure
> Returning an empty recommendations list on failure is graceful. Returning `balance = 0` or `permissions = none` on failure is a **correctness incident** dressed as resilience. And a fallback with no metric behind it turns a loud outage into a silent one — the dashboards look green while every user gets the degraded path.
> **Mitigation:** fall back only where a degraded answer is *safe*, never for authoritative data; and emit a metric/log on every fallback so degradation is visible ([[12 - Actuator, Metrics & Observability]]).

---

## 6. Resilience4j — annotations, config & aspect order

**Resilience4j** is the de-facto library (the successor to Netflix Hystrix, which is in maintenance). Its Spring Boot starter exposes one annotation per pattern, each taking a named instance and an optional `fallbackMethod`. The fallback must have the **same signature plus a trailing `Throwable`**.

```java
@Service
class InventoryService {

    @CircuitBreaker(name = "inventory", fallbackMethod = "stockFallback")
    @Retry(name = "inventory")                       // transient blips only
    public StockLevel getStock(String sku) {
        return inventoryClient.get()                 // the RestClient from §2 (has timeouts!)
                .uri("/stock/{sku}", sku)
                .retrieve()
                .body(StockLevel.class);
    }

    // same signature + Throwable — invoked when the breaker is open or retries are exhausted
    StockLevel stockFallback(String sku, Throwable ex) {
        return StockLevel.unknown(sku);              // cheap, local, degraded answer
    }
}
```

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        sliding-window-type: COUNT_BASED
        sliding-window-size: 20
        failure-rate-threshold: 50            # % of calls that fail → open
        wait-duration-in-open-state: 10s
        permitted-number-of-calls-in-half-open-state: 5
  retry:
    instances:
      inventory:
        max-attempts: 3
        wait-duration: 200ms
        enable-exponential-backoff: true
        exponential-backoff-multiplier: 2
        enable-randomized-wait: true          # THE jitter switch — do not omit
        retry-exceptions: [ java.io.IOException, java.util.concurrent.TimeoutException ]
  timelimiter:
    instances:
      inventory:
        timeout-duration: 3s
```

**The aspect order is fixed and it matters.** Resilience4j applies its aspects in a hardcoded nesting regardless of the annotation order you write on the method:

```
Retry ( CircuitBreaker ( RateLimiter ( TimeLimiter ( Bulkhead ( yourMethod ) ) ) ) )
```

So by default **Retry wraps CircuitBreaker** — each retry attempt is seen by the breaker, and one logical failure that is retried 3× records *3 failures* in the breaker's window, tripping it faster than you intended. Reorder via the `*AspectOrder` properties (higher value = outer) if you need the breaker to wrap the retries instead.

> [!warning] Gotcha #5 — nested retries multiply attempts
> A `@Retry(maxAttempts=3)` method that calls another `@Retry(maxAttempts=3)` method yields **9** attempts per logical call; add a client-library retry underneath and it is 27. Layered retries across a call chain multiply into a self-inflicted DDoS.
> **Mitigation:** retry at **one** layer only — usually the outermost caller of a logical operation. Turn off retries in inner clients, or budget them so the product across the chain stays ≤ 2–3.

**Spring Cloud Circuit Breaker** is a thin abstraction (`CircuitBreakerFactory`) over a provider (Resilience4j by default) for teams that want to swap implementations without touching call sites; most services use the Resilience4j annotations directly.

---

## 7. Spring Framework 7 built-in resilience (`@Retryable`, `@ConcurrencyLimit`)

> [!important] HIGH-CHURN — verify against docs.spring.io before relying on this
> New in **Spring Framework 7.0 / Spring Boot 4.x**. Details below reflect the current reference (`docs.spring.io/spring-framework/reference/core/resilience.html`, verified mid-2026). Re-check attribute names and defaults before committing to them.

Spring 7 pulls a **minimal** set of resilience primitives down into the core (`spring-core` / `spring-context`, package `org.springframework.resilience.annotation`) — inspired by the old Spring Retry project but redesigned. This means retry and concurrency throttling with **no extra dependency**. Enable it with `@EnableResilientMethods` on a `@Configuration` class, then:

```java
@Retryable(                       // NOTE: total attempts = 1 + maxRetries
    includes = MessageDeliveryException.class,
    maxRetries = 3,               // core uses maxRetries, NOT Resilience4j's maxAttempts
    delay = 100, multiplier = 2, maxDelay = 1000,   // exponential backoff
    jitter = 10)                  // milliseconds of randomness — jitter is first-class
public void sendNotification() { ... }

@ConcurrencyLimit(10)             // at most 10 concurrent invocations (a lightweight bulkhead)
public void callRateLimitedApi() { ... }
```

`@Retryable` also supports reactive return types (it decorates the Reactor pipeline) and `String` variants (`maxRetriesString`, `delayString`) for property/SpEL binding; `RetryTemplate` + `RetryPolicy` give the programmatic equivalent. `@ConcurrencyLimit(1)` effectively serialises access to the bean — a cheap throttle that pairs well with virtual threads ([[05 - Web Layer & Embedded Servers - MVC vs WebFlux]]).

> [!tip] When the built-in is enough — and when it isn't
> The core primitives cover the two most common needs (retry, concurrency cap) without a dependency. But there is **no circuit breaker, bulkhead-as-thread-pool, or rate-limiter** in core Spring 7 — for those, reach for Resilience4j. Watch the attribute mismatch: core `@Retryable` counts `maxRetries` (retries *after* the first call), while Resilience4j and Spring Retry count `maxAttempts` (total). Mixing them up silently changes your attempt count.

---

## 8. Graceful shutdown & draining in-flight requests

When Kubernetes rolls a deployment it sends `SIGTERM` and the pod stops receiving *new* traffic — but requests already in flight must be allowed to finish, or users see errors mid-deploy. Spring Boot's **graceful shutdown** does exactly this: on shutdown the server stops accepting new connections and waits (up to a grace period) for active requests to complete.

```properties
server.shutdown=graceful                              # stop accepting, drain in-flight (default is IMMEDIATE)
spring.lifecycle.timeout-per-shutdown-phase=30s       # max drain time before forceful stop

management.endpoint.health.probes.enabled=true        # expose liveness/readiness groups
management.endpoint.health.group.readiness.include=readinessState
```

The mechanism ties directly to [[12 - Actuator, Metrics & Observability]]: when shutdown begins, Spring Boot flips the **readiness** state to `REFUSING_TRAFFIC`, so `/actuator/health/readiness` returns **`OUT_OF_SERVICE` (503)**. Kubernetes sees the failing readiness probe and removes the pod from the Service endpoints — *then* the drain runs, and no new request is routed to a pod that is on its way out.

> [!warning] Gotcha #6 — not draining → dropped requests and 502s on every rolling deploy
> With the default immediate shutdown, `SIGTERM` kills the server while requests are mid-flight. The load balancer, which hasn't yet noticed the pod is gone, keeps routing to it — clients get connection resets and **502/504s on every deploy**. It looks like a flaky app; it's an un-drained shutdown.
> **Mitigation:** set `server.shutdown=graceful`; make the grace period **longer than your longest request** but shorter than Kubernetes' `terminationGracePeriodSeconds` (else the pod is `SIGKILL`ed mid-drain). Add a small `preStop` sleep so the endpoint deregistration propagates before draining begins.

> [!important] Idempotency closes the loop with retries (§3)
> Graceful shutdown reduces dropped requests but can't eliminate them; combined with client retries, a request cut off at shutdown will be retried against another pod. That is *only* safe if the operation is idempotent — the same precondition from §3 and the consumer-side de-dup in [[10 - Messaging, Events & Async]]. Resilience patterns reinforce each other; none stands alone.

---

## 9. Where to put resilience: library vs framework vs mesh

The same timeout/retry/breaker can live in the application code, the framework, or the network. They are complementary layers, not competitors.

| Approach | What it covers | Strengths | When to pick which |
|---|---|---|---|
| **Resilience4j** (library, in-app) | full set: CB, retry, bulkhead, rate limiter, time limiter, fallback | richest features; **business-aware** fallbacks; per-method tuning; works everywhere the JVM runs | any non-trivial service; when you need circuit breakers or fallbacks that return a *meaningful* degraded answer |
| **Spring Framework 7 built-in** (`@Retryable`/`@ConcurrencyLimit`) | retry + concurrency cap only | **zero extra dependency**; core-supported; reactive-aware; simplest | simple retry/throttle needs; libraries that must not impose a resilience dependency; before reaching for R4j |
| **Service mesh** (Istio/Envoy sidecar) | timeouts, retries, CB, rate limiting at the **network** layer | language-agnostic; uniform policy across a polyglot fleet; changed via config, no redeploy | platform-wide L7 defaults (mTLS, coarse timeouts/retries) across many services and languages; ops-owned policy |

> [!tip] The committed recommendation
> Put resilience at the layer that has the **context** to act on it. The **mesh** enforces coarse, uniform defaults (a global timeout, a blanket retry on 503) with no redeploy — great for a polyglot platform, but it cannot write a *business* fallback because it doesn't know your domain. The **application** (Resilience4j, or Spring 7 core for simple cases) owns anything that needs to return a meaningful degraded value or apply per-endpoint tuning. Real systems use **both**: mesh for the floor, in-app for the smart parts. And beware **double retries** — if the mesh retries *and* the app retries, you have re-created Gotcha #5 across two layers; pick one owner per concern.

---

## 10. In practice & interview talking points

**Committed best practices:**
- **Every blocking client gets a connect + read timeout (§2).** An unset timeout is infinite. Size the connection pool deliberately.
- **Retry only idempotent, transient failures — with backoff *and* jitter, small `maxAttempts`, at one layer only (§3, §6).** Never retry a non-idempotent call without an idempotency key.
- **Timeout + circuit breaker are a pair (§4).** The timeout produces the failures the breaker counts; the breaker stops the doomed calls before they exhaust the pool.
- **Bulkhead per dependency; shed load past capacity; fall back only where degraded is safe, and meter it (§5).**
- **Turn on graceful shutdown and wire readiness to it (§8)** so rolling deploys don't drop requests. Grace period < Kubernetes' `terminationGracePeriodSeconds`.
- **Version facts are volatile.** Spring Boot 4.1.x / Framework 7.0 / Jakarta EE 11 / JDK 17 baseline are current as of mid-2026, and the Framework 7 core `@Retryable`/`@ConcurrencyLimit` API is **new** — re-verify names and defaults before relying on them.

```properties
# application.properties — the production-readiness baseline
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=30s
management.endpoint.health.probes.enabled=true
management.endpoint.health.group.readiness.include=readinessState
resilience4j.circuitbreaker.instances.inventory.failure-rate-threshold=50
resilience4j.retry.instances.inventory.enable-randomized-wait=true   # jitter (§3)
```

**Interview talking points to be able to defend:**
- "The most-forgotten control is the **timeout** — an unset read timeout is infinite, and a slow dependency then exhausts my thread pool and turns their problem into my upstream outage."
- "I retry only **idempotent, transient** failures, with exponential backoff **plus jitter** — fixed retries without backoff are a retry storm that amplifies the outage I'm trying to survive."
- "A **circuit breaker** fails callers instantly while a dependency is down, which is what stops the pool exhaustion a bare timeout still allows — but a breaker needs timeouts to generate the failures it counts."
- "Resilience4j's aspect order is fixed: Retry wraps CircuitBreaker by default, so retried failures inflate the breaker's failure count — I know to reorder or account for it."
- "Spring 7 now ships `@Retryable`/`@ConcurrencyLimit` in core (verify the API), but there's still no circuit breaker there — that's where Resilience4j stays."
- "Graceful shutdown flips readiness to `OUT_OF_SERVICE` so the load balancer drains the pod before it dies — without it, every rolling deploy drops in-flight requests as 502s."
- "I decide resilience *placement* by context: the mesh for uniform L7 defaults, the app for business-aware fallbacks — never both retrying the same call."

---

## 11. Sources

- [Spring Framework Reference — Resilience Features (`@Retryable`, `@ConcurrencyLimit`, `RetryTemplate`)](https://docs.spring.io/spring-framework/reference/core/resilience.html)
- [Spring Blog — Core Spring Resilience Features: @ConcurrencyLimit, @Retryable, and RetryTemplate (2025-09-09)](https://spring.io/blog/2025/09/09/core-spring-resilience-features/)
- [Spring Boot Reference — Graceful shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html)
- [Spring Boot Reference — Application Availability & Kubernetes Probes (readiness / liveness)](https://docs.spring.io/spring-boot/reference/features/spring-application.html#features.spring-application.application-availability)
- [Spring Boot Reference — Kubernetes Probes with Actuator](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes)
- [Spring Boot Reference — REST Clients (`RestClient`, request factory settings & timeouts)](https://docs.spring.io/spring-boot/reference/io/rest-client.html)
- [Resilience4j — Getting Started with Spring Boot (annotations, config, aspect order)](https://resilience4j.readme.io/docs/getting-started-3)
- [Resilience4j — Circuit Breaker (states, sliding window, thresholds)](https://resilience4j.readme.io/docs/circuitbreaker)
- [Resilience4j — Retry (backoff, randomized wait / jitter)](https://resilience4j.readme.io/docs/retry)
- [Spring Cloud Circuit Breaker reference](https://docs.spring.io/spring-cloud-circuitbreaker/reference/)
