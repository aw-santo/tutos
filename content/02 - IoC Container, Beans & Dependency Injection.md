---
title: IoC Container, Beans & Dependency Injection
tags:
  - spring
  - spring-boot
  - dependency-injection
  - beans
  - ioc
  - senior
aliases:
  - IoC Container
  - Dependency Injection
  - Bean Lifecycle
status: ready
created: 2026-07-09
---

# IoC Container, Beans & Dependency Injection

> [!abstract] Scope
> The engine underneath every Spring app: the **IoC container** that reads bean *definitions*, instantiates them, and injects their collaborators so your code never calls `new` on its dependencies. We cover `ApplicationContext` vs `BeanFactory`, how definitions get registered, the injection styles and *why constructor injection wins*, `@Autowired` resolution, scopes and the singleton-holds-a-prototype trap, the full **bean lifecycle**, circular dependencies, and — the senior differentiator — the **AOP proxy model** and the self-invocation gotcha that silently disables `@Transactional`/`@Cacheable`. This is the container the auto-configured beans from [[01 - Spring Boot Fundamentals & Auto-Configuration]] actually live in; the proxy mechanics here are exactly what power [[07 - Transactions & Data Consistency]] and [[09 - Caching]].

Related: [[00 - Spring Boot Index]], [[01 - Spring Boot Fundamentals & Auto-Configuration]], [[07 - Transactions & Data Consistency]], [[09 - Caching]]

![[ioc-container.gif|720]]

*You hand the container bean definitions (via component scan or `@Bean` methods); it instantiates the singletons in dependency order, then injects each bean's collaborators — inverting control so objects never construct their own dependencies.*

---

## 1. Inversion of Control: the one idea

**Inversion of Control** means an object does not create or look up its collaborators — the container creates them and *hands them in*. **Dependency Injection** is the concrete technique Spring uses to do that. The payoff is decoupling: your `OrderService` declares "I need a `PaymentGateway`" and never knows which implementation, how it was built, or its lifecycle.

```java
// WITHOUT IoC — the class is welded to a concrete implementation and its construction
class OrderService {
    private final PaymentGateway gateway = new StripeGateway(apiKey, httpClient); // rigid, untestable
}

// WITH IoC — the container supplies a fully-built collaborator; this class only *uses* it
@Service
class OrderService {
    private final PaymentGateway gateway;
    OrderService(PaymentGateway gateway) { this.gateway = gateway; }  // "give me one"
}
```

> [!tip] The one-sentence framing interviewers want
> "The container owns object creation and wiring; my classes declare *what* they need, not *how* to build it. That inversion is what makes the code testable, swappable, and free of `new` on its dependencies." Keep the vocabulary straight: IoC is the principle, DI is the mechanism, and the `ApplicationContext` is the runtime that performs it.

---

## 2. The container: `ApplicationContext` vs `BeanFactory`

Both are IoC containers, but `BeanFactory` is the bare interface — lazy bean instantiation and wiring, nothing else. `ApplicationContext` **extends** it and is what you actually use.

| Capability | `BeanFactory` | `ApplicationContext` |
|---|---|---|
| Instantiate & wire beans | yes | yes |
| Auto-register `BeanPostProcessor` / `BeanFactoryPostProcessor` | manual | **automatic** |
| Annotation processing (`@Autowired`, `@Transactional`, etc.) | manual | **automatic** |
| `ApplicationEvent` publishing | no | **yes** |
| `MessageSource` (i18n) & `Resource` loading | no | **yes** |
| Eager singleton instantiation at startup | no (lazy) | **yes** — fail fast |

> [!important] Use `ApplicationContext` — the eager-init difference matters
> Spring's own guidance is to "use an `ApplicationContext` unless you have a good reason not to." The practical reason is **fail-fast**: `ApplicationContext` instantiates all non-lazy singletons during startup, so a misconfigured or missing dependency blows up at boot with a clear stack trace — not on the first request in production. In Boot the context is created for you (`AnnotationConfigApplicationContext` for a plain app, a servlet/reactive variant for web); you rarely touch `BeanFactory` directly.

---

## 3. How bean definitions get registered

A bean starts life as a **`BeanDefinition`** — metadata (class, scope, dependencies, init/destroy methods) registered *before* any instance exists. There are two idiomatic sources:

**(a) Component scanning + stereotypes** — Spring scans packages and turns annotated classes into definitions automatically:

```java
@Service                       // a @Component; scanned and registered as a singleton named "orderService"
class OrderService { /* ... */ }
```

| Stereotype | Marks a… | Extra behaviour beyond `@Component` |
|---|---|---|
| `@Component` | generic Spring-managed bean | none — the base |
| `@Service` | business-logic bean | semantic only (readability, aspect targeting) |
| `@Repository` | persistence bean | **translates native/JPA exceptions** into Spring's `DataAccessException` |
| `@Controller` / `@RestController` | web endpoint | picked up by Spring MVC handler mapping |

They are functionally near-identical, but the labels carry intent and `@Repository` actually *does* something (exception translation). Use the specific stereotype that fits the layer.

**(b) `@Bean` methods in a `@Configuration` class** — for beans you can't annotate (third-party types) or that need construction logic:

```java
@Configuration
class InfraConfig {
    @Bean
    RestClient paymentRestClient(PaymentProperties props) {   // method name = bean name
        return RestClient.builder().baseUrl(props.baseUrl()).build();
    }
}
```

> [!warning] Gotcha #1 — `@Bean` inter-method calls and `proxyBeanMethods`
> By default `@Configuration` runs in **"full mode"** (`proxyBeanMethods = true`): Spring generates a **CGLIB subclass** of the config class so that when one `@Bean` method calls another (`new ServiceB(serviceA())`), the call is intercepted and returns the *existing singleton*. Set `proxyBeanMethods = false` ("lite mode") — as Boot's own auto-config does for speed — and that same `serviceA()` call is a **plain Java call that builds a brand-new instance every time**, quietly giving you two `ServiceA` objects where you expected one shared singleton.
> **Mitigation:** never call one `@Bean` method from another. Express the dependency as a **method parameter** (`ServiceB serviceB(ServiceA a)`) — Spring injects the managed singleton regardless of proxy mode, and you can safely keep `proxyBeanMethods = false`.

---

## 4. Injection styles: constructor vs setter vs field

There are three ways the container can inject a collaborator. They are not equal, and the choice is a senior signal.

```java
// CONSTRUCTOR (the standard) — final fields, mandatory deps, no Spring annotation needed
@Service
class OrderService {
    private final PaymentGateway gateway;
    private final InventoryClient inventory;
    OrderService(PaymentGateway gateway, InventoryClient inventory) {  // single ctor → @Autowired implicit
        this.gateway = gateway;
        this.inventory = inventory;
    }
}

// SETTER — good for genuinely OPTIONAL deps with a sensible default
@Service
class ReportService {
    private Formatter formatter = Formatter.DEFAULT;
    @Autowired(required = false) void setFormatter(Formatter f) { this.formatter = f; }
}

// FIELD — concise, but avoid (reasons below)
@Service
class BadService {
    @Autowired private PaymentGateway gateway;   // reflection-set, non-final, hidden dependency
}
```

| Style | Fields `final`? | Deps visible in API? | Testable without Spring? | When to pick |
|---|---|---|---|---|
| **Constructor** | **yes** | **yes** (in the signature) | **yes** — just `new` it with mocks | **the default** — all mandatory dependencies |
| **Setter** | no | yes (setter exists) | yes | genuinely optional deps, or reconfigurable ones |
| **Field** | no | **no** (hidden) | **no** — needs reflection/Spring | avoid; tolerable only in throwaway `@Configuration`/tests |

> [!important] Why constructor injection is the standard
> Spring's team "generally advocates constructor injection" for four concrete reasons: (1) **immutability** — fields can be `final`; (2) **guaranteed non-null** — the object cannot exist in a half-wired state, deps are present the instant construction returns; (3) **mandatory-by-design** — a required collaborator is a required constructor argument, enforced by the compiler; (4) **no framework coupling** — a single constructor needs *no* `@Autowired` at all, so the class is a plain object you can unit-test with `new`. A bonus: a constructor with too many arguments *screams* that the class has too many responsibilities — a design smell the other styles hide.

> [!warning] Gotcha #2 — field injection hides dependencies and breaks tests
> `@Autowired private Foo foo;` looks tidy but it is the worst option. The dependency is invisible from the public API, the field cannot be `final` (so the object is mutable and can sit half-initialised), and — the killer — you **cannot instantiate the class in a plain unit test**: there is no constructor to pass mocks to, forcing reflection or a full Spring context just to test one method. It also silently permits unlimited dependencies, masking bloated classes.
> **Mitigation:** use constructor injection everywhere. With Lombok, `@RequiredArgsConstructor` generates the constructor from `final` fields so it is as terse as field injection with none of the cost.

---

## 5. `@Autowired` resolution, `@Primary`, `@Qualifier`

Spring resolves an injection point **by type first**, then disambiguates by name. When exactly one candidate matches, you're done. When several beans satisfy the same type, resolution fails with `NoUniqueBeanDefinitionException` unless you break the tie:

```java
interface PaymentGateway {}
@Component @Primary class StripeGateway  implements PaymentGateway {}  // the default winner
@Component            class PaypalGateway implements PaymentGateway {}

@Service
class Checkout {
    Checkout(PaymentGateway gateway,                              // gets Stripe via @Primary
             @Qualifier("paypalGateway") PaymentGateway backup) {} // explicitly ask for PayPal
}
```

- **`@Primary`** marks *one* bean as the default when multiple candidates exist — set-it-once, applies everywhere.
- **`@Qualifier("name")`** overrides at a *specific* injection point — more explicit, wins over `@Primary`.
- **Optional dependencies:** declare the parameter as `Optional<Foo>`, `@Nullable Foo`, or `@Autowired(required = false)` — absent bean → empty/null instead of a startup failure.
- **All of them / lazy lookup:** inject `List<PaymentGateway>` (every implementation, order via `@Order`) or `ObjectProvider<PaymentGateway>` for lazy, optional, or on-demand retrieval without a hard startup dependency.

> [!tip] `@Primary` for the common default, `@Qualifier` for the exception
> Set `@Primary` on the implementation 90% of call sites want, then reach for `@Qualifier` only at the few places that need the alternative. This keeps most injection points clean while remaining explicit exactly where it matters. `ObjectProvider<T>` is the modern, null-safe way to express "maybe there's a bean" — prefer it over `required = false`.

---

## 6. Bean scopes & the prototype-in-singleton trap

A scope controls **how many instances** the container manages and how long they live.

| Scope | One instance per… | Typical use |
|---|---|---|
| `singleton` (default) | container | stateless services, repositories — almost everything |
| `prototype` | **each injection / lookup** | stateful, short-lived helpers you want a fresh copy of |
| `request` | HTTP request (web only) | per-request data holder |
| `session` | HTTP session (web only) | per-user session state |
| `application` / `websocket` | `ServletContext` / WebSocket | rarely needed |

> [!warning] Gotcha #3 — a prototype injected into a singleton is created **once**
> Scope is resolved **at the injection point's creation time**. Inject a `prototype` bean straight into a `singleton`, and Spring creates the prototype exactly once — when it builds the singleton — and that *same* instance is reused for the life of the app. The prototype scope is silently defeated; you think you get a fresh object per call and you don't.
> ```java
> @Service class Singleton {
>     @Autowired Prototype p;    // resolved ONCE — same p forever
> }
> ```

> [!tip] Break the scope mismatch with `ObjectProvider` (or `@Lookup`)
> To get a genuinely fresh prototype on each use, ask the container each time instead of holding a reference:
> ```java
> @Service
> class Singleton {
>     private final ObjectProvider<Prototype> provider;
>     Singleton(ObjectProvider<Prototype> provider) { this.provider = provider; }
>     void handle() { Prototype fresh = provider.getObject(); /* new instance per call */ }
> }
> ```
> Alternatives: a `@Lookup`-annotated method (Spring overrides it to return a fresh bean), a JSR-330 `jakarta.inject.Provider<T>`, or a **scoped proxy** (`@Scope(value = "request", proxyMode = TARGET_CLASS)`) — the standard fix for injecting a `request`/`session` bean into a singleton, where the proxy fetches the right instance per call.

---

## 7. The bean lifecycle

Knowing the ordered phases lets you hook the correct extension point instead of guessing. For a single bean:

```text
1. Instantiate            → container calls the constructor (constructor injection happens HERE)
2. Populate properties    → setter/field dependencies injected
3. *Aware callbacks       → BeanNameAware, ApplicationContextAware, etc.
4. BeanPostProcessor      → postProcessBeforeInitialization(...)   ← proxies can be created around here
5. Initialization         → @PostConstruct → InitializingBean.afterPropertiesSet() → @Bean(initMethod)
6. BeanPostProcessor      → postProcessAfterInitialization(...)    ← AOP proxy typically wrapped HERE
7. IN USE                 → the fully-initialised (possibly proxied) bean serves the app
8. Destruction            → @PreDestroy → DisposableBean.destroy() → @Bean(destroyMethod)   (on context close)
```

```java
@Component
class ConnectionPool {
    private DataSource ds;
    ConnectionPool(DataSource ds) { this.ds = ds; }         // (1)+(2)

    @PostConstruct void warmUp()  { /* open a few connections */ }   // (5)  jakarta.annotation
    @PreDestroy    void drain()   { /* close pool cleanly     */ }   // (8)  jakarta.annotation
}
```

> [!important] `BeanPostProcessor` is where the "magic" happens — and it explains proxies
> `@Transactional`, `@Cacheable`, `@Async`, and security advice are **not** compiled into your class. A `BeanPostProcessor` inspects each bean *after* initialization (step 6) and, if it carries such annotations, **replaces the bean in the container with a proxy** that wraps it. Prototype beans are the exception: Spring does not manage their full lifecycle, so **`@PreDestroy` never runs on a prototype** — the container hands it over and forgets it. Note the namespace: lifecycle annotations are `jakarta.annotation.*` on Jakarta EE 11, **not** the old `javax.*`. **[HIGH-CHURN: Jakarta EE 11 / `jakarta.*` is current as of mid-2026 — verify the namespace before relying on it.]**

---

## 8. Lazy initialization

By default `ApplicationContext` instantiates every singleton eagerly at startup (§2). `@Lazy` defers a bean's creation until it is first needed:

```java
@Component
@Lazy                                  // not built until something asks for it
class ExpensiveReportEngine { /* heavy to construct */ }
```

> [!tip] Lazy is a scalpel, not a global switch
> Use `@Lazy` for genuinely expensive, rarely-used beans, or to break an occasional cycle (§9). Avoid the global `spring.main.lazy-initialization=true`: it speeds boot but **trades away fail-fast** — a misconfigured bean now explodes on first request, in production, instead of at startup. Keep eager init as the default; make individual beans lazy deliberately.

---

## 9. Circular dependencies

A cycle is `A` needs `B` and `B` needs `A` (directly or through a chain). How Spring reacts depends on the injection style:

- **Constructor ↔ constructor:** *unresolvable*. To build `A` Spring must first build `B`, but to build `B` it must first build `A` — neither can complete. Spring throws **`BeanCurrentlyInCreationException`** at startup.
- **Setter/field:** historically resolvable via Spring's three-level cache (it injects a partially-constructed reference), but **Spring Boot disables this by default since 2.6** — even a setter cycle now fails at startup unless you opt back in.

```java
@Service class A { A(B b) {} }     // ↖ needs B
@Service class B { B(A a) {} }     // ↗ needs A   → BeanCurrentlyInCreationException at boot
```

> [!warning] Gotcha #4 — a constructor cycle is a *design smell*, not a config bug
> The temptation is to reach for `spring.main.allow-circular-references=true` or sprinkle `@Lazy` to make the error disappear. That restores the old lenient behaviour and hides the real problem: two beans are mutually entangled, which means the responsibilities are split along the wrong seam. It also produces fragile init ordering and beans that are hard to test in isolation.
> **Mitigation, in order of preference:** (1) **refactor** — extract the shared logic into a third bean both depend on, or merge them if they're really one concern; (2) invert one direction with an **event** or a callback interface; (3) as a last resort, break the cycle with `@Lazy` on one injection point (Spring injects a proxy, deferring the real lookup). Reaching for the global `allow-circular-references` flag is the answer that fails the interview.

---

## 10. The AOP proxy model & self-invocation

This is the topic that separates senior from mid-level, because it explains *why* `@Transactional` and `@Cacheable` sometimes silently do nothing. Spring implements those annotations with **proxies** (§7): the container gives everyone a proxy that runs the advice (open a transaction, check the cache) *before* delegating to your real object.

Spring chooses the proxy type automatically:

| Proxy | Used when | How it works | Note |
|---|---|---|---|
| **JDK dynamic proxy** | the bean **implements an interface** | runtime `Proxy` implementing the same interface(s) | only interface-declared methods are advised |
| **CGLIB** | the bean has **no interface** (or `proxyTargetClass=true`) | runtime **subclass** overriding methods | can't proxy `final` classes/methods |

```java
@Service
class BillingService {
    @Transactional
    public void chargeAll(List<Order> orders) {
        for (Order o : orders) charge(o);   // ⚠ SELF-INVOCATION — see gotcha
    }
    @Transactional(propagation = REQUIRES_NEW)
    public void charge(Order o) { /* expected to run in its OWN tx */ }
}
```

> [!warning] Gotcha #5 — self-invocation silently disables `@Transactional`/`@Cacheable`/`@Async`
> The advice lives on the **proxy**, not on your object. When an external caller invokes `chargeAll`, it goes through the proxy and the transaction advice runs. But inside `chargeAll`, the call to `charge(o)` is `this.charge(o)` — a **direct call on the target object that never touches the proxy**. Spring's own words: "self invocation via an explicit or implicit `this` reference will bypass the advice." So `charge`'s `REQUIRES_NEW` is ignored, `@Cacheable` results aren't cached, `@Async` runs on the caller's thread. No error — it just quietly doesn't happen. This is one of the most-asked senior Spring questions precisely because the code *looks* correct.
> **Mitigation:** (1) **move the annotated method to a separate bean** so the call crosses a proxy boundary — the cleanest fix; (2) **self-inject** — inject `ObjectProvider<BillingService>` (or the bean itself via a setter) and call `self.charge(o)` so the invocation goes through the proxy; (3) as a last resort `((BillingService) AopContext.currentProxy()).charge(o)` with `exposeProxy = true` — but it couples your code to Spring AOP. Prefer option 1.

---

## 11. Caveats & best practices (summary)

- **Constructor injection, always (§4).** `final` fields, non-null guarantees, plain-`new` testability, and a constructor that flags bloated classes. Field injection is a code-review reject.
- **Never call one `@Bean` method from another (§3).** Pass dependencies as parameters so lite-mode config can't silently double-instantiate.
- **Watch the scope mismatch (§6).** A prototype (or request/session bean) in a singleton needs `ObjectProvider`/`@Lookup`/a scoped proxy, or it's created exactly once.
- **Hook the right lifecycle phase (§7).** `@PostConstruct` for cheap init; heavy startup work belongs in an `ApplicationRunner` (see [[01 - Spring Boot Fundamentals & Auto-Configuration]]), never a constructor.
- **A circular dependency is a redesign signal (§9)** — refactor to a third bean; don't flip `allow-circular-references`.
- **Remember the proxy for `@Transactional`/`@Cacheable`/`@Async` (§10).** Self-invocation bypasses it — annotated methods must be reached from *outside* the bean. Directly relevant to [[07 - Transactions & Data Consistency]] and [[09 - Caching]].
- **Version facts are volatile.** Jakarta EE 11 (`jakarta.*` lifecycle annotations), Framework 7 / Boot 4.1.x, JDK 17 baseline are current as of mid-2026 — **re-verify** before relying on exact names or defaults.

**Interview talking points to be able to defend:**
- "IoC is the principle, DI is the mechanism; the container owns creation and wiring so my classes never `new` their dependencies."
- "I use constructor injection for immutability, non-null guarantees, and to test with a plain `new` — field injection hides deps and can't be unit-tested."
- "`@Primary` sets the default candidate; `@Qualifier` overrides at a specific point and wins over `@Primary`."
- "A prototype injected into a singleton is created once — I use `ObjectProvider` or a scoped proxy to get a fresh instance."
- "`@Transactional` is a proxy; calling an annotated method from within the same bean (`this.method()`) bypasses the proxy and the transaction/cache/async advice silently never runs. I move it to another bean or self-inject."
- "Constructor circular deps throw `BeanCurrentlyInCreationException` and signal a design smell — I refactor rather than flip `allow-circular-references`."

---

## 12. In practice

```java
// A clean, testable service: constructor injection, final fields, no field @Autowired
@Service
class CheckoutService {

    private final PaymentGateway gateway;                 // @Primary picks the default impl
    private final ObjectProvider<AuditContext> auditCtx;  // prototype/request-scoped, fetched per call

    CheckoutService(PaymentGateway gateway, ObjectProvider<AuditContext> auditCtx) {  // no @Autowired needed
        this.gateway = gateway;
        this.auditCtx = auditCtx;
    }

    @Transactional                                        // proxy-driven — call this from OUTSIDE the bean
    public Receipt checkout(Cart cart) {
        AuditContext ctx = auditCtx.getObject();          // fresh instance each checkout (§6)
        return gateway.charge(cart.total(), ctx);
    }
}

// Trivial to unit-test WITHOUT Spring — the whole point of constructor injection
class CheckoutServiceTest {
    @Test void chargesTheCart() {
        var gw = mock(PaymentGateway.class);
        var svc = new CheckoutService(gw, () -> new AuditContext());  // just `new` it
        // ... verify(gw).charge(...)
    }
}
```

```properties
# application.properties
spring.main.lazy-initialization=false        # keep eager init → fail fast at startup (§8)
spring.main.allow-circular-references=false  # default since Boot 2.6 — a cycle is a design smell (§9)
```

---

## 13. Sources

- [Spring Framework — The IoC Container (introduction)](https://docs.spring.io/spring-framework/reference/core/beans/introduction.html)
- [Spring Framework — `BeanFactory` vs `ApplicationContext`](https://docs.spring.io/spring-framework/reference/core/beans/beanfactory.html)
- [Spring Framework — Dependency Injection (constructor vs setter, circular deps)](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html)
- [Spring Framework — Autowiring, `@Primary` & `@Qualifier`](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html)
- [Spring Framework — Bean Scopes (singleton, prototype, request/session, scoped proxies)](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html)
- [Spring Framework — Bean lifecycle & customization callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
- [Spring Framework — Java-based configuration & `proxyBeanMethods` (full vs lite)](https://docs.spring.io/spring-framework/reference/core/beans/java/basic-concepts.html)
- [Spring Framework — AOP proxying mechanisms & self-invocation](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Boot Reference — circular references disabled by default](https://docs.spring.io/spring-boot/reference/features/spring-application.html)
