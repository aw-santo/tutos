---
title: Data Access with Spring Data JPA
tags:
  - spring
  - spring-boot
  - jpa
  - hibernate
  - spring-data
  - senior
aliases:
  - Spring Data JPA
  - JPA
  - Hibernate
  - Repositories
status: ready
created: 2026-07-09
---

# Data Access with Spring Data JPA

> [!abstract] Scope
> How Spring Data JPA turns an interface into a working repository, and — more importantly — the ORM machinery underneath it that every senior must be able to reason about: the **persistence context** (Hibernate's first-level cache), the **entity lifecycle**, **dirty checking** and flush timing, and the performance traps (**N+1**, `LazyInitializationException`, open-session-in-view, unbounded `findAll()`) that separate "it works on my laptop" from "it survives production." The beans and starter wiring come from [[01 - Spring Boot Fundamentals & Auto-Configuration]]; the transaction boundary that scopes the persistence context is in [[07 - Transactions & Data Consistency]].

Related: [[00 - Spring Boot Index]], [[07 - Transactions & Data Consistency]], [[09 - Caching]], [[11 - Testing Spring Boot Applications]]

![[jpa-n-plus-one.gif|720]]

*The N+1 problem: one query loads the parents, then each lazy collection fires its own query (N of them) — collapsed back to a single round-trip by a fetch join.*

---

## 1. The repository abstraction: an interface you never implement

You declare an interface; Spring Data generates the implementation at runtime as a proxy backed by `SimpleJpaRepository`, delegating to an `EntityManager`. There is no code generation on disk and no class you write — the proxy is built when the context starts, and repository method calls are intercepted and routed to a query.

The interface hierarchy — pick the **narrowest** one that exposes only what a caller should be able to do:

| Interface | Adds | Notes |
|---|---|---|
| `Repository<T, ID>` | nothing — pure **marker** | expose only the methods you hand-pick; safest for a domain-driven design |
| `CrudRepository<T, ID>` | `save`, `findById`, `findAll`, `count`, `delete`, `existsById` | returns `Iterable` from `findAll` |
| `ListCrudRepository<T, ID>` | same CRUD but returns `List` | the ergonomic default since Spring Data 3 |
| `PagingAndSortingRepository<T, ID>` | `findAll(Sort)`, `findAll(Pageable)` | **does not** extend CrudRepository — compose both if you need both |
| `ListPagingAndSortingRepository<T, ID>` | `List`-returning paging/sorting | list-flavoured variant |
| `JpaRepository<T, ID>` | JPA extras: `flush()`, `saveAndFlush`, `getReferenceById`, batch deletes | the fullest, JPA-specific surface |

```java
public interface OrderRepository extends JpaRepository<Order, Long> {
    // methods added below
}
```

> [!tip] Expose less, not more
> `extends JpaRepository` hands every caller `deleteAll()` and an unbounded `findAll()`. For a domain aggregate, prefer `extends Repository<Order, Long>` and declare only the methods the domain actually needs. It is a one-line change that prevents a service from ever calling `orderRepository.findAll()` on a 40-million-row table.

---

## 2. Query methods: derived, `@Query`, and native

**Derived queries** — Spring parses the method *name* into a query. Great for simple predicates, and self-documenting.

```java
List<Order> findByCustomerIdAndStatus(Long customerId, OrderStatus status);
Optional<Order> findFirstByCustomerIdOrderByCreatedAtDesc(Long customerId);
long countByStatus(OrderStatus status);
boolean existsByReference(String reference);
```

The grammar supports `And`/`Or`, `Between`, `LessThan`, `Like`, `In`, `IgnoreCase`, `OrderBy`, and `findFirst`/`findTop`. Its limit is complexity: three joins and a subquery become an unreadable 90-character method name. That is where `@Query` takes over.

```java
@Query("""
       select o from Order o
       where o.status = :status and o.total > :min
       """)                                            // JPQL — operates on entities, not tables
List<Order> findExpensive(@Param("status") OrderStatus status, @Param("min") BigDecimal min);

@Query(value = "select * from orders where created_at > now() - interval '7 days'",
       nativeQuery = true)                             // raw SQL — dialect-specific, bypasses JPQL
List<Order> findRecentNative();

@Modifying                                             // required for UPDATE/DELETE bulk statements
@Query("update Order o set o.status = :s where o.createdAt < :cutoff")
int bulkExpire(@Param("s") OrderStatus s, @Param("cutoff") Instant cutoff);
```

> [!warning] `@Modifying` bulk statements bypass the persistence context
> A bulk `update`/`delete` is issued straight to the database — it does **not** update managed entities already loaded in the first-level cache (§3), and it does not run entity callbacks or optimistic-lock version bumps. Entities you loaded before the bulk update are now silently stale.
> **Mitigation:** add `@Modifying(clearAutomatically = true, flushAutomatically = true)`, or run bulk statements in their own transaction before you load the affected rows.

---

## 3. The persistence context: first-level cache & entity lifecycle

This is the concept most candidates hand-wave and most bugs trace back to. The **persistence context** is the `EntityManager`'s working set for one transaction — a map of managed entities keyed by identity. It is also the **first-level cache**: within one transaction, a second `findById` for the same id returns the *same object instance* with **no** second query.

Every entity is in one of four states:

| State | Meaning | How it got there |
|---|---|---|
| **transient** | new object, no identity, unknown to JPA | `new Order()` |
| **managed** | tracked by the persistence context; changes are watched | `save()`, `findById()`, `persist()` |
| **detached** | has identity but context is closed/cleared; changes ignored | transaction ended, `EntityManager` closed |
| **removed** | scheduled for `DELETE` at flush | `delete()` |

**Dirty checking** is the payoff: for every *managed* entity, Hibernate keeps a snapshot taken at load time. At flush it compares current fields to the snapshot and issues `UPDATE` for whatever changed — **you never call `save()` to persist a modification** inside a transaction.

```java
@Transactional
public void rename(Long id, String name) {
    Order order = orderRepository.findById(id).orElseThrow();  // now MANAGED
    order.setName(name);                                       // just a setter
    // NO save() call — dirty checking issues the UPDATE at flush/commit
}
```

**Flush timing:** the SQL is not sent when you call the setter. Hibernate flushes (a) automatically before a query that might be affected, and (b) at transaction commit. `FlushMode.AUTO` is the default. This deferral is what lets Hibernate batch and order statements (§9).

> [!important] "save() does nothing" is often correct, not a bug
> Calling `repository.save(managedEntity)` inside the same transaction that loaded it is usually redundant — dirty checking already schedules the `UPDATE`. `save()` matters for **transient** (new) entities and for **detached** ones you are merging back. Understanding *why* the setter alone persists a change is a reliable senior signal.

---

## 4. The N+1 problem and every way to fix it

The single most common JPA performance bug (see the GIF). You load N parents in one query, then touch a lazy association on each — firing one extra query **per parent**. A list page of 50 orders each with line items becomes 1 + 50 = 51 round-trips, none of which show up in a single-row test.

```java
List<Order> orders = orderRepository.findAll();      // 1 query
for (Order o : orders) {
    o.getLineItems().size();                          // +1 query EACH → N+1
}
```

> [!warning] Gotcha — N+1 is invisible until load
> A unit test with two rows issues three queries and passes in milliseconds. The same code against 10k rows issues 10k+1 queries and melts the connection pool under real traffic. N+1 rarely fails a test; it fails a Black Friday. Assume every lazy collection accessed in a loop is an N+1 until proven otherwise — turn on `spring.jpa.properties.hibernate.generate_statistics=true` in test to count queries.

The fixes, in order of preference:

| Fix | How | Best for |
|---|---|---|
| **`JOIN FETCH`** | JPQL `join fetch` — one query with a join | a specific query that always needs the association |
| **`@EntityGraph`** | declarative fetch plan on a repository method | reusing an entity graph across derived queries |
| **`@BatchSize`** | fetch lazy collections in batches of N | many parents, don't want a giant cartesian join |
| **DTO projection** | select only the columns you need (§6) | read-only views; avoids loading entities at all |

```java
@Query("select distinct o from Order o join fetch o.lineItems where o.status = :s")
List<Order> findWithItems(@Param("s") OrderStatus s);   // 1 query, association pre-loaded

@EntityGraph(attributePaths = "lineItems")              // same effect, declaratively
List<Order> findByStatus(OrderStatus s);
```

> [!warning] `JOIN FETCH` + pagination = fetch-in-memory
> Combining `join fetch` on a collection with a `Pageable` makes Hibernate load **all** matching rows and paginate in memory — logged as `HHH000104: firstResult/maxResults specified with collection fetch; applying in memory`. On a large result set this is an OOM waiting to happen.
> **Mitigation:** use `@EntityGraph` on a paged query, or fetch ids first (paged) then fetch entities+collection by id list; or use `@BatchSize` instead of a fetch join for the paginated case.

---

## 5. FetchType defaults, lazy everything, and the OSIV footgun

Jakarta Persistence defaults are a trap: `@ManyToOne` and `@OneToOne` are **EAGER**; `@OneToMany` and `@ManyToMany` are **LAZY**. Eager `@ManyToOne` means every load of a child silently drags its parent — and chains: an eager graph can pull half your schema on one `findById`.

```java
@Entity
public class Order {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version                                            // optimistic lock (§8)
    private long version;

    @ManyToOne(fetch = FetchType.LAZY)                  // override the EAGER default
    private Customer customer;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<LineItem> lineItems = new ArrayList<>();
}
```

> [!tip] Make everything LAZY, then fetch explicitly
> Set `fetch = FetchType.LAZY` on **every** association, including `@ManyToOne`/`@OneToOne`. You lose nothing — you fetch exactly what a use case needs with `JOIN FETCH`/`@EntityGraph` (§4). Eager fetching is a global decision made at mapping time for a local need known only at query time; it is almost always wrong.

Lazy has its own hazard. A `LAZY` association accessed **after** the transaction (and thus the `EntityManager`) closes throws `LazyInitializationException` — the entity is now **detached** (§3) and cannot load anything.

> [!warning] Gotcha — `LazyInitializationException` in the view/controller
> Returning a JPA entity from a `@RestController` and letting Jackson serialize a lazy collection *after* the service transaction committed throws `LazyInitializationException` (or, worse, is masked — see below). The entity detached the moment the transaction ended.
> **Mitigation:** never serialize entities across a transaction boundary. Map to a **DTO inside the transaction**, or fetch the association eagerly *for that query* with a fetch join / entity graph.

**Open-Session-in-View** is Spring Boot's default "fix" — and a footgun. `spring.jpa.open-in-view=true` (the default) keeps the `EntityManager` open for the **entire HTTP request**, including view/JSON rendering, so lazy loads never throw. Boot even warns about it at startup:

```text
WARN JpaBaseConfiguration$JpaWebConfiguration :
  spring.jpa.open-in-view is enabled by default. Therefore, database queries may be
  performed during view rendering. Explicitly configure spring.jpa.open-in-view to disable this warning
```

> [!warning] Gotcha — OSIV masks N+1 in dev, then perf-bombs prod
> With OSIV on, the N+1 from §4 *works* — the session is still open during serialization, so each lazy access quietly fires a query while Jackson walks the object graph. It passes every test and demo. In production it holds a **database connection for the whole request** (including slow rendering and network write-back), throttling the HikariCP pool (§9) and firing N+1 storms you never saw locally.
> **Mitigation:** set `spring.jpa.open-in-view=false`. This forces the correct architecture — fetch what you need inside the service transaction and return DTOs. Any `LazyInitializationException` it surfaces is a real bug OSIV was hiding.

---

## 6. Pagination and projections

**Pagination** — never return an unbounded list. Pass a `Pageable`; Spring adds `LIMIT`/`OFFSET` and `ORDER BY`.

```java
Page<Order> findByStatus(OrderStatus status, Pageable pageable);
// caller: PageRequest.of(0, 20, Sort.by("createdAt").descending())
```

`Page` vs `Slice` is a senior distinction:

| Type | Knows total count? | Extra query | Use when |
|---|---|---|---|
| `Page<T>` | yes (`getTotalElements`, `getTotalPages`) | **runs a second `COUNT(*)` query** | UI needs "page 7 of 210" |
| `Slice<T>` | no — only "is there a next page?" | none (fetches `size + 1`) | infinite scroll / "load more" |

> [!warning] Gotcha — `Page`'s count query is not free
> Every `Page` result triggers a separate `SELECT COUNT(*)` against the (often complex, joined) query. On a large, heavily-filtered table that count can cost more than the page fetch itself and does not benefit from `LIMIT`. If the caller does not need an exact total, use `Slice`; if it needs a rough total, cache it or use an estimate.

> [!warning] Gotcha — `findAll()` with no `Pageable`
> `repository.findAll()` selects the **entire table** into the heap. It is fine on a 100-row lookup table and catastrophic on `orders`. Treat any argument-less `findAll()` as a code-review red flag; require a `Pageable` or an explicit bounded query.

**Projections** fetch only the columns you need — cheaper than hydrating full entities, and immune to lazy-loading issues since they are read-only.

```java
public interface OrderSummary {           // interface projection — Spring proxies it
    Long getId();
    BigDecimal getTotal();
}
List<OrderSummary> findByStatus(OrderStatus status);

// DTO / constructor expression — explicit, no proxy, works great with native SQL
@Query("select new com.acme.OrderSummaryDto(o.id, o.total) from Order o where o.status = :s")
List<OrderSummaryDto> summaries(@Param("s") OrderStatus s);
```

---

## 7. Schema management: `ddl-auto` and migrations

`spring.jpa.hibernate.ddl-auto` controls whether Hibernate touches your schema at startup: `none`, `validate`, `update`, `create`, `create-drop`.

| Value | Effect | Where |
|---|---|---|
| `validate` | checks entities match schema, changes nothing | **production** |
| `none` | Hibernate ignores schema entirely | production (with migrations owning schema) |
| `update` | tries to alter the schema to match entities | never in prod |
| `create` / `create-drop` | drops & recreates on startup | throwaway tests only |

> [!warning] Gotcha — `ddl-auto=update` in production
> `update` is a best-effort diff: it **adds** columns/tables but never drops or safely alters them, cannot rename, ignores data migration, and its output is non-deterministic across Hibernate versions. Teams reach for it for convenience and then discover it silently left the schema half-migrated, or held a lock that stalled a deploy. It is not a migration tool.
> **Mitigation:** own your schema with **Flyway** or **Liquibase** (both Boot-auto-configured — drop the starter in and put versioned scripts in `db/migration`). Set `ddl-auto=validate` so the app refuses to start if entities and the migrated schema disagree — a fast, loud failure instead of a silent drift.

---

## 8. Concurrency (locking) and auditing

**Optimistic locking** assumes conflicts are rare. Add a `@Version` column; Hibernate appends `where version = ?` to every `UPDATE` and increments it. A concurrent writer whose version no longer matches gets zero rows updated → `OptimisticLockException`. No database locks are held; ideal for web apps.

```java
@Version
private long version;      // Hibernate manages it; adds `and version=?` to UPDATEs
```

**Pessimistic locking** takes an actual database lock (`SELECT ... FOR UPDATE`) for the transaction. Use it only for genuine hot-row contention (e.g. inventory decrement) — it serializes access and risks deadlocks.

```java
@Lock(LockModeType.PESSIMISTIC_WRITE)
@Query("select i from Inventory i where i.sku = :sku")
Optional<Inventory> findForUpdate(@Param("sku") String sku);
```

**Auditing** — annotate timestamp/user fields and enable it once:

```java
@EntityListeners(AuditingEntityListener.class)
@Entity
public class Order {
    @CreatedDate  private Instant createdAt;
    @LastModifiedDate private Instant updatedAt;
}
// @EnableJpaAuditing on a @Configuration class turns it on
```

> [!tip] Prefer optimistic locking by default
> Reach for `@Version` first — it costs one column and no held locks, and it turns lost-update bugs into a catchable exception you can retry. Escalate to pessimistic locking only when you have measured contention on a specific row and can accept the serialization cost. Pair `@Version` with a retry (`@Retryable`) on `OptimisticLockException` for a clean concurrency story.

---

## 9. Connection pool sizing and JDBC batching

**HikariCP** is Boot's default pool. The counter-intuitive rule: **small pools are faster**. A pool larger than the database can service just queues context-switching and lock contention onto the DB.

```properties
spring.datasource.hikari.maximum-pool-size=10   # default; right-size, don't inflate
spring.datasource.hikari.minimum-idle=10
spring.datasource.hikari.connection-timeout=3000
```

> [!important] Size the pool to the database, not the app
> A useful starting formula (PostgreSQL wiki): `connections ≈ (core_count * 2) + effective_spindle_count`. A pool of 10 often out-throughputs a pool of 100. Remember every instance/replica has its own pool, and OSIV (§5) holds a connection for the whole request — a double reason to disable it. `maximum-pool-size` must stay well under the database's `max_connections`.

**Batch inserts** — by default Hibernate sends one `INSERT` per entity. For bulk writes, enable JDBC batching so many rows go in one round-trip:

```properties
spring.jpa.properties.hibernate.jdbc.batch_size=50
spring.jpa.properties.hibernate.order_inserts=true    # group same-table INSERTs so they batch
spring.jpa.properties.hibernate.order_updates=true
```

> [!warning] Gotcha — `GenerationType.IDENTITY` disables insert batching
> With `IDENTITY` id generation, Hibernate must execute each `INSERT` immediately to read back the generated key, so **batching is silently disabled** no matter what `batch_size` you set. For high-volume inserts use a `SEQUENCE` (with a pooled optimizer) instead of `IDENTITY`; the ids can then be assigned before flush and rows batched.

---

## 10. Alternatives & trade-offs

Spring Data JPA is the default, not the only choice. The full ORM (managed entities, dirty checking, lazy loading) is exactly what you want for complex write-heavy domains and exactly the overhead you don't want for reporting and high-throughput reads.

| Tool | Model | Strengths | When to pick it |
|---|---|---|---|
| **Spring Data JPA / Hibernate** | full ORM: managed entities, dirty checking, lazy graphs | rich domain mapping, caching, portability | complex write-heavy domains; the default JVM choice |
| **JdbcClient / Spring Data JDBC** | thin, no persistence context; you write SQL / simple aggregates | predictable SQL, no N+1/lazy surprises, fast | read-heavy paths, simple aggregates, when you want SQL control |
| **jOOQ** | typesafe SQL DSL generated from the schema | compile-checked SQL, superb for complex queries/reporting | analytics, heavy SQL, teams that think in SQL |
| **MyBatis** | SQL mapper (XML/annotation) | full SQL control with mapping convenience | legacy SQL, stored-proc-heavy shops |
| **R2DBC** | reactive, non-blocking driver | backpressure, high concurrency on few threads | fully reactive WebFlux stacks ([[05 - Web Layer & Embedded Servers - MVC vs WebFlux]]) |

> [!tip] The committed recommendation
> Default to **Spring Data JPA** for the transactional domain model, and reach for **`JdbcClient` or jOOQ** for read-heavy/reporting endpoints in the same app — mixing is a feature, not a defeat. JPA earns its complexity when you have a real object graph with invariants; for a flat "select these columns and page them," a thin SQL layer is simpler and faster and cannot N+1. Avoid **R2DBC** unless the whole stack is reactive — a reactive data layer under a blocking web layer buys nothing.

---

## 11. Caveats & risk mitigation (summary)

- **Disable open-in-view (§5).** `spring.jpa.open-in-view=false` — it masks N+1 in dev and starves the pool in prod. Return DTOs from inside the transaction.
- **Assume N+1 until proven otherwise (§4).** Count queries in tests (`generate_statistics`); fix with fetch joins / `@EntityGraph` / `@BatchSize`.
- **Make associations LAZY (§5)**, fetch explicitly per query. EAGER is a mapping-time answer to a query-time question.
- **Never `findAll()` unbounded (§6);** always paginate. Prefer `Slice` when you don't need an exact count.
- **`ddl-auto=validate` in prod (§7);** migrations own the schema (Flyway/Liquibase). `update`/`create` are for throwaway databases only.
- **Optimistic `@Version` first (§8);** pessimistic locks only for measured hot-row contention.
- **Right-size the pool small (§9);** `IDENTITY` ids silently kill insert batching — use a sequence for bulk writes.
- **Version facts are volatile.** Spring Boot 4.1.x / Spring Data (current) / Hibernate ORM 7 / Jakarta Persistence (`jakarta.persistence`, **not** `javax.persistence`) / JDK 17 baseline are current mid-2026 — **re-verify** exact GA versions before relying on them.

---

## 12. In practice

```java
// A read endpoint done right: LAZY entity, fetch join for the graph it needs,
// paginated, mapped to a DTO INSIDE the transaction. No OSIV, no N+1, no LazyInit.
@Service
class OrderQueryService {

    private final OrderRepository orders;

    @Transactional(readOnly = true)                       // read-only tx → Hibernate skips dirty-check flush
    public Page<OrderSummaryDto> recentByStatus(OrderStatus status, Pageable pageable) {
        return orders.findByStatus(status, pageable)      // @EntityGraph pre-loads lineItems (§4)
                     .map(o -> new OrderSummaryDto(o.getId(), o.getTotal()));  // map before tx closes
    }
}

public interface OrderRepository extends Repository<Order, Long> {   // narrow surface (§1)
    @EntityGraph(attributePaths = "lineItems")
    Page<Order> findByStatus(OrderStatus status, Pageable pageable);
}
```

```properties
# application.properties — the senior defaults
spring.jpa.open-in-view=false                                  # §5 — the most important line here
spring.jpa.hibernate.ddl-auto=validate                         # §7 — Flyway/Liquibase owns the schema
spring.jpa.properties.hibernate.jdbc.batch_size=50             # §9
spring.jpa.properties.hibernate.order_inserts=true             # §9
spring.datasource.hikari.maximum-pool-size=10                  # §9 — small, sized to the DB
# spring.jpa.properties.hibernate.generate_statistics=true     # §4 — turn on in test to count queries
```

**Interview talking points to be able to defend:**
- "A repository is an interface Spring proxies onto `SimpleJpaRepository` at startup — I expose the narrowest one and avoid unbounded `findAll()`."
- "The persistence context is Hibernate's first-level cache; inside a transaction I mutate a managed entity and dirty checking issues the UPDATE — I don't call `save()`."
- "N+1 is my first suspicion on any list endpoint; I fix it with a fetch join or `@EntityGraph`, and I disable open-in-view so it can't hide in dev then bomb prod."
- "Everything is LAZY and I fetch per query; entities never cross the transaction boundary — I return DTOs mapped inside the transaction."
- "`ddl-auto=validate` in prod with Flyway owning the schema; `update` is not a migration tool."
- "Optimistic `@Version` by default, pessimistic locks only for measured contention; and `IDENTITY` ids silently disable insert batching."

---

## 13. Sources

- [Spring Data JPA Reference — Core concepts & repository interfaces](https://docs.spring.io/spring-data/jpa/reference/repositories/core-concepts.html)
- [Spring Data JPA Reference — Defining query methods (derived & `@Query`)](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)
- [Spring Data JPA Reference — Entity graphs & fetch plans](https://docs.spring.io/spring-data/jpa/reference/jpa/entity-graph.html)
- [Spring Data — Paging, sorting & Page vs Slice](https://docs.spring.io/spring-data/jpa/reference/repositories/query-methods-details.html)
- [Spring Boot Reference — SQL databases (open-in-view, ddl-auto, Hibernate, Flyway/Liquibase)](https://docs.spring.io/spring-boot/reference/data/sql.html)
- [Hibernate ORM 7 User Guide (persistence context, fetching, batching, locking)](https://docs.hibernate.org/orm/7.0/userguide/html_single/Hibernate_User_Guide.html)
- [Jakarta Persistence Specification (jakarta.persistence, FetchType, `@Version`, LockModeType)](https://jakarta.ee/specifications/persistence/)
- [HikariCP — Pool sizing](https://github.com/brettwooldridge/HikariCP/wiki/About-Pool-Sizing)
