---
title: 05 - Web Layer & Embedded Servers — MVC vs WebFlux
tags:
  - spring
  - spring-boot
  - web-mvc
  - webflux
  - reactive
  - servlet
  - senior
aliases:
  - Servlet vs Reactive
  - WebFlux
  - Embedded Server
  - DispatcherServlet
status: ready
created: 2026-07-09
---

# Web Layer & Embedded Servers — MVC vs WebFlux

> [!abstract] Scope
> How an HTTP request actually becomes a controller call in Spring Boot — the **servlet request lifecycle** (filters → `DispatcherServlet` → handler mapping → controller → message converter), the **embedded server** that runs it (Tomcat by default), and the two competing concurrency models: **Spring MVC** (imperative, thread-per-request, servlet) versus **Spring WebFlux** (reactive, non-blocking, Netty event-loop). We settle the question every senior gets asked — *reactive or not?* — including why **virtual threads** now let you keep the simple blocking stack and still scale I/O. For the controllers and DTOs that sit at the top of this stack, see [[04 - Building REST APIs]]; for the AOT/native angle on startup, see [[14 - Performance, AOT & Native Images]].

Related: [[00 - Spring Boot Index]], [[04 - Building REST APIs]], [[14 - Performance, AOT & Native Images]]

![[request-lifecycle.gif|720]]

*An HTTP request travels the servlet filter chain, reaches the `DispatcherServlet` front controller, is routed by `HandlerMapping` to the matching `@Controller` method, whose return value is serialized back by an `HttpMessageConverter`.*

---

## 1. Two web stacks, one Boot

Spring Boot ships **two independent web frameworks**, and the classpath decides which one you get:

1. **Spring MVC** — the mature, **imperative, blocking** stack built on the **Servlet API** (`jakarta.servlet`). One request occupies one thread from start to finish. Pulled in by `spring-boot-starter-web`.
2. **Spring WebFlux** — the **reactive, non-blocking** stack built on **Reactive Streams** (Project Reactor's `Mono`/`Flux`), running by default on **Reactor Netty** with a small event-loop. Pulled in by `spring-boot-starter-webflux`.

They are not layers of each other — they are alternatives with different programming models, different servers, and different failure modes.

> [!tip] The one-sentence framing interviewers want
> "MVC is one-thread-per-request on a servlet container; WebFlux is a handful of event-loop threads that never block. MVC is simpler and correct for the vast majority of services; WebFlux trades a steep complexity increase for constant memory under massive I/O concurrency — and virtual threads now let me get most of that scaling *without* leaving the blocking model." Naming that third option is the senior signal.

> [!warning] Gotcha #0 — putting both starters on the classpath does *not* give you WebFlux
> If `spring-boot-starter-web` and `spring-boot-starter-webflux` are both present, **Boot auto-configures MVC, not WebFlux** (many teams add WebFlux only for its reactive `WebClient`). To actually run the reactive stack you must exclude the servlet starter. Assuming "I added WebFlux so I'm reactive now" is a classic misread — check which `ApplicationContext` type booted.

---

## 2. The servlet request lifecycle (Spring MVC)

This is the single most-probed topic in the module. Spring MVC is a **front-controller** design: every request funnels through one servlet, the `DispatcherServlet`, which orchestrates configurable delegates.

```text
HTTP request
  1. Servlet container (Tomcat) accepts the socket, assigns ONE worker thread
  2. Filter chain runs  ── Servlet Filters, in order (auth, CORS, logging, compression, Spring Security)
  3. DispatcherServlet (the front controller) takes over
  4. HandlerMapping     ── resolves the request to a HandlerExecutionChain
                           (the @RequestMapping method + its HandlerInterceptors)
  5. HandlerInterceptor.preHandle()  ── may short-circuit (return false)
  6. HandlerAdapter     ── binds params (@PathVariable/@RequestBody/validation), INVOKES the controller
  7. Controller method returns a value (object, ResponseEntity, view name, …)
  8. HandlerMethodReturnValueHandler picks how to render it
       └─ for @ResponseBody/@RestController → HttpMessageConverter writes the body (Jackson → JSON)
       └─ for a view name → ViewResolver renders a template
  9. HandlerInterceptor.postHandle() / afterCompletion()
 10. Response flows back OUT through the filter chain; the worker thread is RELEASED
```

The whole chain executes **on one thread**. That thread is borrowed from the server's pool at step 1 and returned at step 10 — it is **blocked for the entire request**, including any time spent waiting on a database or a downstream HTTP call. That single fact drives everything about MVC's scaling and the entire reactive/virtual-thread debate below.

Exceptions divert to a `HandlerExceptionResolver` (Boot wires `@ExceptionHandler`/`@ControllerAdvice` and the default error page — see [[04 - Building REST APIs]]).

---

## 3. Filters vs `HandlerInterceptor` — when each runs

Both let you run cross-cutting logic around a request, but they live at **different altitudes**, and picking the wrong one is a common design smell.

| | **Servlet `Filter`** | **`HandlerInterceptor`** |
|---|---|---|
| Layer | Servlet container — **outside** Spring MVC | Inside `DispatcherServlet`, **after** handler resolution |
| Sees | Raw `ServletRequest`/`ServletResponse`, every request incl. static resources | The resolved handler (controller method), `ModelAndView` |
| Hooks | `doFilter()` wrapping the whole chain | `preHandle` / `postHandle` / `afterCompletion` |
| Can it wrap/replace the request or response body? | **Yes** (it owns the stream) | No |
| Knows *which controller* will run? | No | **Yes** |
| Typical use | Security, CORS, compression, request logging, tracing, MDC | App concerns needing handler context: auth by annotation, per-endpoint audit |

`preHandle` returning `false` short-circuits the chain (the controller never runs). A subtle trap: for `@ResponseBody`/`ResponseEntity` methods the body is **already written and committed before `postHandle`**, so you cannot mutate the response there — use a `Filter` (or `ResponseBodyAdvice`) instead.

```java
@Bean
FilterRegistrationBean<CorrelationIdFilter> correlationId() {
    var reg = new FilterRegistrationBean<>(new CorrelationIdFilter());
    reg.addUrlPatterns("/api/*");
    reg.setOrder(Ordered.HIGHEST_PRECEDENCE);   // filters are ORDERED; set it explicitly
    return reg;
}
```

> [!tip] Rule of thumb
> Reach for a **Filter** when the concern is transport-level and handler-agnostic (security, CORS, tracing, gzip) or needs to touch the raw streams. Reach for a **HandlerInterceptor** only when you genuinely need to know *which controller method* is about to run. If you're unsure, it's almost always a Filter.

---

## 4. Embedded servers & the thread-per-request model

Boot embeds the server in the fat jar, so `java -jar` is the whole deployment ([[00 - Spring Boot Index]]). For the servlet stack the choices are:

| Server | Notes | Starter |
|---|---|---|
| **Tomcat 11** | **default**; Jakarta EE 11 / `jakarta.servlet`; battle-tested | `spring-boot-starter-tomcat` (transitive in `-web`) |
| **Jetty** | lightweight, good for many idle connections | `spring-boot-starter-jetty` |
| **Undertow** | low memory, high throughput, XNIO-based | `spring-boot-starter-undertow` |

Swap by excluding `-tomcat` and adding another starter (the mechanics are in [[01 - Spring Boot Fundamentals & Auto-Configuration]] §5). **[HIGH-CHURN: Tomcat 11 / Jakarta EE 11 are current for Boot 4.1.x on Framework 7 — re-verify the exact server version before relying on it.]**

**Thread-per-request sizing.** Tomcat serves requests from a **bounded worker pool** (default max **200**). Because a thread is held for the request's entire duration, peak concurrency is capped by pool size, and the sizing is governed by Little's Law: `threads ≈ throughput × average latency`. A service doing 500 req/s at 100 ms average needs ~50 busy threads; the same service talking to a downstream that slows to 2 s needs ~1000 — far past the default.

```properties
server.tomcat.threads.max=200           # worker threads (peak in-flight requests)
server.tomcat.threads.min-spare=10      # kept warm
server.tomcat.accept-count=100          # OS backlog once all threads are busy
server.tomcat.max-connections=8192      # sockets accepted before refusing
server.tomcat.connection-timeout=20s
```

> [!warning] Gotcha #1 — thread-pool exhaustion under a slow downstream
> This is the classic production outage. A downstream API or database slows from 50 ms to 3 s. Each request now pins its worker thread for 3 s; at any real traffic level **all 200 threads fill up**. New requests queue in `accept-count`, then the socket is **refused** — your *healthy* endpoints start timing out too, because they can't get a thread. One slow dependency has taken down the whole service. The blocking model couples every endpoint through one shared, finite pool.

> [!important] Mitigation — timeouts and bulkheads, not a bigger pool
> Bumping `threads.max` to 2000 just delays the cliff and burns ~1 MB of stack per platform thread. The real fixes: **aggressive client-side timeouts** on every downstream call (a call with no timeout is a latent outage), **circuit breakers / bulkheads** to isolate a failing dependency ([[14 - Performance, AOT & Native Images]] and resilience patterns), and — the structural answer — **virtual threads (§8)** so "held for 3 s" costs kilobytes instead of a scarce platform thread.

---

## 5. Spring MVC in practice

Imperative, blocking, and — for most services — exactly right. The code reads top-to-bottom; a stack trace points at your line; a debugger steps through it.

```java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final OrderService orders;                 // constructor injection (§[[02 - IoC Container, Beans & Dependency Injection]])
    OrderController(OrderService orders) { this.orders = orders; }

    @GetMapping("/{id}")
    ResponseEntity<OrderView> get(@PathVariable long id) {
        return orders.find(id)                          // BLOCKING JDBC call — thread waits here
                .map(o -> ResponseEntity.ok(OrderView.from(o)))
                .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @PostMapping
    ResponseEntity<OrderView> create(@Valid @RequestBody CreateOrder cmd) {   // validation (§[[04 - Building REST APIs]])
        Order saved = orders.place(cmd);                // blocks on the DB; that's fine on this stack
        return ResponseEntity.created(URI.create("/api/orders/" + saved.id()))
                             .body(OrderView.from(saved));
    }
}
```

The blocking `orders.find(...)` call is **not a bug here** — on the servlet stack the thread is *supposed* to block. The `@Valid` body binding, `HttpMessageConverter` JSON (de)serialization, and `ResponseEntity` status handling are all the lifecycle from §2 doing their job.

---

## 6. Spring WebFlux — the reactive stack

WebFlux is also a front-controller design (a reactive `DispatcherHandler` with the same `HandlerMapping` → `HandlerAdapter` → result-handler shape), but the programming model and the runtime are fundamentally different:

- **Return a publisher, not a value.** `Mono<T>` = 0..1 element, `Flux<T>` = 0..N. You compose a *pipeline* that describes the work; nothing runs until something subscribes (the framework subscribes for you).
- **A tiny event-loop, not a big pool.** Reactor Netty runs roughly **one event-loop thread per CPU core**. Those threads must **never block** — they hand off between many in-flight requests.
- **Backpressure is built in.** Reactive Streams lets a slow subscriber signal demand (`request(n)`) upstream, so a fast producer can't overwhelm it — the property MVC's blocking streams lack.

```java
@RestController
@RequestMapping("/api/orders")
class ReactiveOrderController {

    private final ReactiveOrderRepository orders;      // e.g. R2DBC — non-blocking all the way down
    ReactiveOrderController(ReactiveOrderRepository orders) { this.orders = orders; }

    @GetMapping("/{id}")
    Mono<ResponseEntity<OrderView>> get(@PathVariable long id) {
        return orders.findById(id)                      // returns Mono immediately; NOTHING blocks
                .map(OrderView::from)
                .map(ResponseEntity::ok)
                .defaultIfEmpty(ResponseEntity.notFound().build());
    }

    @GetMapping(value = "/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    Flux<OrderView> stream() {
        return orders.findAll().map(OrderView::from);   // streamed with backpressure, constant memory
    }
}
```

The payoff is real only when the **whole chain is non-blocking**: reactive driver (R2DBC, reactive Mongo/Redis), `WebClient` for downstream HTTP, no blocking library anywhere in the pipeline. One blocking `Repository` call in that `get()` method and the benefit evaporates — worse, it becomes the disaster in §7.

---

## 7. The cardinal sin — blocking the event loop

> [!warning] Gotcha #2 — a blocking call inside a reactive pipeline is catastrophic
> On MVC, a blocking call ties up *one* of 200 threads. On WebFlux, a blocking call — a JDBC query, a `RestTemplate` call, `Thread.sleep`, a synchronized bottleneck, even heavy CPU work — **parks one of your handful of event-loop threads**. With ~8 loop threads on an 8-core box, eight concurrent slow calls freeze the *entire* server: every connection multiplexed onto those threads stalls, throughput collapses to zero, and health checks fail. It is far more dangerous than the same mistake on MVC, and it hides — it looks fine under light load and detonates under concurrency.

```java
@GetMapping("/bad")
Mono<String> bad() {
    String s = jdbcTemplate.queryForObject(sql, String.class);  // ☠ BLOCKS an event-loop thread
    return Mono.just(s);
}
```

> [!important] Mitigation — offload, time-box, or don't go reactive at all
> Three tiers, cheapest first:
> 1. **Offload unavoidable blocking work to `Schedulers.boundedElastic()`** — a bounded, elastic pool meant exactly for wrapping legacy blocking calls, keeping them off the loop threads.
> 2. **Time-box every async step** with `.timeout(Duration.ofSeconds(2))` and a fallback, so a stalled dependency can't hang a subscription forever.
> 3. **Detect it in tests** with **BlockHound**, which instruments the JVM to throw the moment blocking code runs on a non-blocking thread.
>
> ```java
> return Mono.fromCallable(() -> jdbcTemplate.queryForObject(sql, String.class))
>            .subscribeOn(Schedulers.boundedElastic())     // off the event loop
>            .timeout(Duration.ofSeconds(2))               // bounded wait
>            .onErrorResume(ex -> Mono.just("fallback"));
> ```
>
> But note what tier 1 really is: a **thread pool bolted onto a thread-free model**. If most of your stack is blocking anyway, that's the loud signal you wanted **MVC + virtual threads (§8)**, not WebFlux.

---

## 8. Virtual threads — high I/O concurrency without reactive

Virtual threads (Project Loom, **Java 21+**) are the pragmatic answer that reshaped this whole debate. A virtual thread is a lightweight thread the JVM parks/unparks on a small pool of **carrier** platform threads whenever it blocks on I/O. You keep the simple, imperative, debuggable §5 code — but a blocked "thread" now costs **kilobytes, not a megabyte of stack**, so a service can carry **hundreds of thousands** of concurrent blocked requests.

```properties
# One line. Tomcat serves each request on a fresh virtual thread instead of a pooled platform thread.
spring.threads.virtual.enabled=true
```

```java
@SpringBootApplication
public class StoreApplication {
    public static void main(String[] args) {
        SpringApplication.run(StoreApplication.class, args);
        // With virtual threads on, the §5 blocking controller now scales like a reactive one for I/O.
    }
}
```

This directly dissolves the §4 exhaustion trap: with virtual threads there is no fixed 200-thread ceiling, so a slow downstream inflates cheap virtual threads instead of exhausting a scarce pool (you still need timeouts and circuit breakers — virtual threads make blocking *cheap*, not *free*).

> [!warning] Gotcha #3 — adopting reactive when virtual threads would do
> The most expensive architecture mistake of the last decade of Spring: choosing WebFlux for a plain CRUD-over-JDBC service "to scale." You inherit `Mono`/`Flux` everywhere, unreadable stack traces, a hostile debugger, a reactive-driver requirement for every data store, and the §7 landmine — to solve a problem you didn't have. Since Java 21, **MVC + virtual threads** gives you comparable I/O concurrency on ordinary blocking code.

> [!important] Two virtual-thread caveats to state in an interview
> **Pinning:** on Java 21–23 a virtual thread blocked *inside a `synchronized` block or a native frame* **pins** its carrier thread, defeating the benefit under contention — Java 24 largely removed the `synchronized` pin, which is why **Java 24+ is now strongly recommended**. **Lifecycle:** virtual threads are daemon threads, so a purely `@Scheduled` app can exit early; set `spring.main.keep-alive=true`. Also, thread-*pool* size properties stop applying once virtual threads are on. **[HIGH-CHURN: pinning behavior and the recommended JDK move fast — re-verify against the current JDK/Boot notes.]**

---

## 9. Graceful shutdown, CORS & static resources

**Graceful shutdown** lets in-flight requests finish when the process gets `SIGTERM` (a rolling deploy, a Kubernetes pod eviction) instead of severing them mid-response. The framework *supports* it on all three servers, but the default mode is **immediate** — you must opt in:

```properties
server.shutdown=graceful                         # drain in-flight requests (default is 'immediate')
spring.lifecycle.timeout-per-shutdown-phase=30s  # grace period before forcing termination
```

On shutdown the server stops accepting new connections, lets active requests complete within the timeout, then stops. Pair it with a readiness probe flip so the load balancer stops routing first ([[14 - Performance, AOT & Native Images]]).

**CORS** is a browser security control, configured declaratively — per-endpoint with `@CrossOrigin`, or globally via `WebMvcConfigurer#addCorsMappings`. Prefer the global registry so policy lives in one auditable place, and never pair `allowCredentials(true)` with a wildcard origin.

```java
@Configuration
class WebConfig implements WebMvcConfigurer {
    @Override public void addCorsMappings(CorsRegistry reg) {
        reg.addMapping("/api/**").allowedOrigins("https://app.acme.com")
           .allowedMethods("GET", "POST", "PUT", "DELETE").allowCredentials(true).maxAge(3600);
    }
}
```

**Static resources** are served automatically from `classpath:/static`, `/public`, `/resources`, `/META-INF/resources`, with `index.html` as the welcome page — tune via `spring.web.resources.*` and `spring.mvc.static-path-pattern`. For SPAs, static assets and the API happily coexist under one Boot app.

---

## 10. Choosing the stack: MVC vs MVC + virtual threads vs WebFlux

| Dimension | **MVC (thread-per-request)** | **MVC + virtual threads** | **WebFlux (reactive)** |
|---|---|---|---|
| Concurrency model | 1 platform thread / request, bounded pool (~200) | 1 virtual thread / request, effectively unbounded | ~1 event-loop thread / core, many requests multiplexed |
| I/O throughput ceiling | pool size ÷ latency — exhausts under slow downstreams | very high — blocked threads are cheap | very high — nothing blocks |
| Memory under load | ~1 MB stack × threads; heavy at high concurrency | low — KB per parked virtual thread | lowest — constant, few threads |
| Complexity | **lowest** — imperative, real stack traces, easy debugging | **lowest** — same code, one property | **highest** — `Mono`/`Flux`, reactive drivers, hard debugging |
| Backpressure | none | none | **first-class** (Reactive Streams demand) |
| Blocking calls | fine (expected) | fine (expected) | **forbidden on the event loop** (§7) |
| When to pick | default for most services; teams new to Spring | I/O-bound service needing high concurrency on Java 21+ | true streaming, SSE/WebSocket at scale, end-to-end reactive stack, or backpressure is a hard requirement |

> [!tip] The committed recommendation
> **Default to Spring MVC.** For an I/O-bound service that must handle high concurrency, turn on **virtual threads** — one property, same code, no reactive tax. Choose **WebFlux** deliberately, only when you have a *real* reactive need: streaming large or infinite datasets, huge numbers of long-lived connections (SSE/WebSocket), genuine backpressure requirements, or an already-reactive data layer end-to-end. "We might need to scale someday" is not that need — virtual threads cover it. And **never** mix a blocking call into a reactive pipeline; if your stack is mostly blocking, that's the tell you should have stayed on MVC.

**Committed best practices**
- **Blocking stack for blocking work** — use reactive *only* when the whole chain is non-blocking; anything less is worse than MVC.
- **Timeouts on every downstream call**, on any stack — a call without a timeout is a latent outage (§4).
- **Enable virtual threads** for I/O-bound MVC services on Java 21+ instead of inflating `threads.max`.
- **Never block the event loop** (§7); guard it with `boundedElastic`, timeouts, and BlockHound in tests.
- **Opt into graceful shutdown** (`server.shutdown=graceful`) — it is *not* on by default.
- **Global CORS config**, no `allowCredentials(true)` with a wildcard origin.

---

## 11. In practice + interview talking points

```properties
# application.properties — a pragmatic high-concurrency MVC service in 2026
server.port=8080
spring.threads.virtual.enabled=true              # Java 21+: cheap blocking, no reactive tax (§8)
spring.main.keep-alive=true                       # virtual threads are daemons (§8 caveat)
server.tomcat.threads.max=200                     # still a safety net for non-virtual paths (§4)
server.tomcat.connection-timeout=20s
server.shutdown=graceful                          # drain in-flight requests on SIGTERM (§9)
spring.lifecycle.timeout-per-shutdown-phase=30s
```

**Interview talking points to be able to defend:**
- "MVC is thread-per-request on a servlet container; the thread blocks for the whole request, so peak concurrency is `pool size ÷ latency` — which is exactly why a slow downstream exhausts the pool and takes down healthy endpoints too."
- "The request path is filters → `DispatcherServlet` → `HandlerMapping` → `HandlerAdapter` → controller → `HttpMessageConverter`; filters are container-level and handler-agnostic, interceptors run inside MVC and know the handler."
- "WebFlux runs ~one event-loop thread per core and must never block; a stray JDBC or `RestTemplate` call parks a loop thread and can freeze the whole server — offload to `boundedElastic`, time-box it, or don't go reactive."
- "Since Java 21 I reach for **MVC + virtual threads** first: I get reactive-like I/O concurrency on plain blocking code with one property and full debuggability. I pick WebFlux only for streaming, massive long-lived connections, or real backpressure."
- "Graceful shutdown isn't on by default — I set `server.shutdown=graceful` and a shutdown-phase timeout, and flip readiness first for clean rolling deploys."

---

## 12. Sources

- [Spring Boot Reference — Servlet Web Applications (Spring MVC, embedded containers, filters)](https://docs.spring.io/spring-boot/reference/web/servlet.html)
- [Spring Boot Reference — Reactive Web Applications (WebFlux, Reactor Netty)](https://docs.spring.io/spring-boot/reference/web/reactive.html)
- [Spring Boot Reference — Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html)
- [Spring Boot Reference — SpringApplication (Virtual Threads: `spring.threads.virtual.enabled`)](https://docs.spring.io/spring-boot/reference/features/spring-application.html)
- [Spring Framework Reference — DispatcherServlet (front controller, special beans, processing)](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet.html)
- [Spring Framework Reference — Interception (`HandlerInterceptor`: preHandle/postHandle/afterCompletion)](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/handlermapping-interceptor.html)
- [Spring Framework Reference — WebFlux DispatcherHandler (reactive front controller)](https://docs.spring.io/spring-framework/reference/web/webflux/dispatcher-handler.html)
- [Spring Framework Reference — CORS in Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html)
- [Spring Boot 4.0.0 available now (GA announcement, 2025-11-20)](https://spring.io/blog/2025/11/20/spring-boot-4-0-0-available-now/)
- [Spring Framework 7.0 GA (foundation for Boot 4)](https://spring.io/blog/2025/11/13/spring-framework-7-0-general-availability/)
