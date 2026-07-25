---
title: 00 - Spring Boot — Master Index
tags:
  - spring
  - spring-boot
  - java
  - learning/index
  - senior
aliases:
  - Spring Boot Index
  - Spring Boot Track
status: ready
created: 2026-07-09
---

# Spring Boot — Master Index

> [!abstract] Goal
> Everything a backend engineer needs to **build, secure, test, observe, and ship** production Spring Boot services — from *how auto-configuration actually decides which beans to create* to REST APIs, Spring Data JPA, transactions, security, messaging, caching, resilience, native images, and containerized deployment. Concept-first and interview-grade: every module teaches you to justify a choice, name the failure mode, and mitigate it — not just recite what an annotation does. Pairs with the Java language fundamentals and with [[00 - Gen AI Engineer Index]] when you build AI features on the JVM (via Spring AI, the Spring-idiomatic client for LLM providers — not yet its own track in this vault).

---

## How to use this track

You don't master Spring Boot by memorizing annotations — you master it by understanding the **container** underneath them and the **auto-configuration** that wires it. Go top-to-bottom for a full pass, or jump to the module you need. Every module follows the same through-line: **concept → how it works internally → trade-offs & alternatives → gotchas (shown failing) → mitigations → best practice → in practice → sources.**

> [!important] The through-line every module answers
> What it is → the trade-offs → **when NOT to use it** → the failure mode → the committed recommendation. That is exactly what a senior Spring interview probes: not "what is `@Transactional`" but "what happens when you call a `@Transactional` method from within the same class, and why."

> [!warning] Versions here are HIGH-CHURN — re-verify before relying on them
> This track is written against **Spring Boot 4.1.x** on **Spring Framework 7.0**, **Jakarta EE 11** (Tomcat 11, Hibernate ORM 7, Hibernate Validator 9), **Jackson 3**, **JUnit 6**, with a **JDK 17 baseline** (Java 21/25 recommended). Spring Boot 4.0 went GA on **2025-11-20**. The *concepts* (IoC, the bean lifecycle, the filter chain, transaction propagation, the N+1 problem) are durable; the *coordinates* (version numbers, property keys, deprecations like `RestTemplate`) move every release. Each module flags its volatile facts — check them against the primary docs. Today's date context: mid-2026.

> [!important] Three concerns that run through EVERY module (the spine)
> 1. **Auto-configuration & "convention over configuration"** — Boot's defining trait. You must know *what* it auto-configures and *how to override or disable it*, or you'll fight the framework. See [[01 - Spring Boot Fundamentals & Auto-Configuration]].
> 2. **The container & bean lifecycle** — everything is a bean; DI, scopes, and proxies underlie transactions, security, caching, and `@Async`. Half of "why doesn't my annotation work?" is a proxy/self-invocation issue. See [[02 - IoC Container, Beans & Dependency Injection]].
> 3. **Production-readiness** — security, observability, resilience, and graceful shutdown are not afterthoughts; they are covered as first-class modules ([[08 - Spring Security]], [[12 - Actuator, Metrics & Observability]], [[13 - Resilience & Production Readiness]]).

---

## Curriculum

| # | Module | Core question | Animated? | Status |
|---|--------|--------------|:---:|--------|
| 01 | [[01 - Spring Boot Fundamentals & Auto-Configuration]] | starters, `@SpringBootApplication`, how auto-config decides which beans to create | 🎞️ | `ready` |
| 02 | [[02 - IoC Container, Beans & Dependency Injection]] | ApplicationContext, bean scopes, lifecycle, injection styles, proxies | 🎞️ | `ready` |
| 03 | [[03 - Configuration, Profiles & Externalized Config]] | property sources, `@ConfigurationProperties`, profiles, relaxed binding | 🎞️ | `ready` |
| 04 | [[04 - Building REST APIs]] | `@RestController`, validation, content negotiation, error handling, versioning | 🎞️ | `ready` |
| 05 | [[05 - Web Layer & Embedded Servers - MVC vs WebFlux]] | filter chain, DispatcherServlet, Servlet vs reactive, virtual threads | 🎞️ | `ready` |
| 06 | [[06 - Data Access with Spring Data JPA]] | repositories, entities, the persistence context, N+1, pagination | 🎞️ | `ready` |
| 07 | [[07 - Transactions & Data Consistency]] | `@Transactional`, propagation, isolation, rollback rules, self-invocation | 🎞️ | `ready` |
| 08 | [[08 - Spring Security]] | the security filter chain, authN vs authZ, JWT/OAuth2, method security | 🎞️ | `ready` |
| 09 | [[09 - Caching]] | the cache abstraction, `@Cacheable`, Redis/Caffeine, invalidation, stampede | 🎞️ | `ready` |
| 10 | [[10 - Messaging, Events & Async]] | app events, `@Async`, `@Scheduled`, Kafka/RabbitMQ, at-least-once delivery | 🎞️ | `ready` |
| 11 | [[11 - Testing Spring Boot Applications]] | test slices, `@SpringBootTest`, MockMvc, Testcontainers, the test pyramid | 🎞️ | `ready` |
| 12 | [[12 - Actuator, Metrics & Observability]] | endpoints, Micrometer, tracing, health, the observability pipeline | 🎞️ | `ready` |
| 13 | [[13 - Resilience & Production Readiness]] | retries, circuit breakers, timeouts, bulkheads, graceful shutdown | 🎞️ | `ready` |
| 14 | [[14 - Performance, AOT & Native Images]] | AOT processing, GraalVM native, CRaC, virtual threads, startup vs throughput | 🎞️ | `ready` |
| 15 | [[15 - Packaging, Containers & Deployment]] | executable/layered jars, buildpacks, Docker, config in Kubernetes | 🎞️ | `ready` |

---

## Suggested order

**Foundations** (01–03) → **Web** (04–05) → **Data** (06–07) → **Cross-cutting** (08–10) → **Quality & operations** (11–13) → **Ship it** (14–15). If you only do six before an interview: **01, 02, 06, 07, 08, 12** — the container, persistence, transactions, security, and observability are where senior questions concentrate and where production incidents actually come from.

---

## How this fits the rest of the vault

```text
JAVA LANGUAGE + JVM                    the language, memory model, concurrency
        +
SPRING FRAMEWORK (core)                IoC container, AOP, the bean model
        ▼
SPRING BOOT (this track)               auto-configuration, starters, the
                                       production-ready opinionated stack
        +
SPRING DATA / SECURITY / etc.          the ecosystem modules layered on top
        ▼
SPRING AI  ───────────────────────►    building LLM features on the JVM
                                       (bridges to [[00 - Gen AI Engineer Index]])
```

Spring Boot is *Spring Framework with opinions*: the container, DI, and AOP are Framework; the auto-configuration, starters, embedded server, and Actuator are Boot. Keeping that line straight is itself an interview signal.

---

## Anchor sources (re-verify — they move every release)

- Spring Boot reference: [docs.spring.io/spring-boot](https://docs.spring.io/spring-boot/index.html) · [Spring Boot 4.0 Release Notes](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Release-Notes) · [Spring Boot 4.0.0 announcement](https://spring.io/blog/2025/11/20/spring-boot-4-0-0-available-now/)
- Spring Framework: [reference docs](https://docs.spring.io/spring-framework/reference/) · [Framework 7.0 GA](https://spring.io/blog/2025/11/13/spring-framework-7-0-general-availability/)
- Ecosystem: [Spring Data JPA](https://docs.spring.io/spring-data/jpa/reference/) · [Spring Security](https://docs.spring.io/spring-security/reference/) · [Micrometer](https://docs.micrometer.io/) · [Testcontainers](https://java.testcontainers.org/)
- HTTP clients direction: [The state of HTTP clients in Spring (2025)](https://spring.io/blog/2025/09/30/the-state-of-http-clients-in-spring/)

> [!note] On the diagrams
> Animated GIFs are generated by `assets/gen_springboot_gifs.py` (Pillow, via the `animated-diagrams` skill engine). Re-run it to tweak a figure. Obsidian animates GIFs in reading view (animated SVG renders frozen and Mermaid is static, so GIF is used for anything that *moves*).
