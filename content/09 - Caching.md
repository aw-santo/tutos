---
title: Caching
tags:
  - spring
  - spring-boot
  - caching
  - redis
  - performance
  - senior
aliases:
  - Cache Abstraction
  - Cacheable
  - Caching
status: ready
created: 2026-07-09
---

# Caching

> [!abstract] Scope
> Spring's **cache abstraction** — a provider-agnostic layer that turns "check the cache, call the method on a miss, store the result" into three annotations (`@Cacheable`/`@CachePut`/`@CacheEvict`) driven by the same proxy machinery as [[02 - IoC Container, Beans & Dependency Injection]]. We cover how keys are generated, how Spring Boot auto-selects a provider (`ConcurrentMap` → Caffeine → Redis), the **local vs distributed** trade-off, TTL/eviction, invalidation strategies, and the failure modes that separate a cache that helps from one that leaks data, blows up memory, or serves stale results. For the data layer it usually sits in front of, see [[06 - Data Access with Spring Data JPA]]; for its role in keeping a service responsive under load, see [[13 - Resilience & Production Readiness]].

Related: [[00 - Spring Boot Index]], [[06 - Data Access with Spring Data JPA]], [[13 - Resilience & Production Readiness]]

---

## 1. The abstraction: caching as an aspect, not a data structure

The cache abstraction (in Spring Framework since 3.1) is deliberately *not* a cache. It is a thin, provider-agnostic SPI plus an AOP interceptor that applies caching **declaratively** to method calls — the same way transactions are applied. You annotate a method; a proxy wraps it; on each call the proxy consults a `Cache`, and only invokes your method on a miss. Your business code never touches the store.

Two interfaces are the entire SPI:

| SPI type | Role |
|---|---|
| `CacheManager` | resolves a named cache — `cacheManager.getCache("books")` |
| `Cache` | one named region: `get(key)`, `put(key, value)`, `evict(key)`, `clear()` |

Everything else — Caffeine, Redis, Hazelcast, a `ConcurrentHashMap` — is a backend behind those two interfaces. That is the point: switch providers by changing a dependency and a property, not your code.

```java
@Configuration
@EnableCaching                       // turns on the caching interceptor (proxy) — REQUIRED
public class CacheConfig { }
```

> [!tip] The one-sentence framing interviewers want
> "Spring caching is an AOP aspect over method calls, not a cache implementation — `@Cacheable` means *memoize this method keyed by its arguments*, and the abstraction lets me swap Caffeine for Redis without touching the annotated code." Naming that the annotations do nothing without `@EnableCaching` (there's no proxy otherwise) is the first senior signal.

---

## 2. The annotation vocabulary

Three verbs cover almost everything; two helpers compose and share config.

| Annotation | Behaviour | Method invoked? |
|---|---|---|
| `@Cacheable` | look up by key; on hit return cached value, on miss call the method **and** store the result | only on a miss |
| `@CachePut` | always call the method, then store the result under the key | always |
| `@CacheEvict` | remove one key (or `allEntries=true` to clear the region) | always |
| `@Caching` | group several of the above on one method (e.g. evict two regions) | — |
| `@CacheConfig` | class-level defaults (`cacheNames`, `keyGenerator`) shared by all methods | — |

```java
@Service
@CacheConfig(cacheNames = "books")
public class BookService {

    @Cacheable(key = "#isbn")                       // read-through: cache on miss
    public Book findByIsbn(String isbn) { return repo.load(isbn); }

    @CachePut(key = "#book.isbn")                   // write-through: refresh the entry
    public Book update(Book book) { return repo.save(book); }

    @CacheEvict(key = "#isbn")                       // invalidate on delete
    public void delete(String isbn) { repo.remove(isbn); }
}
```

> [!warning] `@CachePut` and `@Cacheable` on the same method are a bug
> `@Cacheable` skips the method on a hit; `@CachePut` always runs it. Put both on one method and their behaviours contradict — the method may or may not run depending on interceptor ordering, giving nondeterministic results. Use `@Cacheable` for reads and `@CachePut` only to *refresh* an entry you're also persisting.

> [!important] `beforeInvocation` on eviction
> `@CacheEvict` evicts **after** the method returns by default, so if the method throws, the stale entry survives. For a delete/invalidate where you must clear the cache even on failure, set `@CacheEvict(beforeInvocation = true)`.

---

## 3. Keys, conditions, and `sync`

**Default key.** With no `key`, Spring's `SimpleKeyGenerator` builds the key from the method arguments: no args → a shared `SimpleKey.EMPTY`; one arg → that argument itself; several → a `SimpleKey` wrapping them all. This works **only if every argument has correct `equals`/`hashCode`**.

**Custom key (SpEL).** `key` is a SpEL expression evaluated against a root that exposes `#root.methodName`, `#root.target`, `#root.args`, the argument names (`#isbn`, or `#p0`/`#a0` by index), and — in `unless` and key expressions after invocation — `#result`.

**`condition` vs `unless`.** `condition` (evaluated *before* the call) decides whether caching applies at all; `unless` (evaluated *after*, sees `#result`) vetoes storing a particular result.

```java
@Cacheable(cacheNames = "books",
           key = "#isbn",
           condition = "#isbn.length() == 13",     // only cache well-formed ISBNs
           unless = "#result == null || #result.outOfPrint")  // don't cache these
public Book findByIsbn(String isbn) { ... }
```

**Custom `KeyGenerator`.** For composite or normalized keys, implement `KeyGenerator` and reference it by bean name (`keyGenerator = "..."`) instead of hand-writing fragile SpEL everywhere.

> [!warning] Gotcha #1 — per-user data under a shared key → cross-user leak
> The single most dangerous caching bug: caching user-scoped data without the user in the key.
> ```java
> @Cacheable("profile")                 // key = SimpleKey.EMPTY — ONE entry for EVERYONE
> public Profile currentProfile() { return lookup(SecurityContextHolder...); }
> ```
> The first user populates the cache; every subsequent user gets **that user's profile**. This is a data-breach-class bug that passes every functional test run by a single user.
> **Mitigation:** include the principal in the key — `key = "#userId"` — or, better, do not cache request/security-scoped results at method level at all. If the cache key can't fully identify the value, it is the wrong key.

> [!warning] Gotcha #2 — caching a mutable object, then mutating it
> `@Cacheable` stores a **reference** for in-memory providers (Caffeine, `ConcurrentMap`). A caller that mutates the returned object mutates the *cached* object — every later reader sees the change, and it was never persisted.
> **Mitigation:** cache immutable values (records, defensive copies), or use a serializing provider (Redis) where each `get` deserializes a fresh instance. Treat cached objects as read-only by contract.

> [!tip] `sync = true` for expensive misses
> `@Cacheable(sync = true)` tells the provider to lock the key while one thread computes the value; concurrent callers for the same key **wait** for that single computation instead of all stampeding the method (§8). Support is provider-dependent (Caffeine yes; the simple provider yes; not every JCache backend). Use it on hot, expensive keys.

---

## 4. Providers & how Spring Boot auto-selects one

You do not build a `CacheManager` by hand unless you need to. If you *don't* define one, Boot detects a provider from the classpath and configures it. Detection runs in a fixed priority order — **Generic → JCache (EhCache/Hazelcast/Infinispan) → Hazelcast → Infinispan → Couchbase → Redis → Caffeine → Cache2k → Simple** — and stops at the first available. With no cache library present, the **Simple** provider (a `ConcurrentHashMap`) wins as the fallback.

`spring.cache.type` forces or disables a provider explicitly:

```properties
# Force a specific backend (values: generic, jcache, hazelcast, infinispan,
#   couchbase, redis, caffeine, cache2k, simple, none)
spring.cache.type=redis
# spring.cache.type=none                # no-op cache — handy to disable caching in tests
spring.cache.cache-names=books,authors  # pre-create these caches at startup
```

| Provider | Backing store | Character |
|---|---|---|
| `simple` (default) | `ConcurrentHashMap` | zero-config, **unbounded, no TTL** — dev/test only |
| `caffeine` | in-process Caffeine cache | local, size- and time-bounded, fastest |
| `redis` | external Redis | distributed, shared across instances, network-bound |

> [!warning] Gotcha #3 — the default `simple` cache is unbounded → OutOfMemory
> The `ConcurrentHashMap` behind the default provider has **no maximum size and no TTL**. Cache a method keyed by something high-cardinality (user IDs, search queries) and the map grows without limit until the heap dies with `OutOfMemoryError` — typically in production, under real traffic, long after tests passed.
> **Mitigation:** never ship the simple provider for anything user-facing. Move to Caffeine with an explicit `maximumSize`/`expireAfter` (§6), or Redis with a TTL. Treat "unbounded cache" as a memory leak, because it is one.

---

## 5. Local (Caffeine) vs distributed (Redis) vs no cache

This is the core design decision, and the comparison interviewers push on.

| | **Caffeine (local)** | **Redis (distributed)** | **No cache** |
|---|---|---|---|
| Location | in the JVM heap | external server / cluster | — |
| Access latency | nanoseconds (no network) | ~sub-ms + network hop | source latency every call |
| Shared across instances? | **No** — each node has its own copy | **Yes** — one source of truth | n/a |
| Consistency across nodes | can diverge; each evicts independently | consistent; one entry for all | always fresh |
| Survives a restart? | No (in-heap) | Yes (separate process) | n/a |
| Memory cost | consumes app heap | offloads to Redis | none |
| Failure blast radius | isolated to one JVM | Redis outage hits everyone | none |
| Extra ops? | none | run/operate Redis | none |
| **When to pick** | small, hot, read-mostly, per-node tolerable staleness (reference data, config, computed lookups) | data shared across instances, must be consistent, or too large for heap (sessions, API responses, expensive aggregates) | writes ≈ reads, strong-consistency required, or the source is already fast (§10) |

> [!tip] The committed recommendation
> Default to **Caffeine** for local, read-mostly reference data — it's the lowest-latency, lowest-ops option and needs no infrastructure. Reach for **Redis** the moment the cached value must be *consistent across instances* (you'd otherwise get different answers per node) or is *too big for the heap*. A common senior pattern is **two tiers**: Caffeine as an L1 in front of Redis as an L2 — but only add the second tier when profiling shows the network hop is the bottleneck, not by default.

---

## 6. TTL, eviction & size limits

An in-memory cache without a bound is a leak (§4); the provider is where you set the bound.

**Caffeine** — configure via one spec string or a `Caffeine` builder bean:

```properties
# maximumSize = LRU-style eviction cap; expireAfterWrite/Access = TTL
spring.cache.caffeine.spec=maximumSize=10000,expireAfterWrite=10m,recordStats
```

**Redis** — TTL and null-handling via properties, or a `RedisCacheConfiguration` bean for per-cache tuning:

```properties
spring.cache.redis.time-to-live=10m
spring.cache.redis.cache-null-values=true   # see §9
spring.cache.redis.key-prefix=app::         # namespace keys to avoid collisions
spring.cache.redis.use-key-prefix=true
```

Two eviction axes to keep straight: **size-based** (Caffeine's `maximumSize`, evicts least-valuable entries when full) and **time-based** (`expireAfterWrite`/`time-to-live`, entries die after a fixed age). `expireAfterWrite` bounds staleness; `expireAfterAccess` keeps hot keys alive and drops idle ones. Redis TTL additionally frees memory server-side.

> [!important] Always bound both size and time
> Set a `maximumSize` (or Redis `maxmemory` + eviction policy) *and* a TTL. Size alone lets a stale entry live forever if it stays hot; TTL alone lets an unbounded key space exhaust memory before anything expires. Every production cache needs both a ceiling and an expiry.

---

## 7. Invalidation strategies & consistency

A cache is a *copy*; correctness is entirely about when the copy is refreshed or discarded. Two patterns dominate:

- **Cache-aside (lazy / read-through):** on read, check cache → on miss load from source and populate. On write, **evict** the key so the next read reloads. This is the default `@Cacheable` + `@CacheEvict` shape — simple, and the cache only holds what's actually read.
- **Write-through:** on write, update the source **and** the cache in the same operation (`@CachePut`). The cache is always warm for that key, at the cost of caching data that may never be read.

```java
@CachePut(key = "#book.isbn")            // write-through: DB + cache updated together
public Book update(Book book) { return repo.save(book); }

@CacheEvict(key = "#isbn")               // cache-aside invalidation on delete
public void delete(String isbn) { repo.remove(isbn); }
```

> [!warning] Gotcha #4 — stale reads because nothing invalidates
> `@Cacheable` on the read path with no `@CacheEvict`/`@CachePut` on the write path (or writes that bypass the service — direct SQL, another service, a batch job) means the cache **never learns the source changed**. Reads serve the stale value until the TTL expires — minutes or hours of wrong data, and it looks like a "database bug."
> **Mitigation:** pair every cached read with an invalidation on every write path, and treat **any out-of-band writer** as a reason to shorten the TTL or publish an eviction event. If you cannot invalidate, a short TTL is your only bound on staleness — choose it deliberately.

> [!tip] Accept staleness explicitly
> A cache trades freshness for latency. Decide the acceptable staleness window per use case and encode it as the TTL: a currency rate might tolerate 60s, a product catalogue an hour, a user's permissions perhaps nothing (don't cache it). "How stale can this be?" is a design input, not an afterthought.

---

## 8. The self-invocation gotcha (again)

Caching is proxy-based, exactly like `@Transactional` ([[02 - IoC Container, Beans & Dependency Injection]]). The interceptor lives on the **proxy** Spring injects into other beans. A call from **inside** the same bean goes through `this`, not the proxy — so the caching advice never runs.

```java
@Service
public class ReportService {

    public Report daily(String id) {
        return computeExpensive(id);      // internal call via `this` — NOT cached!
    }

    @Cacheable("reports")
    public Report computeExpensive(String id) { ... }   // proxy bypassed
}
```

`daily()` recomputes every time; the `@Cacheable` on `computeExpensive` is silently dead because the call never left the object to pass through the proxy.

> [!warning] Gotcha #5 — internal calls silently skip the cache
> This is identical to the `@Transactional` self-invocation trap and just as invisible — no error, the method simply runs uncached every time, and you "discover" it when the cache hit-rate metric is zero.
> **Mitigation:** call the cached method from a *different* bean, or split the cached method into its own service. Last resort: inject a self-reference / use `AopContext.currentProxy()`. The clean fix is almost always to move the cached method to the boundary where callers are external.

---

## 9. Failure modes on the hot path: stampede & penetration

**Cache stampede (thundering herd).** A hot key expires; N concurrent requests all miss simultaneously and all hit the database (or downstream service) at once — the load spike the cache existed to prevent, delivered precisely when the cache is empty.

**Cache penetration.** Requests for keys that don't exist (missing IDs, garbage from a scanner) always miss and always hit the source, because a *miss* isn't cached — the cache provides zero protection against lookups for absent data.

> [!warning] Gotcha #6 — a hot key expires and the herd hits the database
> On a high-traffic key, TTL expiry turns one cache miss into thousands of simultaneous source calls. Under load this cascades into connection-pool exhaustion and timeouts — the classic "the site fell over at exactly the top of the hour when everything expired together."

> [!tip] Stampede mitigations, in order of reach-for
> - **`sync = true`** (§3): one thread computes, the rest wait — the simplest fix for a single instance.
> - **TTL jitter:** add a random spread (e.g. `10m ± 90s`) so keys don't expire in lockstep; prevents synchronized mass-expiry.
> - **Distributed lock** (Redis): across instances, let one node recompute while others serve the old value or wait — needed when `sync` (per-JVM) isn't enough.
> - **Refresh-ahead:** Caffeine's `refreshAfterWrite` reloads a hot key *in the background* before it expires, so readers never see a miss.

> [!tip] Negative caching defeats penetration
> Cache the *absence* of a value — store a null/sentinel for missing keys with a **short** TTL. Spring Boot's Redis cache does this by default (`spring.cache.redis.cache-null-values=true`); combine with `unless = "#result == null"` only when you deliberately *don't* want to cache nulls. Keep the negative TTL short so a later-created entity isn't masked by a cached "not found."

---

## 10. Redis serialization concerns

Redis stores bytes, so every cached object is **serialized on `put` and deserialized on `get`** — a source of subtle production breakage that in-memory providers don't have.

By default, `RedisCacheConfiguration.defaultCacheConfig()` serializes **keys with `StringRedisSerializer`** and **values with `JdkSerializationRedisSerializer`** (Java native serialization). JDK serialization requires every cached type to implement `Serializable`, produces opaque binary blobs, and — worst of all — **breaks across class changes**: add or rename a field and old cached entries fail to deserialize.

```java
@Bean
RedisCacheConfiguration cacheConfiguration() {
    return RedisCacheConfiguration.defaultCacheConfig()
        .entryTtl(Duration.ofMinutes(10))
        .disableCachingNullValues()
        .serializeValuesWith(SerializationPair.fromSerializer(
            new GenericJackson2JsonRedisSerializer()));   // human-readable JSON
}
```

> [!warning] Gotcha #7 — a deploy changes a class and cached entries won't deserialize
> Whether JDK- or JSON-serialized, entries written by the *old* code can fail to deserialize under the *new* class shape after a rolling deploy — throwing `SerializationException` on read, often only for a subset of keys, until the TTL flushes them. JDK serialization is especially brittle (it keys on `serialVersionUID`).
> **Mitigation:** prefer a JSON serializer (`GenericJackson2JsonRedisSerializer`) for readability and looser compatibility; make DTOs additive (don't rename/remove fields); **version the cache key or key-prefix** on breaking model changes so new code reads a fresh namespace; and cache purpose-built DTOs, not JPA entities (whose lazy proxies serialize terribly). **[HIGH-CHURN: Spring Data Redis 4.x is renaming/deprecating some Jackson serializer classes — verify the exact serializer type name against the current reference before relying on it.]**

---

## 11. When NOT to cache & caveats (summary)

- **Don't cache write-heavy or rapidly-changing data.** If writes rival reads, you spend more on invalidation than you save on hits, and staleness risk dominates.
- **Don't cache when the source is already fast.** An indexed single-row primary-key lookup is often cheaper than a Redis round-trip; measure before adding a cache.
- **Don't cache security-scoped data under a shared key (§3).** Get the key wrong and it's a data breach, not a bug.
- **Bound every cache — size *and* time (§6).** Unbounded is a memory leak (§4).
- **Pair every cached read with invalidation on every write path (§7);** account for out-of-band writers.
- **Cache immutable DTOs, not mutable entities (§3, §10).** Reference sharing and lazy proxies both bite.
- **Version facts are volatile.** Spring Boot 4.1.x / Framework 7.0 / Spring Data Redis 4.1.x / Jakarta EE 11 / JDK 17 baseline are current as of mid-2026 — **re-verify** exact property keys and serializer class names before relying on them.

---

## 12. In practice

```java
// A caching service done right: bounded, invalidated, stampede-safe, DTO-based.
@Service
@CacheConfig(cacheNames = "products")
public class ProductService {

    @Cacheable(key = "#id", sync = true,            // §8 stampede guard on a hot key
               unless = "#result == null")           // §9 don't cache misses here
    public ProductDto find(String id) {              // returns an immutable DTO (§3)
        return mapper.toDto(repo.findById(id).orElse(null));
    }

    @CachePut(key = "#dto.id")                        // §7 write-through keeps entry warm
    public ProductDto update(ProductDto dto) { return mapper.toDto(repo.save(...)); }

    @CacheEvict(key = "#id", beforeInvocation = true) // §2 evict even if delete throws
    public void delete(String id) { repo.deleteById(id); }
}
```

```properties
# application.properties — Redis-backed, bounded, JSON-serialized (via a config bean)
spring.cache.type=redis
spring.cache.cache-names=products,catalog
spring.cache.redis.time-to-live=10m
spring.cache.redis.key-prefix=app::
# For local reference data instead, swap to Caffeine:
# spring.cache.type=caffeine
# spring.cache.caffeine.spec=maximumSize=10000,expireAfterWrite=10m,recordStats
```

**Interview talking points to be able to defend:**
- "Spring caching is an AOP aspect over method calls — `@Cacheable` memoizes by arguments, and nothing works without `@EnableCaching` because there's no proxy otherwise."
- "Boot auto-selects a provider by classpath priority; the default `simple` `ConcurrentHashMap` is unbounded, so it's dev-only — production needs Caffeine or Redis with a size *and* time bound."
- "Caffeine when it's local, hot, read-mostly and per-node staleness is fine; Redis when the value must be consistent across instances or is too big for the heap."
- "The self-invocation trap is identical to `@Transactional`: an internal call skips the proxy, so the cache silently never fires."
- "The scary bugs are per-user data under a shared key (cross-user leak) and a stampede when a hot key expires — I mitigate with correct keys, `sync=true`, TTL jitter, and negative caching."
- "Redis serializes entries, so I cache DTOs not entities, prefer JSON over JDK serialization, and version the key-prefix on breaking model changes."

---

## Sources

- [Spring Framework Reference — Cache Abstraction (`@EnableCaching`, `Cache`/`CacheManager` SPI)](https://docs.spring.io/spring-framework/reference/integration/cache.html)
- [Spring Framework Reference — Declarative annotation-based caching (`@Cacheable`/`@CachePut`/`@CacheEvict`, key/condition/unless/sync)](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Boot Reference — Caching (provider auto-selection, `spring.cache.*` properties)](https://docs.spring.io/spring-boot/reference/io/caching.html)
- [Spring Data Redis Reference — Redis Cache (serializers, TTL, null values, key prefix)](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html)
- [Spring Boot 4.0.0 available now (GA announcement, 2025-11-20)](https://spring.io/blog/2025/11/20/spring-boot-4-0-0-available-now/)
- [Spring Framework 7.0 GA (foundation for Boot 4)](https://spring.io/blog/2025/11/13/spring-framework-7-0-general-availability/)
