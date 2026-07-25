---
title: 11 - Testing Spring Boot Applications
tags:
  - spring
  - spring-boot
  - testing
  - junit
  - testcontainers
  - senior
aliases:
  - Testing
  - SpringBootTest
  - Test Slices
  - Testcontainers
status: ready
created: 2026-07-09
---

# Testing Spring Boot Applications

> [!abstract] Scope
> How to test a Spring Boot service *at the right level* — plain [[02 - IoC Container, Beans & Dependency Injection|constructor-injected]] unit tests with Mockito, focused **slice** tests (`@WebMvcTest`, `@DataJpaTest`, `@JsonTest`, `@RestClientTest`) that boot a thin context, and full `@SpringBootTest` integration tests backed by **Testcontainers** rather than H2. The through-line is *speed vs. fidelity*: which tier answers your question fastest, and how the **test context cache** keeps even the heavy tiers fast. For the persistence layer under test see [[06 - Data Access with Spring Data JPA]]; for securing the endpoints you'll assert against, [[08 - Spring Security]].

Related: [[00 - Spring Boot Index]], [[06 - Data Access with Spring Data JPA]], [[08 - Spring Security]]

---

## 1. The test pyramid, applied to Spring

The classic pyramid — many fast unit tests, fewer integration tests, a handful of end-to-end tests — has a Spring-specific corollary: **starting an `ApplicationContext` is the expensive part.** A pure unit test runs in microseconds; the first test that boots a context pays hundreds of milliseconds to seconds. So the senior instinct is *not* "annotate everything with `@SpringBootTest`" — it is "load the smallest context (or none) that can answer this test's question."

| Tier | What it loads | Speed | Answers the question… |
|---|---|---|---|
| **Unit** | nothing — plain `new`, Mockito mocks | microseconds | "is my logic correct in isolation?" |
| **Slice** | one thin, purpose-built context (web layer, JPA layer, JSON…) | ~1s to warm, cached after | "does this layer wire and behave correctly?" |
| **Integration** | the *whole* application context (+ real infra) | seconds | "do the layers work together, for real?" |

> [!tip] The framing interviewers want
> "Most of my tests don't touch Spring at all — constructor injection makes my beans plain objects I can unit-test with Mockito. I drop to a **slice** when I need the framework's own machinery (MVC serialization, JPA mapping, JSON binding), and I reserve **`@SpringBootTest`** for a small number of true integration paths. Loading a context is the cost, so I minimize *how often* and *how many distinct* contexts I load." That last clause is the test-context-cache point (§7) — the single biggest lever on suite runtime.

---

## 2. Plain unit tests: constructor injection is the whole trick

If a bean receives its collaborators through its **constructor** ([[02 - IoC Container, Beans & Dependency Injection]]), testing it needs no Spring at all — you construct it with mocks and call methods.

```java
class OrderServiceTest {                       // no @SpringBootTest, no @ExtendWith — pure JUnit

    private final InventoryClient inventory = mock(InventoryClient.class);   // Mockito
    private final OrderRepository repo       = mock(OrderRepository.class);
    private final OrderService service       = new OrderService(inventory, repo);  // just `new`

    @Test
    void rejectsOrderWhenOutOfStock() {
        given(inventory.stockFor("SKU-1")).willReturn(0);

        assertThatThrownBy(() -> service.place("SKU-1", 2))
            .isInstanceOf(OutOfStockException.class);
        then(repo).should(never()).save(any());          // verify the interaction
    }
}
```

> [!warning] Gotcha #1 — field injection makes a class un-unit-testable
> A bean that uses `@Autowired` on **private fields** has no constructor to pass mocks into. To test it you're forced to either start a Spring context (slow) or use reflection to poke fields (brittle). The design smell and the testing pain are the same bug.
> **Mitigation:** use **constructor injection** everywhere (final fields, no `@Autowired` needed on a single constructor). The class then advertises its dependencies in its signature and is trivially testable with `new`. Constructor injection isn't a testing trick bolted on afterward — it's the property that *lets* the pyramid have a wide base.

> [!tip] Reach for `@ExtendWith(MockitoExtension.class)` only for wiring sugar
> Adding the Mockito JUnit extension lets you use `@Mock`/`@InjectMocks` and get automatic `strictness`/verification of unused stubs. It still starts **no Spring context** — it's a unit test. Use it for ergonomics, not because you need the framework.

---

## 3. Slice tests: a thin, purpose-built context per concern

When you *do* need Spring's machinery for one layer, a **slice** annotation boots a context containing only that layer's auto-configuration and beans — not your whole app. Each slice also **turns off unrelated auto-configuration** (no full component scan, no `DataSource` for a web slice, etc.), which is why they stay fast.

| Slice annotation | Auto-configures / loads | Does **not** load | Use for |
|---|---|---|---|
| `@WebMvcTest` | `DispatcherServlet`, your `@Controller`s, converters, `@ControllerAdvice`, filters, `MockMvc`/`MockMvcTester` | `@Service`/`@Repository`, `DataSource` | controller mapping, validation, status/JSON, security rules |
| `@DataJpaTest` | JPA `EntityManager`, Spring Data repositories, a `DataSource`, transactions | web layer, `@Service` beans | repository queries, entity mapping, JPQL |
| `@JsonTest` | Jackson/Gson `ObjectMapper`, `JacksonTester` | everything else | serialization/deserialization of DTOs |
| `@RestClientTest` | `RestClient`/`RestTemplate` builders + `MockRestServiceServer` | web layer, data layer | your **outbound** HTTP client code |

Common threads: each slice is `@Transactional`-aware where relevant (`@DataJpaTest` rolls back each test), each restricts component scanning to the relevant stereotypes, and each is a distinct **context configuration** that the cache (§7) keys on. You bring in collaborators the slice deliberately excludes via `@MockitoBean` (§5).

---

## 4. `@WebMvcTest` in practice — MockMvc / MockMvcTester + `@MockitoBean`

This is the workhorse for controller tests: it exercises the real MVC pipeline (routing, argument binding, validation, `@ControllerAdvice`, JSON serialization) **without** a running server or a database. The service the controller depends on is replaced by a mock in the context.

```java
@WebMvcTest(OrderController.class)             // boots ONLY the web slice for this controller
class OrderControllerTests {

    @Autowired MockMvcTester mvc;              // AssertJ-fluent client, auto-configured since Boot 3.4
    @MockitoBean OrderService orderService;    // a mock placed INTO the slice context (§5)

    @Test
    void returnsOrderAsJson() {
        given(orderService.find(42L)).willReturn(new Order(42L, "SHIPPED"));

        assertThat(mvc.get().uri("/orders/{id}", 42L))     // AssertJ triggers the exchange
            .hasStatusOk()
            .bodyJson().extractingPath("$.status").isEqualTo("SHIPPED");
    }

    @Test
    void returns400OnInvalidBody() {
        assertThat(mvc.post().uri("/orders").contentType(APPLICATION_JSON).content("{}"))
            .hasStatus(HttpStatus.BAD_REQUEST);            // bean-validation path
    }
}
```

> [!important] `MockMvcTester` vs classic `MockMvc` — HIGH-CHURN
> `MockMvcTester` (AssertJ-based, `assertThat(mvc.get()...)`) arrived in **Spring Framework 6.2 / Boot 3.4** and is the current-idiom entry point. The older `MockMvc` fluent style — `mockMvc.perform(get(...)).andExpect(status().isOk())` — is still fully supported and ubiquitous in existing codebases; know both. A key behavioral difference: with `MockMvcTester` an unresolved handler exception surfaces on the `MvcTestResult` to be asserted, rather than being thrown out of the call. **Verify the exact API against the reference for your Framework version.**

> [!warning] Gotcha #2 — not resetting mocks between tests
> A `@MockitoBean` lives in the **cached context** (§7), so the same mock instance can be reused across test methods and even across test classes that share the context. Stubbings or recorded interactions bleeding from one test into the next cause maddening order-dependent failures.
> **Mitigation:** `@MockitoBean`/`@MockitoSpyBean` mocks are **reset automatically by Spring after each test method**, so prefer them over hand-rolled mock beans. If you register a mock yourself (a `@Bean` returning `mock(...)`), you own resetting it — call `Mockito.reset(...)` in an `@AfterEach`, or better, switch to `@MockitoBean`.

---

## 5. Replacing a bean in the context — `@MockitoBean` / `@MockitoSpyBean`

Slice and integration tests often need to *swap* a bean in the running context for a mock (an unreliable payment gateway, a clock, a downstream service). That is what these annotations do — they override a bean in the test's `ApplicationContext`.

```java
@MockitoBean    PaymentGateway gateway;   // REPLACE_OR_CREATE: bean becomes a Mockito mock
@MockitoSpyBean AuditService  audit;      // WRAP: real bean kept, wrapped in a Mockito spy
```

- **`@MockitoBean`** replaces (or creates) the bean with a plain mock — the real implementation never runs.
- **`@MockitoSpyBean`** wraps the *real* bean in a spy — real methods run unless you stub them, and you can verify calls.

> [!important] These REPLACED `@MockBean` / `@SpyBean` — VERIFY, because this bit is version-sensitive
> `@MockBean`/`@SpyBean` (Spring Boot's `org.springframework.boot.test.mock.mockito` package) were **deprecated in Boot 3.4** in favour of `@MockitoBean`/`@MockitoSpyBean`, which are part of **Spring Framework itself** — `org.springframework.test.context.bean.override.mockito` — built on the generic bean-override mechanism introduced in Framework 6.2. They were **removed in Boot 4.0**, so on the Boot 4.1 baseline here you *must* use the new annotations; the old imports won't compile. This is a favourite "are you current?" interview probe. **[HIGH-CHURN: confirm the deprecation/removal versions against the reference before quoting them.]** Sibling annotations from the same mechanism: `@TestBean` (replace with a static factory method) and `@MockitoBean` with `types`/`name` targeting.

> [!warning] Gotcha #3 — every distinct set of `@MockitoBean`s is a *new* cached context
> A bean override changes the context configuration, so a test class with `@MockitoBean PaymentGateway` gets a **different cache key** (§7) than one without it. Sprinkling different override combinations across many classes silently multiplies the number of contexts Spring builds and caches, and your "fast" slice suite starts booting ten contexts instead of two.
> **Mitigation:** standardize override sets. Put a common set of `@MockitoBean`s on a shared base test class (or a `@…Test` meta-annotation) so many test classes share one context configuration and therefore one cached context.

---

## 6. `@SpringBootTest` — the full context, and when it's justified

`@SpringBootTest` loads your **entire** application context (every bean, all auto-configuration) — the highest-fidelity, slowest tier. With `webEnvironment = RANDOM_PORT` it also starts the **real embedded server** on a free port, so you test over actual HTTP.

```java
@SpringBootTest(webEnvironment = WebEnvironment.RANDOM_PORT)
@AutoConfigureRestTestClient                       // Framework 7 / Boot 4 client — HIGH-CHURN
class CheckoutIntegrationTests {

    @Test
    void placeOrderEndToEnd(@Autowired RestTestClient client) {
        client.post().uri("/orders").body(new OrderRequest("SKU-1", 2))
              .exchange()
              .expectStatus().isCreated()
              .expectBody().jsonPath("$.status").isEqualTo("CONFIRMED");
    }
}
```

The web client options, all injectable when a server is running:

| Client | Style | Notes |
|---|---|---|
| `RestTestClient` | fluent, `expectStatus()/expectBody()` | **Framework 7 / Boot 4** unified client; the current recommendation — **HIGH-CHURN** |
| `WebTestClient` | fluent, reactive-origin | long-standing; requires WebFlux on the classpath for server binding |
| `TestRestTemplate` | imperative, template-style | classic, still supported; fault-tolerant variant of `RestTemplate` |

> [!warning] Gotcha #4 — `@SpringBootTest` everywhere → a suite that takes minutes
> The most common self-inflicted wound: every test class annotated `@SpringBootTest`, each booting the full context (plus a server, plus a DB). A suite that *should* run in seconds takes minutes, developers stop running it locally, and CI feedback slows to a crawl. `@SpringBootTest` is a scalpel, not a default.
> **Mitigation:** push logic down to **unit tests** (§2) and behaviour down to **slices** (§3); reserve `@SpringBootTest` for genuine cross-layer paths (a full request → service → real DB → response). A healthy suite is mostly base-of-pyramid.

> [!tip] When a full integration test *is* the right call
> Use `@SpringBootTest` when the thing under test **is** the integration: security filter chains combined with controllers and method security, transaction boundaries spanning services and repositories, message-listener → handler → DB flows, or verifying that your beans actually wire together at all. If a slice can answer it, a slice should.

---

## 7. The test context cache — the biggest lever on suite speed

Spring's TestContext framework **caches each loaded `ApplicationContext` and reuses it** across every test class that requests an identical configuration. Booting the context is the expensive step; the cache means you pay it *once* per distinct configuration, not once per class. Getting this right is what makes a large Boot suite fast.

The cache **key** is the full combination of configuration attributes — among them: `@ContextConfiguration` classes/locations, active profiles (`@ActiveProfiles`), `@TestPropertySource` properties, context initializers/customizers, and any **bean overrides** (`@MockitoBean` etc.). Change any of these and you get a *different* context. The cache holds a default maximum of **32** contexts with LRU eviction (tunable via `spring.test.context.cache.maxSize`). **[HIGH-CHURN: verify the default max size for your version.]**

> [!warning] Gotcha #5 — `@DirtiesContext` and inconsistent config quietly bust the cache
> Two failure modes destroy the cache's benefit: **(a)** scattering `@DirtiesContext`, which *evicts and closes* the context so the next class rebuilds it from scratch; **(b)** tiny gratuitous config differences — one class adds `@TestPropertySource("x=1")`, another sets a stray profile, a third adds one `@MockitoBean` — each producing a *separate* cached context. Suddenly the suite builds 15 contexts instead of 3, and nobody notices except the clock.
> **Mitigation:** treat `@DirtiesContext` as a last resort (a bean whose state genuinely can't be reset) and prefer resetting state in `@AfterEach`. **Standardize context configuration**: a small number of shared base classes / composed `@…Test` meta-annotations so most classes collapse onto the same key. Audit context count with the `spring.test.context.cache` logging / statistics to see how many you're really building.

---

## 8. Testcontainers over H2 — real infrastructure, not a lookalike

For any test that touches the database (or a broker, cache, etc.), run the **real** technology in a throwaway Docker container via [Testcontainers](https://java.testcontainers.org/) rather than substituting H2. Since **Boot 3.1**, `@ServiceConnection` wires Spring's connection details (URL, credentials, driver) straight from the container — no `@DynamicPropertySource` plumbing.

```java
@DataJpaTest
@AutoConfigureTestDatabase(replace = Replace.NONE)     // don't swap in an embedded DB — use the container
@Testcontainers
class OrderRepositoryTests {

    @Container @ServiceConnection                       // Boot auto-derives spring.datasource.* from this — since 3.1
    static PostgreSQLContainer<?> postgres = new PostgreSQLContainer<>("postgres:16");

    @Autowired OrderRepository repository;

    @Test
    void findsByStatusUsingRealPostgres() {
        repository.save(new Order("SKU-1", Status.SHIPPED));

        assertThat(repository.findByStatus(Status.SHIPPED)).hasSize(1);
    }
}
```

Note the two annotations working together: `@Testcontainers`/`@Container` manage the container lifecycle (a `static` container starts once for all tests in the class), and `@ServiceConnection` performs the Spring wiring. The `@AutoConfigureTestDatabase(replace = Replace.NONE)` is essential — `@DataJpaTest` otherwise replaces your `DataSource` with an embedded one, defeating the container.

> [!warning] Gotcha #6 — H2 passes, production Postgres fails
> H2 "compatibility modes" only *approximate* Postgres. Tests that pass on H2 routinely break in production because of divergent behaviour: native/JSONB/array types, `ON CONFLICT` upserts, sequence semantics, case-folding of identifiers, window functions, isolation levels, and Hibernate picking a **different SQL dialect** entirely. You are testing a database you don't ship.
> **Mitigation:** test against the **same engine and major version you run in production** using a Testcontainers `PostgreSQLContainer`. It exercises the real dialect, your real DDL/migrations (Flyway/Liquibase — [[06 - Data Access with Spring Data JPA]]), and real SQL features. The container adds seconds of startup, amortized by the shared static container and the context cache.

> [!tip] Keep Testcontainers fast
> Use a `static` container per class (or a shared singleton container started once for the whole JVM) so it isn't recreated per test. Reuse Docker layers by pinning a specific image tag. For local dev-time runs, Boot's `@ServiceConnection`-annotated `@TestConfiguration` beans (the `spring-boot-testcontainers` support, Boot 3.1+) let `spring-boot:test-run` / a `main`-method launcher boot the app against containers with zero external setup.

---

## 9. Testing secured endpoints, and building test data

**Security.** With `spring-security-test` on the classpath, `@WithMockUser` injects an authenticated principal into the `SecurityContext` so you can assert authorization without a real login ([[08 - Spring Security]]). Add Spring Security's `MockMvc`/client request post-processors for CSRF tokens on state-changing requests.

```java
@WebMvcTest(AdminController.class)
class AdminControllerTests {
    @Autowired MockMvcTester mvc;

    @Test @WithMockUser(roles = "ADMIN")
    void adminCanReachDashboard() {
        assertThat(mvc.get().uri("/admin")).hasStatusOk();
    }

    @Test @WithMockUser(roles = "USER")
    void nonAdminIsForbidden() {
        assertThat(mvc.get().uri("/admin")).hasStatus(HttpStatus.FORBIDDEN);
    }
}
```

**Test data builders.** Keep test setup readable and resilient by constructing domain objects through builders with sensible defaults, overriding only the field the test cares about — rather than repeating long constructor calls whose "noise" fields obscure the one that matters.

```java
Order order = anOrder().withStatus(Status.SHIPPED).build();   // only the relevant field is stated
```

> [!tip] Best practices, committed
> - **Constructor injection** so the base of the pyramid is wide and unit tests need no Spring.
> - **Pick the lowest tier that answers the question**: unit → slice → `@SpringBootTest`, in that order.
> - **One (or few) context configurations**: shared base classes / composed test annotations, so the cache is reused (§7).
> - **`@MockitoBean` for in-context mocks** (auto-reset); avoid `@DirtiesContext`.
> - **Testcontainers with your prod engine**, never H2, for anything schema- or SQL-dependent.
> - **Deterministic tests**: fixed `Clock`, no reliance on external network or test-execution order; roll back or reset state per test.

---

## 10. Choosing a test type

| | **Unit** | **Slice** (`@WebMvcTest`, `@DataJpaTest`, …) | **Full** `@SpringBootTest` |
|---|---|---|---|
| Spring context | none | thin, one layer | entire application |
| Speed | microseconds | fast (cached) | slowest |
| Fidelity | logic only | one real layer | everything, real HTTP/DB |
| Collaborators | Mockito mocks | `@MockitoBean` for excluded layers | mostly real; mock only externals |
| **When to pick** | **default** — business logic, branching, validation rules | one layer's framework behaviour (routing, mapping, JSON, outbound HTTP) | true cross-layer/integration paths, security + tx flows |

| Database in tests | **Testcontainers (real Postgres)** | **H2 (embedded)** |
|---|---|---|
| Fidelity to prod | exact engine, dialect, SQL features | approximation; compatibility-mode only |
| Startup cost | seconds (amortized: static container + cache) | milliseconds |
| Catches dialect/JSONB/upsert/sequence bugs | yes | no — hides them |
| **When to pick** | **anything schema- or SQL-dependent** (the default) | throwaway spikes where DB behaviour is irrelevant |

> [!important] Caveats & risk mitigation (summary)
> - **Context loading is the cost.** Every tier decision and the cache (§7) trace back to this one fact.
> - **Don't `@SpringBootTest` everything** (§6) — it's the classic slow-suite cause.
> - **Guard the cache** (§7): standardize config, avoid `@DirtiesContext`, watch the context count.
> - **Constructor-inject** (§2) — field injection makes classes un-unit-testable.
> - **Reset mocks** (§4) — prefer auto-reset `@MockitoBean` over hand-managed mock beans.
> - **Real DB, not H2** (§8) — you should test the database you deploy.
> - **Version facts are volatile.** The `@MockBean → @MockitoBean` rename (deprecated 3.4, removed 4.0), `MockMvcTester`/`RestTestClient` availability, `@ServiceConnection` (since 3.1), JUnit 6 / Framework 7 / Boot 4.1 baselines — **re-verify** against the current reference.

---

## 11. In practice

```java
// A shared base class collapses many integration tests onto ONE cached context (§7)
@SpringBootTest(webEnvironment = WebEnvironment.RANDOM_PORT)
@Testcontainers
abstract class IntegrationTestBase {

    @Container @ServiceConnection                 // real Postgres, auto-wired (Boot 3.1+)
    static PostgreSQLContainer<?> postgres = new PostgreSQLContainer<>("postgres:16");

    @Autowired RestTestClient client;             // Framework 7 / Boot 4 — HIGH-CHURN
}

class CheckoutFlowTests extends IntegrationTestBase {   // same config key → reuses the cached context

    @MockitoBean PaymentGateway gateway;          // only the EXTERNAL dependency is mocked

    @Test @WithMockUser(roles = "CUSTOMER")
    void placeOrderChargesAndPersists() {
        given(gateway.charge(any())).willReturn(Receipt.approved("txn-1"));

        client.post().uri("/checkout").body(anOrder().build())
              .exchange().expectStatus().isCreated();

        then(gateway).should().charge(any());     // real controller, service, DB; mocked payment
    }
}
```

**Interview talking points to be able to defend:**
- "Loading a Spring context is the expensive part, so most of my tests are plain constructor-injected unit tests with Mockito — no context at all."
- "I use slices (`@WebMvcTest`, `@DataJpaTest`, `@JsonTest`, `@RestClientTest`) to test one layer's framework behaviour, and reserve `@SpringBootTest` for genuine integration paths."
- "The test context cache is the biggest speed lever: identical configuration is cached and reused, so I standardize config and avoid `@DirtiesContext`, which busts it."
- "`@MockBean`/`@SpyBean` were deprecated in Boot 3.4 and removed in 4.0 — the current annotations are `@MockitoBean`/`@MockitoSpyBean` from Spring Framework itself, and they auto-reset between tests."
- "I test against real Postgres via Testcontainers with `@ServiceConnection`, not H2 — H2 hides dialect, JSONB, upsert and sequence differences that break in production."

---

## 12. Sources

- [Spring Boot Reference — Testing (slices, `@SpringBootTest`, web environment)](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [Spring Boot Reference — Testcontainers support & `@ServiceConnection`](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html)
- [Spring Boot Blog — Improved Testcontainers Support in Spring Boot 3.1 (`@ServiceConnection`)](https://spring.io/blog/2023/06/23/improved-testcontainers-support-in-spring-boot-3-1/)
- [Spring Framework Reference — `@MockitoBean` and `@MockitoSpyBean`](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-mockitobean.html)
- [Spring Framework Reference — Context caching (TestContext framework)](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html)
- [Spring Framework Reference — MockMvc AssertJ integration (`MockMvcTester`)](https://docs.spring.io/spring-framework/reference/testing/mockmvc/assertj.html)
- [Spring Framework Reference — `RestTestClient`](https://docs.spring.io/spring-framework/reference/testing/resttestclient.html)
- [Testcontainers for Java — documentation](https://java.testcontainers.org/)
- [GitHub — Spring Boot issue #39860: Deprecate `@MockBean` and `@SpyBean`](https://github.com/spring-projects/spring-boot/issues/39860)
