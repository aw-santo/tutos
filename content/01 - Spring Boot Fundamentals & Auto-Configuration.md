---
title: 01 - Spring Boot Fundamentals & Auto-Configuration
tags:
  - spring
  - spring-boot
  - auto-configuration
  - starters
  - senior
aliases:
  - Auto-Configuration
  - SpringBootApplication
  - Spring Boot Starters
status: ready
created: 2026-07-09
---

# Spring Boot Fundamentals & Auto-Configuration

> [!abstract] Scope
> What Spring Boot actually *is* on top of the Spring Framework — starters, `@SpringBootApplication`, the embedded server, and above all **auto-configuration**: the mechanism that inspects your classpath and configuration and registers sensible beans so you don't have to. We go past "it just works" to *how* it decides (the `@Conditional` model and the `AutoConfiguration.imports` file), *how the app boots* (`SpringApplication.run`), *how to override or disable* any of it, and the classpath/placement/versioning footguns that bite in production. For the container those beans live in, see [[02 - IoC Container, Beans & Dependency Injection]]; for the property system auto-config reads, see [[03 - Configuration, Profiles & Externalized Config]].

Related: [[00 - Spring Boot Index]], [[02 - IoC Container, Beans & Dependency Injection]], [[03 - Configuration, Profiles & Externalized Config]], [[15 - Packaging, Containers & Deployment]]

![[springboot-autoconfig.gif|720]]

*A starter puts libraries on the classpath; each auto-configuration class is guarded by `@Conditional` checks; the ones whose conditions pass contribute beans to the `ApplicationContext` — beans you never declared, and can still override.*

---

## 1. The concept: Spring Framework *with opinions*

Spring **Framework** gives you the IoC container, dependency injection, and AOP — but wiring a web app by hand (a `DispatcherServlet`, a view resolver, a `DataSource`, a connection pool, a JSON message converter, an embedded server) is dozens of boilerplate `@Bean` methods before you write a line of business logic. Spring **Boot** is a layer on top that makes three opinionated moves:

1. **Starters** — curated, version-aligned dependency bundles. One `spring-boot-starter-web` pulls in Spring MVC, Jackson, validation, and an embedded Tomcat, all at mutually-compatible versions.
2. **Auto-configuration** — at startup, Boot looks at what's on the classpath and what you've configured, and registers the beans a typical app of that shape needs — *unless you've already defined your own*.
3. **Production-ready & standalone** — an embedded server so the artifact is a runnable `java -jar` fat jar (no external app server), plus Actuator for health/metrics/observability out of the box ([[12 - Actuator, Metrics & Observability]]).

> [!tip] The one-sentence framing interviewers want
> "Spring Boot is convention-over-configuration for Spring: it doesn't add new DI or AOP — it *pre-wires the container* based on your classpath, and every default is one you can override." Keeping the Framework/Boot line straight is itself a senior signal — DI, scopes, and AOP are **Framework**; starters, auto-config, the embedded server, and Actuator are **Boot**.

---

## 2. `@SpringBootApplication`: three annotations in one

The single annotation on your main class is a meta-annotation composing three:

```java
@SpringBootApplication          // = the three below, with sensible defaults
public class StoreApplication {
    public static void main(String[] args) {
        SpringApplication.run(StoreApplication.class, args);
    }
}
```

| Composed annotation | What it does |
|---|---|
| `@SpringBootConfiguration` | a specialization of `@Configuration` — marks this as the primary config class (and lets tests find it) |
| `@EnableAutoConfiguration` | switches on the auto-configuration machinery (§3) |
| `@ComponentScan` | scans **the package of this class and its sub-packages** for `@Component`/`@Service`/`@Repository`/`@Controller` |

You can tune it: `@SpringBootApplication(scanBasePackages = "com.acme", exclude = DataSourceAutoConfiguration.class)`.

> [!warning] Gotcha #1 — main class placement silently breaks component scanning
> `@ComponentScan` (with no explicit base package) scans **downward from the package of the annotated class**. Put `StoreApplication` in `com.acme.app` while your services live in `com.acme.services`, and those beans are **never found** — you get `NoSuchBeanDefinitionException` or a null autowired field, with no error at startup pointing at the cause. This is the single most common "why isn't my bean picked up?" for beginners.
> **Mitigation:** put the main class in the **root package**, above every other package (`com.acme`), so the whole tree is scanned. If you can't, set `scanBasePackages` explicitly. Never leave it to chance.

---

## 3. How auto-configuration actually works

This is the heart of the module and the most-probed topic. Auto-configuration is *not* magic and *not* reflection scanning your whole classpath at random — it is a deterministic, ordered, condition-gated bean-registration pass.

**The mechanism, step by step:**

1. `@EnableAutoConfiguration` imports a selector that reads every JAR's `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` file — a plain newline-delimited list of auto-configuration class names. (This replaced the old `spring.factories` `EnableAutoConfiguration` key; that key was deprecated in Boot 2.7 and **removed in 3.0**. If you maintain a custom starter, you must use the `.imports` file.)
2. Each listed class is a `@AutoConfiguration` (a `@Configuration` variant) whose `@Bean` methods are guarded by **`@Conditional`** annotations.
3. Spring evaluates the conditions **against the current classpath, environment, and already-registered beans**. A class or bean method whose conditions fail is silently skipped — it "backs off."
4. Ordering matters: `@AutoConfiguration(after = ..., before = ...)` sequences them so, e.g., your custom `DataSource` is seen *before* JPA auto-config decides whether to create one.

**The condition vocabulary you must know:**

| Condition | Fires the bean when… | Typical use |
|---|---|---|
| `@ConditionalOnClass` | a class is **on the classpath** | "only configure Jackson if Jackson is present" |
| `@ConditionalOnMissingClass` | a class is **absent** | fallback wiring |
| `@ConditionalOnBean` | a bean of a type **already exists** | build on top of another bean |
| `@ConditionalOnMissingBean` | **no** such bean exists yet | *the* back-off mechanism — "only if the user didn't define their own" |
| `@ConditionalOnProperty` | a property has a given value | feature flags (`spring.cache.type=redis`) |
| `@ConditionalOnWebApplication` | it's a servlet/reactive web app | web-only beans |
| `@ConditionalOnExpression` | a SpEL expression is true | complex predicates |

> [!important] `@ConditionalOnMissingBean` is *why* your beans win
> The reason "just declare your own `@Bean` and Boot steps aside" works is that nearly every auto-configured bean is annotated `@ConditionalOnMissingBean`. Boot registers your beans first, then auto-config runs and sees yours already there, so its condition fails and it backs off. **Override precedence is a feature of the condition system, not a special case.** Understanding this turns "I fought the framework for a day" into a five-minute change.

---

## 4. The boot sequence: what `SpringApplication.run` does

Knowing the phases lets you hook the right extension point instead of guessing.

```text
SpringApplication.run(App.class, args)
  1. Create a BootstrapContext; fire ApplicationStartingEvent
  2. Prepare the Environment  ── loads application.yml/properties, profiles, env vars, CLI args (§[[03 - Configuration, Profiles & Externalized Config]])
  3. Print the banner; create the ApplicationContext (servlet vs reactive vs none — decided by classpath)
  4. Run ApplicationContextInitializers; load the primary bean definitions
  5. refresh()  ── instantiate singletons, run BeanFactoryPostProcessors, THEN evaluate auto-config conditions & register beans, wire dependencies, start the embedded server
  6. Call every ApplicationRunner / CommandLineRunner (your "run once at startup" hook)
  7. Fire ApplicationReadyEvent
```

```java
@Component
class SeedData implements ApplicationRunner {          // runs after the context is ready
    public void run(ApplicationArguments args) {
        // one-time startup work: warm caches, seed dev data, validate config
    }
}
```

> [!warning] Gotcha #2 — heavy work in a `@PostConstruct` or a static initializer
> Doing slow I/O (calling a remote service, running migrations) in a bean's `@PostConstruct` runs it **during context refresh**, before the server is listening — it inflates startup time and, if it throws, the whole app fails to start with a stack trace far from the real cause.
> **Mitigation:** use an `ApplicationRunner`/`CommandLineRunner` (step 6) or listen for `ApplicationReadyEvent` for startup side-effects; keep bean construction cheap. For schema changes, use Flyway/Liquibase (auto-configured), not hand-rolled `@PostConstruct` SQL.

---

## 5. Starters & dependency management: never hand-pick versions

A starter is mostly an empty POM that transitively pulls a coherent set of dependencies. The versions come from Boot's **dependency management** BOM, wired in one of two ways:

```xml
<!-- Option A: inherit the starter parent (also configures plugins, Java version, resource filtering) -->
<parent>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-parent</artifactId>
  <version>4.1.0</version>       <!-- HIGH-CHURN: verify the current GA -->
</parent>

<dependencies>
  <dependency>                    <!-- NO version — the BOM supplies it -->
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
  </dependency>
</dependencies>
```

> [!warning] Gotcha #3 — pinning a transitive version by hand
> Overriding one managed version (say, bumping Jackson or Netty because a blog told you to) breaks the tested compatibility matrix Boot guarantees. Symptoms are ugly: `NoSuchMethodError`, `LinkageError`, or subtle serialization changes at runtime, not compile time.
> **Mitigation:** change versions **through** the BOM by overriding a version property (`<jackson.version>` in `<properties>`), so the whole family moves together — or better, upgrade Boot itself. Treat the BOM as the source of truth; don't fight it dependency-by-dependency.

**Swapping the embedded server** (a common "do you know the starters are modular?" question):

```xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-web</artifactId>
  <exclusions>                    <!-- drop the default Tomcat -->
    <exclusion><groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-tomcat</artifactId></exclusion>
  </exclusions>
</dependency>
<dependency>                      <!-- and add Jetty (or Undertow) -->
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-jetty</artifactId>
</dependency>
```

---

## 6. Overriding & disabling auto-configuration

There is a clear order of preference — reach for the lightest tool first.

| Approach | How | When to use |
|---|---|---|
| **Property** | set the knob auto-config already exposes (`server.port`, `spring.datasource.url`, `spring.jpa.hibernate.ddl-auto`) | 90% of cases — the default is fine, you just tune it |
| **Your own `@Bean`** | define the bean yourself; `@ConditionalOnMissingBean` makes auto-config back off | you need a bean built differently than the default |
| **Exclude the class** | `@SpringBootApplication(exclude = DataSourceAutoConfiguration.class)` or `spring.autoconfigure.exclude` | you want a whole feature *off* (e.g. no DB in this profile) |

> [!tip] Best practice — tune, don't replace
> Prefer a **property** over a custom bean, and a custom **bean** over an exclusion. Every exclusion is a piece of Boot's tested wiring you now own and must maintain across upgrades. Reach for `exclude` only to switch a feature off entirely, never to "redo it slightly differently" — that's what a `@ConditionalOnMissingBean`-winning bean is for.

> [!warning] Gotcha #4 — "auto-config didn't kick in" and you're guessing
> When a bean you expected isn't there (or one you didn't expect is), don't add random `@Bean`s hoping something sticks. Every conditional decision is recorded.
> **Mitigation — the Conditions Evaluation Report:** run with `--debug` (or `debug=true` in properties) and read the report: **Positive matches** (conditions that passed → bean created), **Negative matches** (why each backed off), and **Exclusions**. In a running app the same data is at the Actuator `/actuator/conditions` endpoint. This turns auto-config from a black box into a log you can read.

```bash
java -jar app.jar --debug        # prints the CONDITIONS EVALUATION REPORT at startup
```

---

## 7. Writing your own auto-configuration (custom starter)

The pattern every shared internal library should follow — this is what "we built a company starter" means in an interview.

```java
@AutoConfiguration                                    // Boot 2.7+; a @Configuration variant
@ConditionalOnClass(PaymentClient.class)              // only if the client lib is present
@EnableConfigurationProperties(PaymentProperties.class)
public class PaymentAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean                          // the consumer can override us
    public PaymentClient paymentClient(PaymentProperties props) {
        return PaymentClient.builder()
                .baseUrl(props.getBaseUrl())
                .apiKey(props.getApiKey())
                .build();
    }
}
```

Then register it (this file is **mandatory** — without it the class is inert):

```text
# src/main/resources/META-INF/spring/
#   org.springframework.boot.autoconfigure.AutoConfiguration.imports
com.acme.payment.PaymentAutoConfiguration
```

> [!warning] Gotcha #5 — migrating a pre-3.0 starter and forgetting the imports file
> Custom starters written for Boot ≤2.6 registered auto-config under the `EnableAutoConfiguration` key in `META-INF/spring.factories`. That key was **removed in Boot 3.0**. A starter that still uses only `spring.factories` will compile and publish fine but its auto-configuration **silently never runs** on Boot 3/4 — beans just don't appear.
> **Mitigation:** move the class list to the `AutoConfiguration.imports` file. Split the module in two (an `-autoconfigure` module + a thin `-starter` that just declares dependencies) — the convention Boot's own starters follow. **[HIGH-CHURN: verify against the current reference before relying on file/path details.]**

---

## 8. Alternatives & trade-offs

Auto-configuration's convenience has a cost — runtime classpath inspection and (historically) reflection — that competing frameworks attack differently.

| Framework | DI / config model | Strengths | When to pick it |
|---|---|---|---|
| **Spring Boot** | runtime auto-config + reflection; **AOT + GraalVM native** since 3.x ([[14 - Performance, AOT & Native Images]]) | vast ecosystem, maturity, hiring pool, flexibility | the default for JVM services; anything needing the Spring ecosystem (Data, Security, Cloud) |
| **Micronaut** | **compile-time** DI & AOP (annotation processors, no reflection) | fast startup, low memory, native-friendly | serverless / functions where cold-start dominates |
| **Quarkus** | build-time augmentation, GraalVM-first | very fast native, great Kubernetes/dev story | cloud-native / native-image-first shops |
| **Plain Spring Framework** | manual `@Configuration`, no auto-config | total control, no "magic" | rare — legacy, or a library that must not impose opinions |
| **Dropwizard** | explicit, glued libraries (Jetty + Jersey + Jackson) | minimal magic, easy to reason about | small services by teams that dislike auto-config |

> [!tip] The committed recommendation
> For a JVM backend service in 2026, **default to Spring Boot** — the ecosystem depth (Data, Security, Cloud, AI) and hiring pool outweigh the startup-time penalty, which is now largely answered by AOT + native images and virtual threads ([[14 - Performance, AOT & Native Images]]). Reach for **Micronaut/Quarkus** specifically when **cold-start latency is the product constraint** (serverless, scale-to-zero) and you don't need the full Spring ecosystem. The honest interview answer names the startup/native trade-off rather than pretending Boot has no cost.

---

## 9. Caveats & risk mitigation (summary)

- **Placement over configuration.** The root-package rule (§2) prevents the most common silent failure — enforce it in code review.
- **Read the conditions report before adding beans (§6).** Debugging auto-config by guessing wastes hours; the report answers it in one read.
- **Override through the smallest tool (§6).** Property → bean → exclude, in that order. Every exclusion is tested wiring you now maintain.
- **Respect the BOM (§5).** Don't pin transitive versions by hand; move version properties or upgrade Boot.
- **Keep construction cheap (§4).** Startup side-effects belong in `ApplicationRunner`/`ApplicationReadyEvent`, not constructors or `@PostConstruct`.
- **Version facts are volatile.** Boot 4.1.x / Framework 7 / Jakarta EE 11 / JDK 17 baseline are current as of mid-2026 — **re-verify** the exact GA and any file-path details before relying on them.

---

## 10. In practice

```java
// StoreApplication.java — at the ROOT package com.acme so the whole tree is scanned
package com.acme;

@SpringBootApplication(
    exclude = { SecurityAutoConfiguration.class }      // this profile is internal-only, no auth
)
public class StoreApplication {
    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(StoreApplication.class);
        app.setDefaultProperties(Map.of("server.shutdown", "graceful"));  // §[[13 - Resilience & Production Readiness]]
        app.run(args);
    }

    @Bean
    ApplicationRunner startupCheck(DataSource ds) {        // startup work done RIGHT (§4)
        return args -> { try (var c = ds.getConnection()) { /* fail fast if DB unreachable */ } };
    }
}
```

```properties
# application.properties — tune auto-config via properties FIRST (§6)
server.port=8080
spring.datasource.url=jdbc:postgresql://localhost/store
spring.jpa.hibernate.ddl-auto=validate        # never `update`/`create` in prod (§[[06 - Data Access with Spring Data JPA]])
# debug=true                                   # uncomment to print the conditions evaluation report
```

**Interview talking points to be able to defend:**
- "Auto-configuration is condition-gated bean registration keyed off the classpath, not reflection magic — and `@ConditionalOnMissingBean` is why my beans take precedence."
- "The main class goes in the root package because `@ComponentScan` scans downward from it."
- "To debug missing beans I read the conditions evaluation report (`--debug` / `/actuator/conditions`), I don't guess."
- "I tune via properties, override via a bean, and exclude only to switch a whole feature off."
- "Boot's cost is startup time from runtime wiring; AOT + native and virtual threads close most of that gap, but for serverless cold-start I'd weigh Micronaut/Quarkus."

---

## 11. Sources

- [Spring Boot Reference — Auto-configuration](https://docs.spring.io/spring-boot/reference/using/auto-configuration.html)
- [Spring Boot Reference — Developing Auto-configuration & custom starters](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html)
- [Spring Boot Reference — SpringApplication & the run sequence](https://docs.spring.io/spring-boot/reference/features/spring-application.html)
- [Spring Boot Reference — Build systems & dependency management (starters, BOM)](https://docs.spring.io/spring-boot/reference/using/build-systems.html)
- [Spring Boot 4.0.0 available now (GA announcement, 2025-11-20)](https://spring.io/blog/2025/11/20/spring-boot-4-0-0-available-now/)
- [Spring Framework 7.0 GA (foundation for Boot 4)](https://spring.io/blog/2025/11/13/spring-framework-7-0-general-availability/)
- [Condition annotations — `spring-boot-autoconfigure` Javadoc / `@Conditional` family](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/autoconfigure/condition/package-summary.html)
