---
title: 04 - Building REST APIs
tags:
  - spring
  - spring-boot
  - rest
  - web-mvc
  - validation
  - senior
aliases:
  - REST Controllers
  - REST APIs
  - Web MVC Controllers
status: ready
created: 2026-07-09
---

# Building REST APIs

> [!abstract] Scope
> How to build correct, defensible REST endpoints with Spring MVC: mapping requests, binding and **validating** input at the edge, shaping output through **DTOs** (never JPA entities), and returning consistent errors as **RFC 9457 Problem Details**. We finish with the API-evolution questions seniors are expected to answer — versioning (including the new first-class support in Framework 7 / Boot 4), pagination, OpenAPI, and idempotency. For the servlet/reactive machinery underneath, see [[05 - Web Layer & Embedded Servers - MVC vs WebFlux]]; for locking these endpoints down, see [[08 - Spring Security]].

Related: [[00 - Spring Boot Index]], [[05 - Web Layer & Embedded Servers - MVC vs WebFlux]], [[08 - Spring Security]], [[13 - Resilience & Production Readiness]]

![[dto-vs-entity.gif|720]]

*The same request body bound two ways: an entity has no defense against an over-posted field, a DTO simply doesn't have one to bind.*

---

## 1. `@RestController` vs `@Controller` + `@ResponseBody`

A classic `@Controller` returns a **view name** — a string the `ViewResolver` maps to a template (Thymeleaf, JSP). To return *data* instead, each method needs `@ResponseBody`, which tells Spring to run the return value through an `HttpMessageConverter` (Jackson for JSON) and write it straight to the response body.

```java
@RestController                       // = @Controller + @ResponseBody on every method
@RequestMapping("/api/orders")
public class OrderController { ... }
```

`@RestController` is a meta-annotation that composes `@Controller` and `@ResponseBody`, so every handler serializes its return value by default. Use `@Controller` only when the same class also renders views; for a JSON/XML API, `@RestController` is the correct and idiomatic choice.

> [!tip] The framing interviewers want
> "`@RestController` means every method is `@ResponseBody` — I'm returning a *representation*, not a view name. That one distinction is why I don't accidentally return the string `"order"` and get a 404 from a view resolver looking for an `order.html`."

---

## 2. Request mapping & binding

The `@RequestMapping` family maps HTTP verbs to methods; the parameter annotations bind parts of the request into typed arguments.

```java
@GetMapping("/{id}")                                   // path + verb
public OrderResponse get(@PathVariable Long id) { ... }

@GetMapping                                            // /api/orders?status=OPEN&page=0
public Page<OrderResponse> list(
        @RequestParam(defaultValue = "OPEN") Status status,
        @RequestParam(required = false) String q,
        Pageable pageable) { ... }                     // §10

@PostMapping                                           // create
@ResponseStatus(HttpStatus.CREATED)
public OrderResponse create(@Valid @RequestBody CreateOrderRequest body) { ... }

@PutMapping("/{id}")                                   // full replace (idempotent)
public OrderResponse replace(@PathVariable Long id,
                             @Valid @RequestBody UpdateOrderRequest body) { ... }

@DeleteMapping("/{id}")
@ResponseStatus(HttpStatus.NO_CONTENT)
public void delete(@PathVariable Long id) { ... }
```

| Annotation | Binds from | Notes |
|---|---|---|
| `@PathVariable` | a `{template}` segment in the URI | identity of a resource (`/orders/42`) |
| `@RequestParam` | query string or form field | filters, flags; supports `defaultValue`, `required` |
| `@RequestBody` | the deserialized request body | one per method; the payload DTO |
| `@RequestHeader` / `@CookieValue` | a header / cookie | e.g. `Idempotency-Key` (§12) |

> [!tip] Verb semantics are part of the contract
> Map verbs to intent, not convenience: **GET** never mutates (safe, cacheable), **PUT** replaces and is **idempotent** (same call twice = same state), **PATCH** partially updates, **POST** creates and is *not* idempotent. Interviewers probe this because getting it wrong breaks caching, retries, and client expectations.

---

## 3. Content negotiation & Jackson 3

Spring picks a representation by matching the request's `Accept` header against each handler's `produces`, and validates the request body against `consumes`. Serialization runs through `HttpMessageConverter`s — for JSON that is **Jackson**, now **Jackson 3** in Boot 4.

```java
@PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE,   // reject anything but JSON → 415
             produces = MediaType.APPLICATION_JSON_VALUE)   // Accept mismatch → 406
public OrderResponse create(@Valid @RequestBody CreateOrderRequest body) { ... }
```

- A body whose `Content-Type` isn't in `consumes` → **415 Unsupported Media Type**.
- An `Accept` the endpoint can't satisfy via `produces` → **406 Not Acceptable**.
- Shape the JSON with Jackson annotations (`@JsonProperty`, `@JsonIgnore`, `@JsonView`, `@JsonFormat`) on the **DTO**, never on the entity (§4).

> [!warning] Jackson 3 is a breaking upgrade — high-churn
> Boot 4 ships **Jackson 3**, whose core/databind types moved to the new `tools.jackson` namespace (the annotations remain under `com.fasterxml.jackson.annotation`), and several defaults changed (e.g. stricter handling of unknown properties). Custom `ObjectMapper`/`JsonMapper` beans, mixins, and third-party libraries (springdoc has had a Jackson 2↔3 lag) can break on upgrade.
> **Mitigation:** rely on Boot's auto-configured mapper where you can, keep Jackson customization in a single `Jackson2ObjectMapperBuilderCustomizer`/`JsonMapper` bean, and re-verify against the current reference. **[HIGH-CHURN: confirm Jackson 3 package/defaults for your exact Boot version.]**

---

## 4. DTOs vs entities — never expose your JPA entities

The single most important design rule in this module. A **DTO** (Data Transfer Object) is a purpose-built class for one request or response shape. A JPA **entity** is a persistence-mapped, mutable, proxied object tied to a Hibernate `Session`. Binding requests to and serializing responses from entities directly is a recipe for three concrete, painful bugs.

```java
public record CreateOrderRequest(                      // INPUT DTO — only client-settable fields
        @NotBlank String customerRef,
        @NotEmpty @Valid List<LineItemRequest> items) {}

public record OrderResponse(                           // OUTPUT DTO — only what the client may see
        Long id, String customerRef, Status status,
        BigDecimal total, Instant createdAt) {

    static OrderResponse from(Order e) {               // explicit mapping — the boundary
        return new OrderResponse(e.getId(), e.getCustomerRef(),
                e.getStatus(), e.getTotal(), e.getCreatedAt());
    }
}
```

> [!warning] Three ways exposing entities bites you
> 1. **Lazy-load serialization failures.** Jackson walks a `@ManyToOne`/`@OneToMany` lazy proxy *after* the transaction closed → `LazyInitializationException`, or it eagerly serializes the whole object graph and leaks unrelated data (and N+1 queries). See [[06 - Data Access with Spring Data JPA]].
> 2. **Over-posting / mass assignment.** If you bind `@RequestBody Order`, a malicious client can set fields you never intended — `role`, `status`, `balance`, `id` — and your `save()` persists them. This is a real vulnerability class, not a style nit.
> 3. **Coupled contract.** Every schema change now leaks into your API and vice-versa; you can't rename a column without breaking clients.

> [!important] Best practice — DTOs at both edges, mapped explicitly
> Accept an **input DTO** carrying *only* client-settable fields, and return an **output DTO** carrying *only* what the client may see. Map between DTO and entity in one place (a factory method, or MapStruct). This kills over-posting by construction (the entity's `id`/`status` simply aren't bindable), avoids lazy-loading surprises, and lets the persistence model and the API evolve independently. Treat "we return entities directly" as an automatic code-review block.

---

## 5. Bean Validation at the edge

Validate untrusted input *before* it reaches your service layer, using **Jakarta Bean Validation** (`jakarta.validation`, **not** the old `javax`) with **Hibernate Validator 9** as the implementation (pulled in by `spring-boot-starter-validation`).

```java
public record CreateOrderRequest(
        @NotBlank                         String customerRef,
        @Email                            String notifyEmail,
        @NotEmpty @Valid                  List<LineItemRequest> items,   // @Valid → cascade
        @Size(max = 280)                  String note) {}

public record LineItemRequest(
        @NotNull  Long sku,
        @Positive @Max(999) int quantity) {}
```

```java
@PostMapping
public OrderResponse create(@Valid @RequestBody CreateOrderRequest body) { ... }  // triggers it
```

**`@Valid` vs `@Validated`:**

| | `@Valid` (jakarta) | `@Validated` (Spring) |
|---|---|---|
| Origin | Bean Validation standard | Spring |
| On a `@RequestBody` param | triggers body validation | also works |
| **Validation groups** | not supported | **supported** — `@Validated(OnCreate.class)` |
| Method-level (on `@RequestParam`/`@PathVariable`) | — | enable by putting `@Validated` on the class |

**Validation groups** let one DTO carry different rules per operation (e.g. `id` required on update but not create):

```java
public interface OnCreate {}
public interface OnUpdate {}

public record OrderPayload(
        @Null(groups = OnCreate.class) @NotNull(groups = OnUpdate.class) Long id,
        @NotBlank(groups = {OnCreate.class, OnUpdate.class}) String customerRef) {}

@PostMapping public OrderResponse create(@Validated(OnCreate.class) @RequestBody OrderPayload p) { ... }
@PutMapping("/{id}") public OrderResponse update(@Validated(OnUpdate.class) @RequestBody OrderPayload p) { ... }
```

**Custom constraint** (business rules the built-ins can't express):

```java
@Documented
@Constraint(validatedBy = SkuExistsValidator.class)
@Target(ElementType.FIELD) @Retention(RetentionPolicy.RUNTIME)
public @interface SkuExists {
    String message() default "unknown SKU";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}

@Component
class SkuExistsValidator implements ConstraintValidator<SkuExists, Long> {
    private final CatalogClient catalog;
    SkuExistsValidator(CatalogClient catalog) { this.catalog = catalog; }   // DI works here
    public boolean isValid(Long sku, ConstraintValidatorContext ctx) {
        return sku != null && catalog.exists(sku);
    }
}
```

> [!warning] Gotcha — forget `@Valid` and validation *silently* does nothing
> Constraint annotations on a DTO are **inert** unless something triggers validation. Omit `@Valid`/`@Validated` on the `@RequestBody` parameter and the framework binds the body and calls your method with an invalid object — **no error, no 400** — and the bad data flows into your service. This is a favourite interview trap because the annotations *look* like they're doing their job.
> **Mitigation:** the `@Valid` on the parameter is mandatory; make it a review checklist item, and write a test that posts an invalid body and asserts **400**.

---

## 6. Centralized error handling with `@RestControllerAdvice`

Never `try/catch` in every handler. Put one `@RestControllerAdvice` bean (a `@ControllerAdvice` + `@ResponseBody`) with `@ExceptionHandler` methods that translate exceptions into responses application-wide.

```java
@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    ProblemDetail handleNotFound(OrderNotFoundException ex) {              // §7
        ProblemDetail pd = ProblemDetail.forStatusAndDetail(HttpStatus.NOT_FOUND, ex.getMessage());
        pd.setType(URI.create("https://api.acme.com/errors/order-not-found"));
        pd.setTitle("Order not found");
        return pd;                                                         // → 404, application/problem+json
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)               // thrown by @Valid failure
    ProblemDetail handleValidation(MethodArgumentNotValidException ex) {
        ProblemDetail pd = ProblemDetail.forStatus(HttpStatus.BAD_REQUEST);
        pd.setTitle("Validation failed");
        pd.setProperty("errors", ex.getBindingResult().getFieldErrors().stream()
                .map(fe -> Map.of("field", fe.getField(), "reason", fe.getDefaultMessage()))
                .toList());                                                // structured, non-standard field
        return pd;
    }
}
```

> [!warning] Gotcha — leaking internals, wrong status, and the un-handled `MethodArgumentNotValidException`
> Three failures cluster here: (a) returning `ex.getMessage()` or a stack trace to the client — leaking table names, SQL, internal hostnames; (b) letting everything fall through to a generic **500** when the real answer is 400/404/409 — a validation failure returned as 500 tells the client to *retry*, which never helps; (c) forgetting that a failed `@Valid` throws **`MethodArgumentNotValidException`** (query/path constraint failures throw `HandlerMethodValidationException`) — leave it unhandled and the client gets an opaque 500 or Spring's default body instead of a clean 400 with field details.
> **Mitigation:** map each exception to its *correct* status; return a **generic** client-safe message and log the detail server-side with a correlation id; always add an explicit handler for the validation exceptions above (or let Boot's Problem Details support handle them — §7).

---

## 7. RFC 9457 Problem Details — the standard error body

Ad-hoc error JSON (`{"error": "..."}`) differs per endpoint and per team. [**RFC 9457** *Problem Details for HTTP APIs*](https://www.rfc-editor.org/rfc/rfc9457) standardizes it, and Spring implements it as **`ProblemDetail`** with the media type `application/problem+json`.

```json
{
  "type": "https://api.acme.com/errors/order-not-found",
  "title": "Order not found",
  "status": 404,
  "detail": "No order with id 42",
  "instance": "/api/orders/42",
  "errors": [ { "field": "quantity", "reason": "must be greater than 0" } ]
}
```

Standard fields are `type`, `title`, `status`, `detail`, `instance`; anything extra goes into the `properties` map (via `setProperty`) and Jackson unwraps it to top-level JSON through the registered `ProblemDetailJacksonMixin`.

**Turn on the built-in handling** so Spring renders *its own* exceptions (validation, 404, 405, 415…) as Problem Details, not just yours:

```properties
spring.mvc.problemdetails.enabled=true   # auto-configures a ResponseEntityExceptionHandler
```

> [!tip] `ErrorResponse` / `ErrorResponseException` and `ResponseEntityExceptionHandler`
> `ErrorResponse` is the contract (status + headers + `ProblemDetail` body) that **every** built-in Spring MVC exception implements; `ErrorResponseException` is a ready base class for your own exceptions. Extend **`ResponseEntityExceptionHandler`** in your advice to inherit correct Problem Detail handling for all framework exceptions and override only the hooks you care about. This is the committed 2026 pattern: standard body, standard media type, minimal custom code. **[HIGH-CHURN: verify the default value of `spring.mvc.problemdetails.enabled` for your Boot version — historically off by default.]**

---

## 8. `ResponseEntity` vs `@ResponseStatus`

Two ways to control the status line and headers.

| | `@ResponseStatus(HttpStatus.CREATED)` | `ResponseEntity<T>` |
|---|---|---|
| Where | annotation on method / exception | value returned from method |
| Status | **fixed** at compile time | **chosen at runtime** |
| Headers/body control | none (body is the return value) | full — `Location`, `ETag`, cache headers, body or none |
| When to pick | the status is always the same (e.g. `create` always 201) | status/headers depend on logic, or you must set headers |

```java
@PostMapping
public ResponseEntity<OrderResponse> create(@Valid @RequestBody CreateOrderRequest body,
                                            UriComponentsBuilder uri) {
    Order saved = service.create(body);
    URI location = uri.path("/api/orders/{id}").buildAndExpand(saved.getId()).toUri();
    return ResponseEntity.created(location)            // 201 + Location header — the correct create response
            .body(OrderResponse.from(saved));
}
```

> [!warning] Gotcha — wrong or lazy status codes
> Returning **200** for a create (should be **201 + `Location`**), **200** with an empty body for a not-found (should be **404**), or **500** for a client mistake (should be **400/409**) all break clients and monitoring. A `POST` that "succeeds" with an error message in a 200 body is invisible to every alerting rule watching 5xx/4xx rates.

---

## 9. API versioning — including Framework 7's built-in support

APIs must evolve without breaking existing clients. There are three classic transport strategies, and — new in **Spring Framework 7 / Boot 4** — first-class support that works across all of them.

| Strategy | Example | Pros | Cons | When to pick which |
|---|---|---|---|---|
| **URI path** | `GET /api/v2/orders` | dead-simple, visible, cache/log-friendly, easy to browse | "version" isn't really a resource; duplicated routes; ugly across many resources | public APIs, broad third-party audiences, when discoverability & curl-ability matter most |
| **Request header** | `API-Version: 2` | clean URIs; resource identity stays stable | invisible in a browser/logs; easy for clients to forget; harder to cache | internal / first-party clients you control, service-to-service |
| **Media-type (content negotiation)** | `Accept: application/vnd.acme.order.v2+json` | most "RESTful"; per-representation versioning | steepest client learning curve; awkward tooling | hypermedia/HATEOAS-mature APIs, fine-grained representation control |

**The new built-in (Framework 7 / Boot 4).** Instead of hand-rolling any of the above, declare a `version` on the mapping and choose *once* where the version is read from:

```java
@Configuration
class WebConfig implements WebMvcConfigurer {
    @Override
    public void configureApiVersioning(ApiVersionConfigurer configurer) {
        configurer.useRequestHeader("API-Version");    // or useQueryParam / usePathSegment(int) / useMediaTypeParameter
        // .addSupportedVersions("1.1", "1.2")          // else detected from @RequestMapping(version=...)
        // .setVersionRequired(true) / .setDefaultVersion("1.2")
    }
}

@RestController
@RequestMapping("/api/orders")
class OrderController {
    @GetMapping("/{id}")                                 // matches any version (fallback)
    OrderResponse v0(@PathVariable Long id) { ... }

    @GetMapping(path = "/{id}", version = "1.1")         // exact version 1.1
    OrderResponseV11 v11(@PathVariable Long id) { ... }

    @GetMapping(path = "/{id}", version = "1.2+")        // baseline: 1.2 and any supported version above
    OrderResponseV12 v12(@PathVariable Long id) { ... }
}
```

Version parsing defaults to `SemanticApiVersionParser` (major.minor.patch); a missing required version raises `MissingApiVersionException` (400) and an unknown one `InvalidApiVersionException` (400). Deprecations can emit RFC 9745 `Deprecation`/`Sunset` headers via `StandardApiVersionDeprecationHandler`.

> [!important] Prefer the built-in, and pin one strategy — high-churn
> Framework 7's versioning decouples the *strategy* (header/query/path/media-type — swappable in `configureApiVersioning`) from the *mapping* (`version="1.2+"`), which is exactly the flexibility hand-rolled solutions lacked. Adopt it, and **pick a single strategy org-wide** — mixing them fractures your clients. Because this API landed in Framework 7 and is still settling, **[HIGH-CHURN: verify `ApiVersionConfigurer` method names, the `version` attribute, and defaults against the current `docs.spring.io` reference before relying on them.]**

---

## 10. Pagination & sorting with `Pageable`

Never return an unbounded list — one `GET /orders` on a large table can OOM the server and the client. Accept a `Pageable` and return a `Page`.

```java
@GetMapping
public Page<OrderResponse> list(
        @RequestParam(required = false) Status status,
        @PageableDefault(size = 20, sort = "createdAt", direction = Sort.Direction.DESC) Pageable pageable) {
    return service.find(status, pageable).map(OrderResponse::from);   // Page<Entity> → Page<DTO>
}
```

Spring resolves `?page=0&size=20&sort=createdAt,desc` into the `Pageable` automatically. The response carries `content`, `totalElements`, `totalPages`, etc.

> [!tip] Cap the page size and map to DTOs
> Set a hard server-side maximum (`spring.data.web.pageable.max-page-size`) so a client can't request `size=1000000`. Always `.map()` the `Page<Entity>` to a `Page<DTO>` — the paging must not leak entities any more than a single response does (§4). For cursor/keyset pagination on very large or infinite feeds, prefer a keyset approach over `OFFSET` (see [[06 - Data Access with Spring Data JPA]]).

---

## 11. Documenting with OpenAPI (springdoc)

Add `springdoc-openapi-starter-webmvc-ui` and you get a generated OpenAPI 3 spec at `/v3/api-docs` and interactive Swagger UI at `/swagger-ui.html`, derived from your controllers, DTOs, and validation annotations.

```java
@Operation(summary = "Create an order")
@ApiResponse(responseCode = "201", description = "Created")
@ApiResponse(responseCode = "400", description = "Validation failed",
             content = @Content(schema = @Schema(implementation = ProblemDetail.class)))
@PostMapping
public ResponseEntity<OrderResponse> create(@Valid @RequestBody CreateOrderRequest body) { ... }
```

> [!warning] Gotcha — springdoc / Jackson 3 lag on Boot 4
> springdoc is a third-party project on its own release cadence; around the Boot 4 / Jackson 3 transition there were version-alignment gaps. **Mitigation:** pin the springdoc version its release notes state is compatible with your exact Boot version, and don't upgrade Boot and springdoc blindly. **[HIGH-CHURN: verify the compatible springdoc version.]**

---

## 12. Idempotency & ETags (briefly)

Two production concerns interviewers like to see you *mention*:

- **Idempotency for POST.** Retries (client timeout, gateway retry) can create duplicate resources. Accept an `Idempotency-Key` header, persist the key with the result of the first call, and on a repeat key return the original result instead of creating again. (`PUT`/`DELETE` are already idempotent by verb semantics; `POST` needs help.)
- **ETags & conditional requests.** Return an `ETag` (a version/hash of the resource); clients send `If-None-Match` on GET (get **304 Not Modified**, saving bandwidth) or `If-Match` on PUT to get **optimistic concurrency** — a **412 Precondition Failed** instead of silently overwriting a concurrent change. Spring's `ShallowEtagHeaderFilter` covers the simple GET case; use entity version fields for write concurrency (see [[06 - Data Access with Spring Data JPA]]).

---

## 13. Caveats & risk mitigation (summary)

- **DTOs at both edges, always (§4).** Never bind or serialize JPA entities — it invites over-posting, lazy-load failures, and a coupled contract. This is the non-negotiable one.
- **Validate at the edge and don't forget `@Valid` (§5).** The annotation on the parameter is what *runs* the constraints; without it validation is silent.
- **One error strategy: Problem Details (§6–§7).** Central `@RestControllerAdvice`, RFC 9457 bodies, correct statuses, generic client messages, detail logged server-side.
- **Right verbs, right status codes (§2, §8).** 201+`Location` for create, 404 for missing, 400/409 for client faults — not a blanket 200 or 500.
- **Bound your collections (§10).** Paginate and cap page size; nothing returns an unbounded list.
- **Version facts are volatile.** Boot 4.1.x / Framework 7 / Jakarta EE 11 / Jackson 3 / JDK 17 baseline are current as of mid-2026 — **re-verify** the API versioning API, Jackson 3 packages, Problem Details defaults, and springdoc compatibility before relying on them.

---

## 14. In practice

```java
@RestController
@RequestMapping("/api/orders")
@Validated                                              // enables method-level validation on params
class OrderController {

    private final OrderService service;
    OrderController(OrderService service) { this.service = service; }

    @GetMapping("/{id}")
    OrderResponse get(@PathVariable Long id) {
        return OrderResponse.from(service.getOrThrow(id));   // throws OrderNotFoundException → §6 → 404
    }

    @GetMapping
    Page<OrderResponse> list(@RequestParam(defaultValue = "OPEN") Status status,
                             @PageableDefault(size = 20) Pageable pageable) {
        return service.find(status, pageable).map(OrderResponse::from);
    }

    @PostMapping
    ResponseEntity<OrderResponse> create(@Valid @RequestBody CreateOrderRequest body,   // §5
                                         UriComponentsBuilder uri) {
        Order saved = service.create(body);                                             // §4 mapping inside
        URI location = uri.path("/api/orders/{id}").buildAndExpand(saved.getId()).toUri();
        return ResponseEntity.created(location).body(OrderResponse.from(saved));         // 201 + Location
    }
}
```

**Interview talking points to be able to defend:**
- "I never expose JPA entities — input and output DTOs stop over-posting by construction and avoid lazy-loading serialization failures; I map at the boundary."
- "Validation runs at the edge with Jakarta Bean Validation; the `@Valid` on the `@RequestBody` parameter is mandatory, and a failed one throws `MethodArgumentNotValidException`, which my advice turns into a 400 Problem Detail."
- "All errors are RFC 9457 `ProblemDetail` from one `@RestControllerAdvice`; I return generic client-safe messages and log the detail with a correlation id — no stack traces on the wire."
- "`@ResponseStatus` for fixed statuses, `ResponseEntity` when I need runtime status or headers like `Location`/`ETag`; create returns 201 + Location."
- "For versioning I'd standardize on one strategy; Framework 7's built-in `@RequestMapping(version=...)` plus `configureApiVersioning` decouples the transport from the mapping, so I'd adopt that — flagging it's a new, still-settling API."

---

## 15. Sources

- [Spring Framework Reference — Error Responses / RFC 9457 Problem Details](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html)
- [Spring Framework Reference — API Versioning (Web MVC)](https://docs.spring.io/spring-framework/reference/web/webmvc-versioning.html)
- [Spring Framework Reference — MVC Config: API Version (`ApiVersionConfigurer`)](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/api-version.html)
- [Spring Framework Reference — `@RequestMapping` (version attribute)](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html)
- [Spring Framework API — `ProblemDetail`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/ProblemDetail.html)
- [Spring Boot Reference — Developing web applications (Spring MVC)](https://docs.spring.io/spring-boot/reference/web/servlet.html)
- [Spring Boot Reference — JSON (Jackson)](https://docs.spring.io/spring-boot/reference/features/json.html)
- [Spring blog — API Versioning in Spring (2025-09-16)](https://spring.io/blog/2025/09/16/api-versioning-in-spring/)
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457)
- [springdoc-openapi documentation](https://springdoc.org/)
