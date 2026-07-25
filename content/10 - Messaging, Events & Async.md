---
title: 10 - Messaging, Events & Async
tags:
  - spring
  - spring-boot
  - messaging
  - kafka
  - async
  - events
  - senior
aliases:
  - Messaging
  - Application Events
  - Async
  - Kafka
  - RabbitMQ
status: ready
created: 2026-07-09
---

# Messaging, Events & Async

> [!abstract] Scope
> How work leaves the request thread and how components talk without calling each other directly — **in-process application events** ([[02 - IoC Container, Beans & Dependency Injection]] beans publishing to beans), **`@Async`/`@Scheduled`** background execution inside one JVM, and **external brokers** (Kafka, RabbitMQ) between services. The senior material is the failure modes: proxy self-invocation, exceptions swallowed by `void` async methods, schedulers firing on every clustered instance, and above all the **dual-write** problem that the [[07 - Transactions & Data Consistency|transactional outbox]] pattern exists to solve.

Related: [[00 - Spring Boot Index]], [[07 - Transactions & Data Consistency]], [[13 - Resilience & Production Readiness]]

---

## 1. Three mechanisms, one question: what's the coupling boundary?

"Messaging" spans three very different tools, and picking the wrong one is a design smell interviewers listen for. The deciding question is **where the boundary is** and **what happens if the other side is down**.

| Mechanism | Boundary | Delivery | Survives a crash? |
|---|---|---|---|
| **In-process events** (`ApplicationEventPublisher`) | between beans in **one JVM** | in-memory method calls | **No** — events live only in heap |
| **`@Async` / `@Scheduled`** | off the caller's thread, **same JVM** | in-memory task queue | **No** — queued tasks lost on restart |
| **External broker** (Kafka / RabbitMQ) | between **separate processes/services** | persisted on the broker | **Yes** — the broker is durable storage |

> [!tip] The framing interviewers want
> In-process events and `@Async` are **decoupling within a deployable**, not durability — if the JVM dies mid-work, that work is gone. The moment you need the work to *survive a crash* or cross a *service boundary*, you need a **broker**. Choosing an in-memory `@EventListener` for something that must not be lost (a payment side-effect) is the classic mistake; choosing Kafka for two beans in the same app is the opposite over-engineering.

---

## 2. In-process application events

The `ApplicationContext` is itself an event bus. A bean publishes an event; any bean with a matching listener handles it. This decouples a producer from its consumers without either holding a reference to the other.

```java
public record OrderPlaced(String orderId, BigDecimal total) {}   // a plain POJO event (Spring 4.2+)

@Service
class OrderService {
    private final ApplicationEventPublisher publisher;           // injected, not ApplicationEventPublisherAware

    OrderService(ApplicationEventPublisher publisher) { this.publisher = publisher; }

    public void place(Order order) {
        // ... persist the order ...
        publisher.publishEvent(new OrderPlaced(order.id(), order.total()));
    }
}

@Component
class InventoryListener {
    @EventListener                                               // type-safe; method name is free
    void on(OrderPlaced e) { /* reserve stock */ }
}
```

> [!warning] `@EventListener` is SYNCHRONOUS by default
> `publishEvent(...)` does **not** return until every listener has run, **on the caller's thread, inside the caller's transaction**. A slow or throwing listener slows down — or rolls back — the code that published the event. People assume "event = fire-and-forget" and are surprised when a listener's exception fails the original request.
> **Mitigation:** make a listener asynchronous by adding `@Async` (see §4) *and* `@EnableAsync`. Note that once it's `@Async` it runs on another thread, **outside the publisher's transaction**, and its exceptions no longer propagate to the caller — a deliberate trade-off, not a free upgrade.

---

## 3. `@TransactionalEventListener`: firing after the commit

A plain `@EventListener` runs *inside* the publisher's transaction, so a listener that calls an external system will have acted even if the transaction later rolls back. `@TransactionalEventListener` binds the listener to a **transaction phase** instead.

| `TransactionPhase` | Listener runs… | Use for |
|---|---|---|
| `BEFORE_COMMIT` | just before commit | last-chance validation / same-tx writes |
| `AFTER_COMMIT` *(default)* | after a successful commit | side-effects that must only happen if the data really persisted |
| `AFTER_ROLLBACK` | after a rollback | compensation, alerting |
| `AFTER_COMPLETION` | after commit **or** rollback | cleanup regardless of outcome |

```java
@TransactionalEventListener                 // default phase = AFTER_COMMIT
void on(OrderPlaced e) {
    emailClient.sendConfirmation(e.orderId());   // only sent if the order truly committed
}
```

> [!important] `AFTER_COMMIT` is the honest default for external side-effects
> "Send the email / call the shipping API only if the order actually committed" is exactly `AFTER_COMMIT`. If there is **no active transaction**, the listener is **silently skipped** unless you set `fallbackExecution = true` — a subtle gotcha when the same method is invoked both inside and outside a transaction. Crucially, `AFTER_COMMIT` does **not** make the side-effect durable: the commit succeeds, then the JVM can die before the email sends. That gap is the dual-write problem (§9), and it is why `AFTER_COMMIT` on its own is not a delivery guarantee.

---

## 4. `@Async`: work off the caller's thread

`@Async` runs a method on a task executor instead of the calling thread. It is **proxy-based** — Spring wraps the bean in an AOP proxy whose overridden method dispatches to the executor.

```java
@Configuration
@EnableAsync                                                   // required, or @Async is ignored
class AsyncConfig {
    @Bean
    ThreadPoolTaskExecutor appExecutor() {                     // name it; qualify with @Async("appExecutor")
        var ex = new ThreadPoolTaskExecutor();
        ex.setCorePoolSize(8);
        ex.setMaxPoolSize(16);
        ex.setQueueCapacity(500);                              // bounded — see backpressure (§10)
        ex.setThreadNamePrefix("app-async-");
        ex.initialize();
        return ex;
    }
}

@Service
class ReportService {
    @Async("appExecutor")
    CompletableFuture<Report> build(String id) {               // return a Future to get the result / errors back
        return CompletableFuture.completedFuture(generate(id));
    }
}
```

> [!warning] Self-invocation is a no-op — the proxy is bypassed
> Because `@Async` works through a proxy, calling an `@Async` method **from another method of the same bean** (`this.build(id)`) runs it **synchronously on the current thread** — the call never leaves the object, so the proxy that would have dispatched to the executor is never involved. This is the same proxy limitation that bites `@Transactional` and `@Cacheable`; see [[02 - IoC Container, Beans & Dependency Injection]]. The method appears to "not be async" for no visible reason.
> **Mitigation:** call the async method from a **different bean**, inject a reference to `self` (via `ApplicationContext` or a self-injected proxy), or — for pervasive cases — switch to AspectJ load-time weaving (`@EnableAsync(mode = AdviceMode.ASPECTJ)`).

> [!warning] `@Async void` swallows every exception
> A `void` (or `Future`-less) `@Async` method that throws sends its exception **nowhere** — there is no caller holding a `Future` to observe it, so it vanishes. Silent, permanent data loss with no stack trace in the request path.
> **Mitigation:** return `CompletableFuture<T>` so the caller can observe failures via `.exceptionally(...)`/`.get()`; for genuinely `void` methods, register an **`AsyncUncaughtExceptionHandler`** (below) so at minimum it is logged/alerted.

```java
@Configuration
@EnableAsync
class AsyncErrorConfig implements AsyncConfigurer {
    @Override public AsyncUncaughtExceptionHandler getAsyncUncaughtExceptionHandler() {
        return (ex, method, params) -> log.error("async {} failed", method.getName(), ex);
    }
}
```

> [!tip] Virtual-thread executors for I/O-bound async (JDK 21+)
> If your async work is I/O-bound (HTTP calls, DB), a pool sized for threads is the wrong model. On **JDK 21+** back it with virtual threads — `SimpleAsyncTaskExecutor` supports them (`setVirtualThreads(true)`), and Spring Boot's `spring.threads.virtual.enabled=true` switches the app's executors over wholesale. You then stop tuning pool sizes and let the platform schedule. **[HIGH-CHURN: JDK 17 is the Boot 4 baseline; virtual threads require Java 21+ — verify your runtime.]**

---

## 5. `@Scheduled`: periodic work, and the cluster trap

`@Scheduled` (with `@EnableScheduling`) runs a method on a timer. Know the three triggers cold:

| Attribute | Interval measured… | Behaviour if a run overruns |
|---|---|---|
| `fixedRate` | between successive **start** times | runs pile up / overlap (single scheduler thread serializes) |
| `fixedDelay` | between end of one run and **start** of next | naturally spaces out; no overlap |
| `cron` | wall-clock expression (`0 0 3 * * *`), optional `zone` | calendar-based; supports `@daily` macros |

```java
@Scheduled(fixedDelay = 30_000, initialDelay = 5_000)          // 30s AFTER each run finishes
void reconcile() { /* ... */ }

@Scheduled(cron = "0 0 3 * * *", zone = "Europe/Berlin")       // 03:00 Berlin time daily
void nightlyRollup() { /* ... */ }
```

> [!warning] `@Scheduled` fires on EVERY instance in a cluster
> `@Scheduled` is per-JVM. Deploy the app across **three pods** and the nightly job runs **three times** — three emails, triple-charged invoices, three racing writes. Works perfectly in dev (one instance), corrupts data in production (many). This is one of the most common "it worked on my machine" incidents.
> **Mitigation:** serialize the job cluster-wide. The pragmatic default is **ShedLock** (a distributed lock in your DB/Redis via `@SchedulerLock`, so only one instance runs each fire). Alternatives: a leader-election mechanism (Spring Cloud / Kubernetes lease), or moving the job to a dedicated single-instance worker or an external scheduler (Quartz clustered, K8s `CronJob`).

```java
@Scheduled(cron = "0 0 3 * * *")
@SchedulerLock(name = "nightlyRollup", lockAtMostFor = "10m")   // ShedLock: only one instance wins
void nightlyRollup() { /* ... */ }
```

---

## 6. Kafka with `spring-kafka`

Kafka is a **durable, partitioned, append-only log**. Producers append records to a topic's partitions; consumers read at their own pace by tracking an **offset**. Records are retained (by time/size) after being read, so many independent consumers can replay the same log.

```java
@Component
class OrderConsumer {
    @KafkaListener(topics = "orders", groupId = "billing")     // consumer group "billing"
    void handle(ConsumerRecord<String, OrderPlaced> rec, Acknowledgment ack) {
        process(rec.value());
        ack.acknowledge();                                     // manual offset commit AFTER success
    }
}
```

```java
@Service
class OrderProducer {
    private final KafkaTemplate<String, OrderPlaced> template;
    OrderProducer(KafkaTemplate<String, OrderPlaced> t) { this.template = t; }

    void publish(OrderPlaced e) {
        template.send("orders", e.orderId(), e);               // key = orderId → same partition → ordered
    }
}
```

Two senior points:

- **Consumer groups = scaling + ordering unit.** Kafka assigns each partition to exactly one consumer *within a group*, so concurrency is capped at the partition count; add a *second* group and it gets its own full copy of the stream. The **message key** decides the partition, and **ordering is only guaranteed per partition** — so keying by `orderId` keeps one order's events in order while still parallelising across orders.
- **Offset commit is your delivery lever.** The default `AckMode` is `BATCH` (commit after each poll batch). For at-least-once with precise control, use `MANUAL`/`MANUAL_IMMEDIATE` and `ack.acknowledge()` *after* successful processing. Commit *before* processing and a crash loses the record (at-most-once); commit *after* and a crash redelivers it (at-least-once).

---

## 7. RabbitMQ with `spring-amqp`

RabbitMQ is a **broker with queues**: a producer publishes to an **exchange**, which routes (by binding/routing-key) into **queues**, and consumers pull from queues. Unlike Kafka, a message is typically **removed once acknowledged** — it's a work queue, not a replayable log.

```java
@Component
class PaymentConsumer {
    @RabbitListener(queues = "payments")
    void handle(PaymentMessage msg) {                          // container acks on normal return
        process(msg);                                          // throw → nack → retry/DLQ per config
    }
}
```

`@RabbitListener` uses `AcknowledgeMode.AUTO` by default: return normally and the message is acked; throw and it is nacked (redelivered or dead-lettered depending on configuration). Rabbit shines for **per-message routing, priorities, and competing-consumer work queues**; Kafka shines for **high-throughput, replayable event streams** consumed by many independent readers.

---

## 8. Delivery semantics: at-least-once is the real world

Every interview probes this. There are three theoretical guarantees; only two are practical.

| Guarantee | Mechanics | Reality |
|---|---|---|
| **At-most-once** | commit/ack *before* processing | fast, but loses messages on crash — rarely acceptable |
| **At-least-once** | commit/ack *after* processing | **the practical default**; a crash after work-but-before-ack redelivers → **duplicates** |
| **Exactly-once** | broker transactions + dedup | narrow, costly, and **not** end-to-end once your side-effects touch external systems |

> [!warning] A non-idempotent consumer turns redelivery into corruption
> Under at-least-once, a message **will** be delivered more than once eventually (consumer crashes after processing, before commit; a rebalance re-reads; a retry fires). If `handle()` does `balance += amount` or `INSERT` without a uniqueness guard, the redelivery **double-charges / double-inserts**. The bug is invisible until the day a consumer restarts mid-batch.
> **Mitigation — idempotent consumers.** Carry a stable **idempotency key** (message id / business key) and make the effect idempotent: `INSERT ... ON CONFLICT DO NOTHING`, an `UPSERT`, or a processed-ids table checked in the same transaction as the write. Then redelivery is a no-op, and you can stop chasing "exactly-once" you can't actually get.

> [!important] Why exactly-once is largely a myth end-to-end
> Kafka's "exactly-once semantics" holds **within** the Kafka boundary (idempotent producer + transactional read-process-write between Kafka topics). The instant your consumer sends an email, charges a card, or writes to a *different* database, that external effect isn't inside the broker's transaction — so the honest architecture is **at-least-once delivery + idempotent processing**, which is *effectively* exactly-once from the business's point of view without pretending the broker gives it to you.

---

## 9. The dual-write problem and the transactional outbox

The single most important distributed-systems pattern in this module.

> [!warning] Dual-write: DB and broker can't be committed atomically
> The natural code is "save the order, then publish the event":
> ```java
> orderRepo.save(order);              // (1) commits to Postgres
> kafka.send("orders", event);        // (2) sends to Kafka — SEPARATE system
> ```
> There is **no shared transaction** across two systems. If (2) fails (broker down, pod killed between the two lines), the DB has the order but no event was ever sent — inventory and billing never hear about it. Reverse the order and a broker success followed by a DB rollback publishes a **phantom** event for an order that doesn't exist. You cannot make two independent commits atomic, and `@Transactional` around both does **not** help — Kafka isn't in that transaction.

> [!important] Mitigation — the Transactional Outbox
> Write the event as a **row in an `outbox` table in the same local DB transaction** as the business change. Now the state change and the "intent to publish" commit **atomically** — one transaction, one system. A separate **relay** (a poller, or Change-Data-Capture like Debezium tailing the WAL) reads unsent outbox rows and publishes them to the broker, marking them sent. Publishing is retried until it succeeds → **at-least-once** delivery with **no lost or phantom events**. Consumers must still be idempotent (§8), because the relay can publish a row twice if it crashes after sending but before marking it sent. This is the concrete payoff of the local-transaction guarantees in [[07 - Transactions & Data Consistency]].

```java
@Transactional                                   // ONE local transaction — both rows or neither
public void placeOrder(Order order) {
    orderRepo.save(order);
    outboxRepo.save(new OutboxEvent("orders", order.id(), toJson(new OrderPlaced(...))));
}
// A relay (poller / Debezium CDC) later publishes unsent outbox rows to Kafka and marks them sent.
```

---

## 10. Retries, dead-letters, ordering, backpressure

The operational concerns that separate a demo from production.

- **Retries.** Transient failures (a downstream blip) should be retried with **backoff**, not a tight loop. Spring Kafka's `DefaultErrorHandler` and Rabbit's retry interceptor give bounded retries with exponential backoff; wrap external calls with the resilience patterns in [[13 - Resilience & Production Readiness]]. Distinguish **retryable** (timeout) from **non-retryable** (malformed payload) — retrying a poison message forever blocks the partition/queue.
- **Dead-letter queues (DLQ).** After N failed attempts, route the message to a **dead-letter topic/queue** rather than blocking or dropping it. Spring Kafka's `DeadLetterPublishingRecoverer` and Rabbit's DLX give you this. A DLQ you never monitor is just a slow data-loss bug — alert on its depth.
- **Ordering.** Only guaranteed **per Kafka partition** / per Rabbit queue with a single consumer. Concurrency and ordering are in tension: parallel consumers reorder. Key related events onto the same partition when order matters, and accept that unrelated events interleave.
- **Backpressure.** A fast producer and slow consumer will overflow *something*. **Bound your queues** — a `ThreadPoolTaskExecutor` with `queueCapacity` and a sensible `RejectedExecutionHandler` (e.g. `CallerRunsPolicy` to slow the producer) beats an unbounded queue that becomes an `OutOfMemoryError`. Kafka provides natural backpressure (the consumer pulls at its own pace); an unbounded in-JVM `@Async` queue does not.

---

## 11. In-process events vs Kafka vs RabbitMQ

| Dimension | **In-process events** | **Kafka** (log) | **RabbitMQ** (queue) |
|---|---|---|---|
| Boundary | one JVM | across services | across services |
| Durable / survives crash | No (in-heap) | Yes (persisted log) | Yes (persisted queue) |
| Model | observer / pub-sub | append-only **log**, pull, replayable | **queue**, push, consume-and-remove |
| Multiple independent readers | yes (many listeners) | yes (many consumer groups, each full copy) | needs fan-out exchange per consumer |
| Replay / re-read history | no | **yes** (offsets, retention) | no (once acked, gone) |
| Ordering | caller order | per-partition | per-queue |
| Throughput | in-memory (highest) | very high | high |
| Per-message routing / priority | n/a | limited (keys) | **rich** (exchanges, routing keys, priorities) |
| **When to pick which** | decouple beans **inside one deployable**; no durability needed | **event streaming / high-volume**, many consumers, replay, audit log, event sourcing | **task/work queues**, complex routing, RPC-style, per-message priorities, competing consumers |

> [!tip] The committed recommendation
> Reach for **in-process events** to decouple beans in a single service and nothing more — never for anything that must survive a restart. Choose **Kafka** when the workload is a **stream** consumed by multiple independent readers, needs **replay/audit**, or is genuinely high-throughput. Choose **RabbitMQ** for **work-queue** semantics — competing consumers pulling discrete tasks, rich routing, or priorities. And regardless of broker, design for **at-least-once + idempotent consumers**, and cross the DB→broker boundary through the **outbox** (§9), not a naive dual write.

---

## 12. Caveats & risk mitigation (summary)

- **In-memory ≠ durable (§1).** Events and `@Async` tasks vanish on crash; if the work must not be lost, it belongs on a broker.
- **Proxies don't self-invoke (§4).** `@Async` (and `@Transactional`, `@Cacheable`) do nothing when called from within the same bean — cross a bean boundary.
- **Never `@Async void` without a handler (§4).** Return a `Future` or register `AsyncUncaughtExceptionHandler`, or exceptions disappear.
- **`@Scheduled` is per-instance (§5).** In a cluster, guard cluster-wide jobs with ShedLock or leader election.
- **Assume redelivery (§8).** At-least-once is the default; make every consumer idempotent with an idempotency key.
- **Don't dual-write (§9).** Use the transactional outbox to make the state change and the publish atomic; a relay handles delivery.
- **DLQ + backoff + bounded queues (§10).** Retry transient failures, dead-letter poison messages, and never run an unbounded in-JVM queue.
- **Version facts are volatile.** Spring Boot 4.1.x / Framework 7.0 / spring-kafka & spring-amqp 4.1.x / Jakarta EE 11 / JDK 17 baseline (virtual threads Java 21+) are current as of mid-2026 — **re-verify** exact GA versions and any API details before relying on them.

---

## 13. In practice

```java
// Outbox-backed order flow with an idempotent, manually-acked Kafka consumer.
@Service
class OrderService {
    private final OrderRepository orders;
    private final OutboxRepository outbox;

    OrderService(OrderRepository o, OutboxRepository ob) { this.orders = o; this.outbox = ob; }

    @Transactional                                              // ONE local tx: state + intent-to-publish (§9)
    public void place(Order order) {
        orders.save(order);
        outbox.save(OutboxEvent.of("orders", order.id(), new OrderPlaced(order.id(), order.total())));
    }
}

@Component
class BillingConsumer {
    @KafkaListener(topics = "orders", groupId = "billing")
    void handle(ConsumerRecord<String, OrderPlaced> rec, Acknowledgment ack) {
        var e = rec.value();
        if (processed.putIfAbsent(e.orderId())) {               // idempotency key → redelivery is a no-op (§8)
            charge(e.orderId(), e.total());
        }
        ack.acknowledge();                                      // at-least-once: commit AFTER success (§6)
    }
}
```

**Interview talking points to be able to defend:**
- "In-process events and `@Async` decouple beans but aren't durable — if the JVM dies the work is gone; durability means a broker."
- "`@Async` and `@Transactional` are proxy-based, so self-invocation is a no-op — I call across a bean boundary, and never leave an `@Async void` without an exception handler."
- "`@Scheduled` runs on every instance in a cluster; I guard cluster-wide jobs with ShedLock or leader election."
- "At-least-once is the practical default, so I make consumers idempotent with an idempotency key — end-to-end exactly-once is a myth once external side-effects are involved."
- "I never dual-write DB then broker; I use a transactional outbox so the state change and the publish commit atomically, and a relay delivers with retries."

---

## Sources

- [Spring Framework Reference — Standard & Custom Events (`ApplicationEventPublisher`, `@EventListener`)](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework Reference — Transaction-bound Events (`@TransactionalEventListener`, `TransactionPhase`)](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Framework Reference — Task Execution & Scheduling (`@Async`, `@Scheduled`, `TaskExecutor`)](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring for Apache Kafka Reference — `@KafkaListener`](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/listener-annotation.html)
- [Spring for Apache Kafka Reference — Committing Offsets](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/ooo-commits.html)
- [Spring AMQP Reference — Annotation-driven Listener Endpoints (`@RabbitListener`)](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-annotation-driven.html)
- [Spring Boot Reference — Apache Kafka Support](https://docs.spring.io/spring-boot/reference/messaging/kafka.html)
- [Spring Boot Reference — AMQP (RabbitMQ) Support](https://docs.spring.io/spring-boot/reference/messaging/amqp.html)
- [ShedLock — distributed lock for `@Scheduled` (project README)](https://github.com/lukas-krecan/ShedLock)
