---
title: 07 - Transactions & Data Consistency
tags:
  - spring
  - spring-boot
  - transactions
  - jpa
  - senior
aliases:
  - Transactions
  - Transactional
  - Propagation
  - Isolation
status: ready
created: 2026-07-09
---

# Transactions & Data Consistency

> [!abstract] Scope
> How Spring turns `@Transactional` into an atomic unit of work — the **AOP proxy** that wraps your bean (see [[02 - IoC Container, Beans & Dependency Injection]]), the **propagation** and **isolation** knobs, the **rollback rules** that surprise everyone, and the proxy-shaped gotchas (self-invocation, checked exceptions, `UnexpectedRollbackException`) that make a transaction silently do nothing. We finish at the hard edge: why single-database transactions don't extend across services, and the **saga** and **transactional outbox** patterns that do the job instead ([[10 - Messaging, Events & Async]]). Persistence context mechanics live in [[06 - Data Access with Spring Data JPA]].

Related: [[00 - Spring Boot Index]], [[02 - IoC Container, Beans & Dependency Injection]], [[06 - Data Access with Spring Data JPA]], [[10 - Messaging, Events & Async]]

---

## 1. What a transaction is, and where its boundary belongs

A transaction is a unit of work that is **all-or-nothing**: either every write commits, or none does. Spring doesn't invent this — it delegates to a `TransactionManager` (for JPA, `JpaTransactionManager`; for plain JDBC, `DataSourceTransactionManager`) which drives the underlying database's `BEGIN`/`COMMIT`/`ROLLBACK` and manages the connection and the persistence context for the duration.

The senior decision is *where* the boundary sits, and there is one right answer for the common case:

| Layer | Should own the transaction? | Why |
|---|---|---|
| Controller | **No** | HTTP concerns only; a transaction open across request parsing/serialization is a leak |
| **Service** | **Yes** | A service method *is* the business use case — the natural atomic unit |
| Repository | **No** | Too fine-grained; one `save()` per transaction defeats atomicity across multiple writes |

> [!important] The boundary is the use case, not the query
> Put `@Transactional` on the **service method** that represents one business operation ("place order" = insert order + decrement stock + write ledger). If you push it down to the repository, each write commits independently and a mid-operation failure leaves the database half-updated with no way back. If you push it up to the controller, you hold a database connection while serializing JSON. The service layer is the Goldilocks boundary.

---

## 2. How `@Transactional` works: an AOP proxy around the bean

`@Transactional` is **metadata**, not behavior. It works because `@EnableTransactionManagement` (auto-enabled by Spring Boot) registers a `TransactionInterceptor` and Spring AOP wraps your bean in a **proxy** — exactly the proxy mechanism from [[02 - IoC Container, Beans & Dependency Injection]]. Callers get the proxy from the container, never the raw object.

```text
caller ──▶ [ proxy ]  ── begin tx (TransactionInterceptor) ─────────┐
                          │  yourService.placeOrder(...)  ← real bean │
                          └── commit on normal return / rollback on ex ┘
```

When a call enters *through the proxy*, the interceptor asks the `TransactionManager` for a transaction (per the propagation rule), invokes your method, and then commits on normal return or rolls back on a qualifying exception. Two consequences follow directly from "it's a proxy," and both are exam favourites (§7):

1. Only calls that **cross the proxy boundary** are advised. An internal `this.method()` call is not.
2. The proxy can only override methods it can see — so `private` and `final` methods can't be advised.

> [!tip] One-sentence framing
> "`@Transactional` is declarative AOP: the container hands callers a proxy that opens a transaction before my method and commits or rolls back after it. Everything surprising about transactions — self-invocation, private methods, rollback rules — falls out of *it's a proxy driven by an interceptor*, not magic on the method itself."

---

## 3. Declarative vs programmatic

**Declarative** (`@Transactional`) is the default and covers ~95% of cases. **Programmatic** — `TransactionTemplate` (imperative) or the raw `PlatformTransactionManager` — is for when the transaction boundary is *narrower than a method* or is *conditional*.

```java
@Service
class OrderService {

    private final TransactionTemplate tx;   // built from a PlatformTransactionManager

    OrderService(PlatformTransactionManager txManager) {
        this.tx = new TransactionTemplate(txManager);
    }

    void process(Order order) {
        doExpensiveNonTransactionalPrep(order);           // OUTSIDE the tx — no connection held

        tx.executeWithoutResult(status -> {               // tight, explicit boundary
            orderRepo.save(order);
            stockRepo.decrement(order.items());
            if (order.isSuspicious()) status.setRollbackOnly();  // conditional rollback
        });
    }
}
```

| Approach | API | When to pick which |
|---|---|---|
| **Declarative** | `@Transactional` on a service method | Default. The whole method is the unit of work; clean, no Spring API in your logic |
| **Programmatic — template** | `TransactionTemplate.execute(...)` | You need a **sub-method** boundary, or want to keep slow prep *outside* the transaction, or roll back conditionally |
| **Programmatic — raw** | `PlatformTransactionManager.getTransaction / commit / rollback` | Framework/library code, or multiple transactions with hand-managed lifecycles. Rare in app code |

> [!tip] Reach for the template only when the annotation can't express the boundary
> Prefer `@Transactional`; it keeps Spring's API out of your business logic. Drop to `TransactionTemplate` specifically to **shrink the boundary** — e.g. do a slow computation or an external call *before* opening the transaction (§8). Never use the raw `PlatformTransactionManager` in ordinary service code; that's a code-review flag.

---

## 4. Propagation: what happens when a transaction meets a transaction

Propagation decides what the interceptor does when a `@Transactional` method is called while a transaction may or may not already be active. `REQUIRED` is the default and correct choice almost always.

| Propagation | Behavior (exact) | When to use |
|---|---|---|
| **REQUIRED** *(default)* | Join the current transaction; create one if none exists | The default — one logical unit that may be called standalone or nested |
| **REQUIRES_NEW** | **Suspend** the current transaction and run in a brand-new independent one | Work that must commit **regardless** of the outer outcome — audit log, failed-attempt counter |
| **NESTED** | Run in a **savepoint** inside the current transaction; inner rollback rewinds to the savepoint, outer can still commit | Partial rollback of a sub-step (JDBC savepoints only; not all setups support it) |
| **SUPPORTS** | Join a transaction if one exists, else run non-transactionally | Read methods that are fine either way; avoids forcing a transaction |
| **MANDATORY** | Join the current one; **throw** if none exists | Method that must only ever be part of a larger unit — enforces "call me inside a tx" |
| **NOT_SUPPORTED** | Suspend any current transaction; run non-transactionally | Long non-transactional work you don't want holding a connection |
| **NEVER** | **Throw** if a transaction exists | Guard code that must never run transactionally |

> [!warning] `REQUIRES_NEW` and `NESTED` are not the same, and mixing them up corrupts data
> `REQUIRES_NEW` opens a **second physical transaction on a second connection** — the outer one is suspended. The inner commit is permanent even if the outer rolls back. `NESTED` uses a **savepoint on the same connection** — an inner rollback rewinds to the savepoint but the outer transaction (and connection) is shared. Choosing `REQUIRES_NEW` for an audit row is correct (you want it kept); choosing it for a sub-step you *expect* to roll back with its parent will leave orphaned committed rows.

---

## 5. Isolation levels and the anomalies they prevent

Isolation controls what one transaction sees of *other* concurrent transactions. Higher isolation prevents more anomalies but costs concurrency (more/longer locks). `DEFAULT` delegates to the database (PostgreSQL & Oracle default to `READ_COMMITTED`; MySQL/InnoDB to `REPEATABLE_READ`).

| Isolation | Dirty read | Non-repeatable read | Phantom read | When to pick which |
|---|---|---|---|---|
| **READ_UNCOMMITTED** | possible | possible | possible | Almost never — you can read another tx's uncommitted, later-rolled-back writes |
| **READ_COMMITTED** | prevented | possible | possible | The sane default for most OLTP; you only see committed data |
| **REPEATABLE_READ** | prevented | prevented | possible | A transaction that reads the same row(s) twice and needs a stable answer |
| **SERIALIZABLE** | prevented | prevented | prevented | Full correctness for critical invariants; expect contention/serialization failures |

- **Dirty read** — reading another transaction's *uncommitted* change (which may be rolled back).
- **Non-repeatable read** — re-reading a row you already read and getting a *different value* (someone updated + committed in between).
- **Phantom read** — re-running a range query and getting *new rows* that appeared (someone inserted + committed).

> [!warning] `isolation` and `timeout` apply only to `REQUIRED` / `REQUIRES_NEW`
> Setting `isolation` or `timeout` on a method that *joins* an existing transaction (e.g. a `REQUIRED` call nested inside another) is **silently ignored** — the outer transaction's settings win, because you can't change the isolation of a transaction that's already running. Set isolation at the point the transaction is actually *created*, or Spring will (in strict validation modes) reject the mismatch. Prefer the database default unless a specific anomaly forces your hand.

---

## 6. Rollback rules: the gotcha that eats data

This is the single most-tested transaction fact. By Spring's default rule:

> Any **`RuntimeException`** or **`Error`** triggers rollback. Any **checked `Exception`** does **not** — the transaction **commits**.

```java
@Transactional
public void transfer(Long from, Long to, BigDecimal amt) throws InsufficientFundsException {
    debit(from, amt);
    if (balanceOf(from).signum() < 0)
        throw new InsufficientFundsException();   // CHECKED → Spring COMMITS the debit! 💥
    credit(to, amt);
}
```

> [!warning] A checked exception silently commits a half-done transaction
> The code above throws *after* the debit but *before* the credit. Because `InsufficientFundsException` is a **checked** exception, Spring's default rule does **not** roll back — the debit is committed and the money vanishes. Nothing warns you; the method "failed" from the caller's view but the database kept the partial write. This surprises nearly everyone, because "it threw, so surely it rolled back" is the natural assumption.

> [!tip] Make rollback semantics explicit
> Either declare `@Transactional(rollbackFor = Exception.class)` on methods that throw checked exceptions, or — cleaner for consistency across a service — use `@Transactional(rollbackFor = Exception.class)` as a convention, or set `rollbackOn`/`ALL_EXCEPTIONS` semantics so *any* thrown exception rolls back. The Spring team itself advises switching to all-exception rollback unless you deliberately rely on EJB-style "commit on business exception" behavior. Reserve `noRollbackFor` for exceptions you genuinely want to swallow-and-commit.

Two more attributes worth setting deliberately:

- **`readOnly = true`** — a hint the transaction won't write. Lets Hibernate skip dirty-checking/flush and lets the driver/DB optimize (and route to read replicas in some setups). Use it on every query-only service method; it's free performance and documents intent.
- **`timeout = N`** (seconds) — abort a transaction that runs too long, releasing its locks and connection. A backstop against a runaway query holding resources.

```java
@Transactional(readOnly = true, timeout = 5)
public OrderView getOrder(Long id) { ... }   // query-only: no flush, bounded duration
```

---

## 7. The proxy gotchas: self-invocation, visibility, and rollback-only

Everything here is a direct consequence of §2 — *it's a proxy*.

> [!warning] Self-invocation makes `@Transactional` a silent no-op
> Because only calls **through the proxy** are advised, one method of a bean calling another method of the **same bean** bypasses the interceptor entirely — the inner `@Transactional` does nothing.
> ```java
> @Service
> class ReportService {
>     public void run() {
>         generate();                 // internal call → NO transaction is opened
>     }
>     @Transactional
>     public void generate() { ... }  // annotation ignored on the self-call
>     }
> ```
> **Mitigation:** move `generate()` to a **separate bean** and inject it (so the call crosses a proxy), or self-inject the proxy, or use `TransactionTemplate`. Also note: **`@Transactional` on `private` or `final` methods is ignored** — the proxy can't override them. (Since Spring 6.0, class-based proxies *can* advise `protected`/package-private methods; interface-based proxies still require `public`.)

> [!warning] Catching an exception inside a rollback-only transaction → `UnexpectedRollbackException`
> If an inner call marks the transaction **rollback-only** (e.g. an inner `REQUIRED` method threw, so Spring flags the shared transaction) and you *catch* that exception in the outer method and try to continue/commit, Spring refuses at commit time and throws **`UnexpectedRollbackException`** ("Transaction silently rolled back because it has been marked as rollback-only"). The transaction is already doomed; catching the exception doesn't un-doom it.
> **Mitigation:** don't swallow exceptions from a joined (`REQUIRED`) inner transactional call and expect to commit. If a sub-step is genuinely optional and may fail independently, give it **`REQUIRES_NEW`** so its rollback is isolated from the outer transaction, then catching its exception is safe.

---

## 8. Keep transactions short: hold the connection for microseconds, not seconds

An open transaction pins a database **connection** from the pool for its entire duration. Long transactions starve the pool and, under load, cause `Connection is not available` timeouts that look like a database outage but are self-inflicted.

> [!warning] Never call a slow external API inside a transaction
> ```java
> @Transactional
> public void checkout(Order o) {
>     orderRepo.save(o);
>     paymentGateway.charge(o);   // network call: 200ms–30s, holding a DB connection the whole time 💥
>     o.markPaid();
> }
> ```
> The HTTP call to the payment gateway can hang for seconds; meanwhile a pooled connection is held open and idle. A few concurrent checkouts exhaust the pool and the whole service stalls. The same applies to sending an email, calling another microservice, or any I/O that isn't the database.

> [!tip] Do slow work outside the boundary; commit local state, then react
> Split it: persist and commit local state in a short transaction, then do the external call *after* commit — ideally via a `@TransactionalEventListener` on `AFTER_COMMIT` (§9) or an async message ([[10 - Messaging, Events & Async]]). Structure the code so the transaction contains only database work. If prep is expensive, compute it *before* opening the transaction (use `TransactionTemplate`, §3). Rule of thumb: **no network calls, no user waits, no `Thread.sleep`, inside `@Transactional`.**

---

## 9. Transaction-bound events: `@TransactionalEventListener`

Ordinary `@EventListener`s fire synchronously *inside* the publisher's transaction. `@TransactionalEventListener` binds the handler to a **transaction phase** — by default `AFTER_COMMIT` — so side-effects fire only if (and after) the transaction actually commits.

```java
@Transactional
public void placeOrder(Order o) {
    orderRepo.save(o);
    events.publishEvent(new OrderPlaced(o.getId()));   // published now, HANDLED after commit
}

@TransactionalEventListener          // default phase = AFTER_COMMIT
void onCommitted(OrderPlaced e) {
    emailService.sendConfirmation(e.orderId());        // only if the order truly committed
}
```

This is the clean answer to §8's "don't do slow work in the transaction" and the natural building block for the outbox pattern below.

> [!warning] `AFTER_COMMIT` runs after the transaction closed — new DB writes won't commit
> By default, if no transaction is active when the event is published, the listener **doesn't run at all** (unless `fallbackExecution = true`). And in the `AFTER_COMMIT` phase the original transaction is already committed, so any *new* database write you attempt there participates in a transaction that will never be committed — it silently disappears. Use the phase for external side-effects (email, message publish), not for more database writes; for those, publish an outbox row *inside* the original transaction instead.

---

## 10. Distributed consistency: why not 2PC, and what to do instead

A single `@Transactional` guarantees consistency **within one database**. The moment a business operation spans two services (or a database *and* a message broker), you have no shared transaction — and reaching for a distributed transaction is usually the wrong move.

| Approach | Mechanism | Trade-off / when to pick which |
|---|---|---|
| **2PC / XA** | A coordinator runs prepare→commit across all resources (`JtaTransactionManager`) | **Avoid.** Synchronous locking across services, the coordinator is a SPOF, poor scalability, brittle under partitions. Only for legacy XA resources you truly can't avoid |
| **Saga** | A sequence of **local** transactions, each publishing an event that triggers the next; failures trigger **compensating** actions | Cross-service business flows (order → payment → shipping). Eventually consistent; you must design compensations. Choreography (events) or orchestration (a coordinator) |
| **Transactional outbox** | Write the domain change **and** an "outbox" row in the **same local transaction**; a relay polls the outbox and publishes to the broker | The reliable bridge from DB to broker — guarantees **at-least-once** publish with **no 2PC**. Almost always the right way to emit events ([[10 - Messaging, Events & Async]]) |

> [!important] The dual-write problem is why the outbox exists
> "Save to the DB, then publish to Kafka" is two writes to two systems with **no shared transaction**. If the process dies between them, you've either lost the event (saved, not published) or published a lie (published, DB rolled back). The **outbox** collapses this to a *single* local transaction: the domain row and the outbox row commit atomically, and a separate relay (polling or CDC/Debezium) publishes the outbox row afterward. Combined with **idempotent consumers**, this gives reliable eventual consistency without any distributed transaction.

> [!tip] Default recommendation for cross-service consistency
> Reach for **outbox + saga + idempotent consumers**, not XA. Model the business flow as local transactions linked by events (saga), emit those events reliably via the outbox, and make every consumer idempotent (dedupe on a message/business key). Accept **eventual** consistency as the price — it's the honest trade for availability and scale, and it's the answer interviewers want over "I'd use a distributed transaction."

---

## 11. In practice

```java
@Service
class CheckoutService {

    // Transaction boundary = the business use case, at the SERVICE layer (§1)
    @Transactional(rollbackFor = Exception.class, timeout = 10)   // roll back on ANY exception (§6)
    public OrderId checkout(Cart cart) throws PaymentDeclinedException {
        Order order = orderRepo.save(Order.from(cart));           // DB work only, no external calls (§8)
        stockRepo.decrement(cart.items());                        // same tx: atomic with the order
        events.publishEvent(new OrderPlaced(order.getId()));      // outbox/notify AFTER commit (§9)
        return order.getId();
    }

    @Transactional(readOnly = true)                               // query path: no flush (§6)
    public OrderView view(OrderId id) {
        return orderRepo.findView(id).orElseThrow();
    }
}

@TransactionalEventListener   // AFTER_COMMIT — external side-effect, outside the tx (§8, §9)
void onOrderPlaced(OrderPlaced e) {
    notifier.sendConfirmation(e.orderId());
}
```

**Interview talking points to be able to defend:**
- "`@Transactional` is an AOP proxy driven by a `TransactionInterceptor` — every surprise (self-invocation, private methods, rollback rules) falls out of *it's a proxy*."
- "Boundary belongs at the **service** layer; a service method is one business use case, which is the natural atomic unit."
- "Default rollback is `RuntimeException`/`Error` **only** — checked exceptions commit. I set `rollbackFor` so a thrown exception never leaves a half-written transaction."
- "`REQUIRES_NEW` is a new physical transaction on a new connection; `NESTED` is a savepoint on the same one — I pick by whether the inner work should survive an outer rollback."
- "I keep transactions short — no external API calls inside `@Transactional` — and push side-effects to `AFTER_COMMIT` or an outbox."
- "Across services I use **outbox + saga + idempotent consumers**, never 2PC; the dual-write problem is exactly what the outbox solves."

---

## 12. Sources

- [Spring Framework Reference — Transaction Management (overview)](https://docs.spring.io/spring-framework/reference/data-access/transaction.html)
- [Spring Framework Reference — Using `@Transactional` (attributes, rollback rules, self-invocation, visibility)](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework Reference — Understanding the declarative transaction implementation (AOP proxy)](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)
- [Spring Framework Reference — Programmatic transaction management (`TransactionTemplate`, `PlatformTransactionManager`)](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)
- [Spring Framework Reference — Transaction-bound events (`@TransactionalEventListener`)](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Framework API — `Propagation` enum](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/annotation/Propagation.html)
- [Spring Framework API — `Isolation` enum](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/annotation/Isolation.html)
- [Spring Framework 7.0 GA (foundation for Boot 4)](https://spring.io/blog/2025/11/13/spring-framework-7-0-general-availability/)
- [Spring Boot 4.0.0 available now (GA announcement, 2025-11-20)](https://spring.io/blog/2025/11/20/spring-boot-4-0-0-available-now/)
