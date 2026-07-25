---
title: 03 - Configuration, Profiles & Externalized Config
tags:
  - spring
  - spring-boot
  - configuration
  - profiles
  - senior
aliases:
  - Externalized Configuration
  - Profiles
  - ConfigurationProperties
status: ready
created: 2026-07-09
---

# Configuration, Profiles & Externalized Config

> [!abstract] Scope
> How a Spring Boot app reads configuration from *outside* the jar — the **ordered property-source precedence**, `application.yml` vs `.properties`, the type-safe `@ConfigurationProperties` model (and why it beats `@Value`), relaxed binding, constructor-bound immutable records, fail-fast validation, **profiles** (`@Profile`, active/include/groups, profile-specific files), the **ConfigData** API with `spring.config.import` (config trees for Kubernetes ConfigMaps/Secrets), and 12-factor secret externalization. This is the property system that [[01 - Spring Boot Fundamentals & Auto-Configuration]] reads to decide what to wire; it is also what you tune per-environment when you package and deploy in [[15 - Packaging, Containers & Deployment]].

Related: [[00 - Spring Boot Index]], [[01 - Spring Boot Fundamentals & Auto-Configuration]], [[15 - Packaging, Containers & Deployment]]

| Concern | `@Value("${...}")` | `@ConfigurationProperties` |
|---|---|---|
| Binding | one key → one field | a whole prefix → a typed object graph |
| Type safety | string-ish, coerced per use | strongly typed, validated at bind time |
| Relaxed binding | placeholder must match a resolvable key | full relaxed binding (kebab/camel/underscore/UPPER) |
| Nested / lists / maps | painful | first-class |
| Validation | none | `@Validated` + `jakarta.validation`, **fail-fast at startup** |
| IDE metadata / autocomplete | no | yes (via the annotation processor) |
| Immutability | no | yes (constructor binding / records) |

*The two ways to read a property. The table's last column in §4 tells you when each is the right tool — but the short version is: reach for `@ConfigurationProperties` by default, keep `@Value` for one-off SpEL or a single ad-hoc key.*

---

## 1. Why externalize — the 12-factor line

The same jar must run unchanged in dev, staging, and prod; only the *configuration* differs. That is [factor III of the 12-factor app](https://12factor.net/config): **strict separation of config from code**, config supplied by the environment. Spring Boot's whole externalized-config machinery exists to serve that rule — you build one artifact, then feed it a database URL, a log level, or a feature flag from a file, an environment variable, or a command-line argument at launch.

Two consequences drive everything below:

1. **Config is layered, not single-sourced.** A value can come from a dozen places, so there must be a *deterministic precedence* (§3) — otherwise "which value wins?" is a coin toss.
2. **Secrets are config too, but special.** They must never live in the artifact or in version control (§10). The mechanisms that inject config from the environment are exactly the mechanisms that inject secrets safely.

> [!tip] The framing interviewers want
> "One immutable artifact, configuration supplied from outside per environment, with a well-defined precedence so overrides are predictable — and secrets injected the same way but never committed." If you can also name *where* in the order an environment variable sits relative to `application.yml`, that's the senior signal.

---

## 2. `application.properties` vs `application.yml`

Boot reads either from `src/main/resources` (or an external location, §9). They are functionally equivalent for simple keys; YAML wins for hierarchy and lists.

```properties
# application.properties — flat, one key per line
spring.datasource.url=jdbc:postgresql://localhost/store
spring.datasource.hikari.maximum-pool-size=10
app.features[0]=search
app.features[1]=recommend
```

```yaml
# application.yml — hierarchical; the same shape, far less repetition
spring:
  datasource:
    url: jdbc:postgresql://localhost/store
    hikari:
      maximum-pool-size: 10
app:
  features: [search, recommend]
```

| | `.properties` | `.yml` |
|---|---|---|
| Structure | flat, dotted keys | nested, indentation-based |
| Lists / maps | index syntax `[0]` | native sequences / maps |
| Multi-document | `#---` separator | `---` separator |
| Type surprises | few (all strings) | **many** (see gotcha below) |
| When to pick | tiny/flat config, ops familiarity | anything hierarchical (the common case) |

> [!warning] Gotcha #1 — YAML silently coerces types (the "Norway problem")
> YAML infers types from unquoted scalars. The classic bite: a country code `NO` (Norway) is read as the boolean `false`; `on`/`off`/`yes`/`no` likewise become booleans. Unquoted numbers with a leading zero can be read as **octal** (`0755` ≠ 755), a version string `1.10` loses its trailing zero, and a large account number becomes a `long` you didn't want. None of this errors — you just get the wrong value at runtime.
> **Mitigation:** **quote every string value that could look like something else** — `"NO"`, `"0755"`, `"1.10"`, `"on"`. When binding to a typed field via `@ConfigurationProperties` (§4), the declared Java type disambiguates for you — another reason to prefer it over stringly `@Value`.

> [!warning] Gotcha #2 — precedence: `.properties` wins over `.yml`
> If both `application.properties` and `application.yml` exist in the **same location**, the `.properties` file takes precedence, so a stray leftover `.properties` can silently shadow your carefully edited YAML.
> **Mitigation:** pick one format per project and delete the other; don't keep both in `src/main/resources`.

---

## 3. The ordered property-source precedence

This is the most-probed topic. A property is resolved by consulting sources **highest-priority first**; the first source that has the key wins. The full order (highest → lowest), keeping the sources you actually reason about in bold:

| # | Source | Example |
|---|---|---|
| 1 | **Command-line arguments** | `--server.port=9000` |
| 2 | **`SPRING_APPLICATION_JSON`** (inline JSON in an env var / system prop) | `SPRING_APPLICATION_JSON='{"server":{"port":9000}}'` |
| 3 | `ServletConfig` / `ServletContext` init params | (traditional servlet deploys) |
| 4 | JNDI attributes (`java:comp/env`) | (app-server deploys) |
| 5 | Java **System properties** | `-Dserver.port=9000` |
| 6 | **OS environment variables** | `SERVER_PORT=9000` |
| 7 | `RandomValuePropertySource` | `${random.uuid}` |
| 8 | **`application-{profile}.yml`** (profile-specific; outside-jar beats inside) | `application-prod.yml` |
| 9 | **`application.yml` / `.properties`** (outside-jar beats inside) | `application.yml` |
| 10 | **`@PropertySource`** on a `@Configuration` class | `@PropertySource("classpath:legacy.properties")` |
| 11 | **`SpringApplication.setDefaultProperties(...)`** | code-supplied fallbacks |

Two nuances worth stating precisely, because both surprise people:

- **Java system properties (`-D…`) outrank OS environment variables.** A `-Dspring.profiles.active=…` beats an exported `SPRING_PROFILES_ACTIVE`.
- Within files, **profile-specific beats plain**, and **outside-the-jar beats inside-the-jar** — so an ops-supplied external `application.yml` overrides the one you baked in.

> [!warning] Gotcha #3 — the prod override that never applied
> You set `server.port` in `application-prod.yml`, deploy, and the app still binds the default port. Cause: an OS environment variable `SERVER_PORT` (or a `--server.port` in the launch script, or a `-D` flag) sits **above** file config in the order, so the file value can never win. Teams burn hours "fixing the YAML" when the file was never the effective source.
> **Mitigation:** treat the precedence table as canonical. To see the *effective* value and its origin at runtime, hit the Actuator `/actuator/env` endpoint ([[12 - Actuator, Metrics & Observability]]) — it shows every source and which one supplied each key. Debug the order, don't edit blindly.

---

## 4. `@Value` vs `@ConfigurationProperties` — and why the latter wins

`@Value` injects a single resolved placeholder; `@ConfigurationProperties` binds an entire prefix to a typed bean.

```java
// @Value — fine for a single ad-hoc key, but note the failure modes
@Component
class LegacyClient {
    @Value("${app.timeout-ms:5000}")   // ':5000' = default if the key is absent
    private long timeoutMs;
}
```

```java
// @ConfigurationProperties — the preferred model: typed, grouped, validated
@ConfigurationProperties(prefix = "app.payment")
@Validated                                       // turn on jakarta.validation (§7)
public class PaymentProperties {
    @NotBlank private String baseUrl;            // fail-fast if missing/blank
    @Min(1)   private int retries = 3;           // field default
    private Duration timeout = Duration.ofSeconds(5);  // "5s"/"500ms" parsed for you
    // getters/setters …
}
```

```java
@SpringBootApplication
@ConfigurationPropertiesScan                     // scans for @ConfigurationProperties beans
public class StoreApplication { /* … */ }
// (or, for finer control: @EnableConfigurationProperties(PaymentProperties.class))
```

```yaml
app:
  payment:
    base-url: https://payments.acme.internal   # kebab-case → baseUrl (relaxed binding, §5)
    retries: 5
    timeout: 750ms
```

**Why `@ConfigurationProperties` is preferred** — five concrete wins: **(1) type-safe** binding to real Java types (`Duration`, `DataSize`, enums, `List`/`Map`) instead of stringly values; **(2) relaxed binding** (§5) so the YAML and the field can differ in case/style; **(3) validation** via `@Validated` + `jakarta.validation`, failing fast at startup (§7); **(4) IDE metadata** — the `spring-boot-configuration-processor` generates `spring-configuration-metadata.json`, giving autocomplete and docs for your keys; **(5) grouping** — related keys bind to one cohesive object you inject as a unit, instead of scattering `@Value`s across the codebase.

| Question | Answer |
|---|---|
| Multiple related keys under a prefix? | `@ConfigurationProperties` |
| Nested objects, lists, or maps? | `@ConfigurationProperties` |
| Want validation / fail-fast / IDE autocomplete? | `@ConfigurationProperties` |
| Immutable config object? | `@ConfigurationProperties` with constructor binding (§6) |
| A single one-off key, or a **SpEL expression** (`#{…}`)? | `@Value` |
| Injecting into a bean you don't own / can't add a prefix to? | `@Value` |

> [!warning] Gotcha #4 — a `@Value` placeholder typo
> `@Value("${app.timout-ms}")` (note the missing `e`) with **no default** throws `IllegalArgumentException: Could not resolve placeholder 'app.timout-ms'` at startup — annoying but at least loud. The nastier variant: write `@Value("app.timeout-ms")` *without* the `${…}` and Spring injects the **literal string** `"app.timeout-ms"`, which then blows up as a `NumberFormatException` on a `long` field, or worse, silently is the literal on a `String` field. There is no compile-time check on placeholder names.
> **Mitigation:** prefer `@ConfigurationProperties` (a wrong key just leaves the field at its default, and the generated metadata catches typos in the IDE); when you must use `@Value`, always include a default (`${key:fallback}`) and always wrap in `${…}`.

> [!important] Committed best practice
> Default to `@ConfigurationProperties` for anything that is a *group* of settings for a component; it is the type-safe, validatable, discoverable, immutable-capable model. Keep `@Value` for genuine one-offs and SpEL. This is a real signal in code review — a class with six `@Value` fields should almost always be one `@ConfigurationProperties` record.

---

## 5. Relaxed binding

`@ConfigurationProperties` does **not** require the source key to match the field name exactly. Boot canonicalises both sides, so one field binds from several spellings — which is what lets an environment variable (screaming-snake, the only form most OSes allow) map to a camelCase field.

| Field `baseUrl` under prefix `app.payment` binds from… | Where you'd use it |
|---|---|
| `app.payment.base-url` (**kebab-case**) | `.yml` / `.properties` — the recommended canonical form |
| `app.payment.baseUrl` (camelCase) | properties files |
| `app.payment.base_url` (underscore) | properties files |
| `APP_PAYMENT_BASEURL` (**UPPER + underscore**) | **OS environment variables** |

The env-var rule specifically: uppercase the canonical name, replace `.` and `-` with `_`. So `spring.datasource.url` ← `SPRING_DATASOURCE_URL`, and `spring.profiles.active` ← `SPRING_PROFILES_ACTIVE`. This is the bridge between container/Kubernetes env injection and your typed config.

> [!tip] Write kebab-case, only kebab-case
> Relaxed binding is a *reader* convenience; don't rely on it for style consistency in your files. Standardise on **kebab-case** in every `.yml`/`.properties` file (`base-url`, not `baseUrl`) — it's the canonical form Boot's own docs and the metadata use, and it reads consistently. Reserve the UPPER_SNAKE form for the env vars that must use it.

---

## 6. Constructor binding & immutable records

Setter binding needs a mutable bean. Constructor binding gives you an **immutable** config object — ideal for `record`s. Boot infers constructor binding from a single constructor, so a record just works:

```java
@ConfigurationProperties(prefix = "app.payment")
@Validated
public record PaymentProperties(
        @NotBlank String baseUrl,
        @DefaultValue("3") @Min(1) int retries,     // @DefaultValue supplies binder defaults
        @DefaultValue("5s") Duration timeout,
        Security security) {                         // nested record binds too

    public record Security(@NotBlank String apiKey) {}
}
```

Key rules, verified against the Boot 4.1 reference:

- **Records work out of the box** — no annotation needed as long as there is a single constructor.
- **`@ConstructorBinding`** is only required to disambiguate when a class/record has **multiple constructors**; put it on the constructor to select.
- Defaults come from **`@DefaultValue`** (constructor binding can't use field initializers, since the fields are `final` and set by the constructor).
- Requires parameter names at runtime — compile with `-parameters` (the `spring-boot-starter-parent` and Boot Gradle plugin set this for you). **[HIGH-CHURN: verify the `-parameters` default in your build tooling.]**

> [!tip] Immutable config is safer config
> A `record`-based `@ConfigurationProperties` can't be mutated after startup, is trivially thread-safe, and documents its shape in one line. Prefer it over the setter-based JavaBean style for new code.

---

## 7. Validation — fail fast at startup

Add `@Validated` to a `@ConfigurationProperties` class and annotate fields with `jakarta.validation` constraints (Jakarta EE 11 — **`jakarta.*`, not the removed `javax.*`**). Requires a validator on the classpath (`spring-boot-starter-validation`, which brings Hibernate Validator).

```java
@ConfigurationProperties(prefix = "app.pool")
@Validated
public class PoolProperties {
    @Min(1) @Max(100) private int size = 10;
    @NotNull private Duration idleTimeout;          // no default → must be supplied
    @Email  private String alertEmail;
    // getters/setters …
}
```

If any constraint fails, Boot throws and the application **refuses to start**, with a report naming the offending property, the invalid value, and the constraint. That is the point: a bad config is caught at boot, in the deploy pipeline, not as a `NullPointerException` under load three hours later.

> [!important] Fail-fast beats defensive nulls
> Validating config at startup converts a whole class of "misconfigured in prod" incidents into a failed deploy. Put `@NotNull`/`@NotBlank` on anything that has no safe default (credentials, URLs, required timeouts) and let the app fail loudly rather than boot in a broken half-state.

---

## 8. Profiles

A **profile** is a named condition; beans and configuration can be scoped to it, so one artifact behaves differently per environment.

**Scoping beans** with `@Profile`:

```java
@Configuration(proxyBeanMethods = false)
@Profile("prod")                       // this config loads only when 'prod' is active
class ProdMailConfig { /* real SMTP sender */ }

@Configuration(proxyBeanMethods = false)
@Profile("!prod")                      // everything except prod
class DevMailConfig { /* logging no-op sender */ }
```

**Activating** profiles — `spring.profiles.active` (comma-separated), set anywhere in the precedence order:

```bash
java -jar app.jar --spring.profiles.active=prod         # CLI
export SPRING_PROFILES_ACTIVE=prod                      # env var
```

**Profile-specific files** load automatically on top of the base file: `application-prod.yml`, `application-dev.properties`, etc. **Profile groups** (`spring.profiles.group`) expand one profile into several; **`spring.profiles.include`** always-adds profiles on top of the active set:

```yaml
# application.yml
spring:
  profiles:
    group:
      prod: ["prod-db", "prod-mq", "metrics"]   # activating 'prod' turns on all three
    include: ["logging-common"]                  # added regardless of active profiles
```

> [!warning] Gotcha #5 — the active profile was never set, so the profile file never loaded
> `application-prod.yml` exists, looks right, and is completely ignored — because nothing set `spring.profiles.active=prod` in that environment. Profile-specific files load **only** when their profile is active; there is no error, the app just runs on defaults. A close cousin: you cannot put `spring.profiles.active` (or `include`/`group`) **inside** a profile-specific document — Boot ignores it there by design, so `application-prod.yml` can't activate `prod`.
> **Mitigation:** set the active profile from the *environment* (env var / CLI / deployment manifest), never from a profile-specific file. Verify it landed via the startup log line `The following profiles are active: prod` or `/actuator/env`. In containers, set `SPRING_PROFILES_ACTIVE` in the manifest so it's visible and reviewable.

---

## 9. The ConfigData API & `spring.config.import`

Since Boot 2.4 the **ConfigData** API replaced the old bootstrap-context config loading and made `spring.config.import` the uniform way to pull in *additional* config locations — files, directories, config trees, or third-party sources (Vault, Consul) via extensions. It is processed as part of the normal environment preparation, so imported values slot into the precedence order (§3) predictably.

```yaml
# application.yml
spring:
  config:
    import:
      - optional:file:./local-overrides.yml        # optional: = don't fail if absent
      - configtree:/etc/config/                      # Kubernetes ConfigMap mounted as files
      - configtree:/etc/secrets/                     # Kubernetes Secret mounted as files
```

**Config trees** (`configtree:`) are the Kubernetes-native pattern: a mounted ConfigMap or Secret becomes a directory where **each file's name is a property key and its content is the value**. A Secret mounted at `/etc/secrets/` with a file `app.payment.api-key` binds straight to that property — the secret never appears in any committed file or env var dump.

```
/etc/secrets/
  spring.datasource.password      ← file content is the value
  app.payment.api-key
```

Other prefixes you'll use: `optional:` (tolerate a missing location), `file:` / `classpath:` (explicit locations), and — for pointing at an entirely different config file — `spring.config.location` (replaces defaults) or `spring.config.additional-location` (adds to them).

> [!tip] `spring.config.import` over the legacy bootstrap
> If you still have `spring-cloud-starter-bootstrap` or a `bootstrap.yml` pulling config from Vault/Consul, migrate to `spring.config.import=vault://…` / `consul:…`. The ConfigData approach is the supported path on Boot 2.4+ and slots cleanly into the documented precedence instead of the separate, surprising bootstrap context. **[HIGH-CHURN: confirm the exact import URL scheme for your Spring Cloud version.]**

---

## 10. Secrets & the 12-factor discipline

Secrets are config, but they must never be *baked into* the artifact or committed. The mechanisms above are exactly how you keep them out.

- **Never** put a real credential in `application.yml` / `.properties` in the repo. Use a placeholder that resolves from the environment: `spring.datasource.password=${DB_PASSWORD}`.
- **Inject at runtime** via OS environment variables (`SPRING_DATASOURCE_PASSWORD`), a mounted Secret config tree (§9), or a secrets manager (**HashiCorp Vault** via `spring.config.import=vault://…`, AWS Secrets Manager, etc.).
- **Rotate** without redeploying — a Vault/Secret-backed value can change with a pod restart, not a rebuild.

> [!warning] Gotcha #6 — a secret committed in `application.yml`
> A password or API key checked into `application.yml` is in git history **forever** — rotating the key doesn't un-leak it, and anyone with repo (or fork, or CI-log) access has it. This is the single most common security finding in a Spring codebase review.
> **Mitigation:** keep only placeholders in committed files (`${DB_PASSWORD}`); supply real values from env vars, config trees, or Vault. Add a secret-scanner (gitleaks / GitHub secret scanning) to CI to block commits. If one already leaked, **rotate the credential** — deleting the line is not enough. See [[15 - Packaging, Containers & Deployment]] for wiring secrets into containers.

---

## 11. Caveats & risk mitigation (summary)

- **Know the order (§3).** Env vars and `-D` outrank files; an external file outranks the baked-in one. Debug effective values with `/actuator/env`, don't edit blindly.
- **Quote ambiguous YAML scalars (§2).** `NO`, `0755`, `1.10`, `on` — or bind them through a typed `@ConfigurationProperties` field.
- **Prefer `@ConfigurationProperties` (§4).** Type-safe, validated, discoverable, immutable. Keep `@Value` for one-offs/SpEL and always give it a default.
- **Validate and fail fast (§7).** `@Validated` + `jakarta.validation` turns misconfiguration into a failed deploy.
- **Set the active profile from the environment (§8).** Never from a profile-specific file; verify it in the startup log.
- **Externalize every secret (§10).** Placeholders in the repo, real values from env/config-tree/Vault, rotate on leak.
- **Version facts are volatile.** Boot 4.1.x on Framework 7.0, Jakarta EE 11 (`jakarta.validation`), JDK 17 baseline are current as of mid-2026 — **re-verify** exact versions and the `-parameters` build default before relying on them.

---

## 12. In practice

```java
// PaymentProperties.java — typed, immutable, validated config for one component
@ConfigurationProperties(prefix = "app.payment")
@Validated
public record PaymentProperties(
        @NotBlank String baseUrl,
        @DefaultValue("5s") Duration timeout,
        @DefaultValue("3") @Min(1) int retries) {}
```

```yaml
# application.yml — base config, secrets as placeholders only
spring:
  config:
    import: "optional:configtree:/etc/secrets/"     # prod secrets mounted here
app:
  payment:
    base-url: https://payments.acme.internal
    timeout: 750ms
--- # ---------- dev profile document ----------
spring:
  config:
    activate:
      on-profile: dev
app:
  payment:
    base-url: http://localhost:8081                 # dev points at a stub
```

```bash
# launch — profile + secret supplied by the environment, never the repo
SPRING_PROFILES_ACTIVE=prod \
APP_PAYMENT_BASE_URL=https://payments.prod.acme.com \   # env var beats the file (§3)
java -jar store.jar
```

**Interview talking points to be able to defend:**
- "Config precedence, top to bottom: command-line args, `SPRING_APPLICATION_JSON`, then system properties, then OS env vars, then profile-specific files, then `application.yml`, then `@PropertySource`, then coded defaults — and env vars beat files, which is why prod overrides sometimes don't apply."
- "I default to `@ConfigurationProperties` — type-safe, relaxed-bound, validatable, immutable as a record — and keep `@Value` for one-off keys or SpEL."
- "Relaxed binding is what lets `SPRING_DATASOURCE_URL` bind to `spring.datasource.url`; I write kebab-case in files."
- "`@Validated` + `jakarta.validation` on a properties class fails the app at startup on bad config — fail fast in the pipeline, not under load."
- "Profiles are activated from the environment, never from a profile-specific file, and I verify via the startup log; groups expand one profile into many."
- "Secrets are placeholders in the repo and real values from env vars, a Kubernetes Secret config tree (`configtree:`), or Vault via `spring.config.import` — never committed, and rotated on leak."

---

## 13. Sources

- [Spring Boot Reference — Externalized Configuration (precedence, relaxed binding, `@ConfigurationProperties`, ConfigData, `spring.config.import`)](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot Reference — Profiles (`@Profile`, active/include/group, profile-specific files)](https://docs.spring.io/spring-boot/reference/features/profiles.html)
- [Spring Boot Reference — Type-safe config properties & validation](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
- [`@ConfigurationProperties` Javadoc (Boot 4.1)](https://docs.spring.io/spring-boot/4.1.0/api/java/org/springframework/boot/context/properties/ConfigurationProperties.html)
- [`@ConstructorBinding` Javadoc (Boot 4.1)](https://docs.spring.io/spring-boot/4.1.0/api/java/org/springframework/boot/context/properties/bind/ConstructorBinding.html)
- [Spring Boot 4.0.0 available now (GA announcement, 2025-11-20)](https://spring.io/blog/2025/11/20/spring-boot-4-0-0-available-now/)
- [The Twelve-Factor App — III. Config](https://12factor.net/config)
