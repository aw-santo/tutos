---
title: Spring Security
tags:
  - spring
  - spring-boot
  - spring-security
  - authentication
  - authorization
  - oauth2
  - senior
aliases:
  - Spring Security
  - Authentication
  - Authorization
  - JWT
  - OAuth2
status: ready
created: 2026-07-09
---

# Spring Security

> [!abstract] Scope
> How Spring Security actually guards a request: the **servlet filter chain** that runs *before* your controller, the modern component-based `SecurityFilterChain` config, and the two halves of the job — **authentication** (who are you?) and **authorization** (what may you do?). We cover stateless JWT resource servers vs server-side sessions, OAuth2/OIDC, method security, and the settings people get catastrophically wrong (CSRF, matcher order, password hashing). For where these beans live see [[02 - IoC Container, Beans & Dependency Injection]]; for the APIs being secured see [[04 - Building REST APIs]].

Related: [[00 - Spring Boot Index]], [[04 - Building REST APIs]], [[01 - Spring Boot Fundamentals & Auto-Configuration]]

![[security-filter-chain.gif|720]]

*A request traverses the Spring Security filter chain — authentication first, then authorization — and only reaches your controller if both pass.*

---

## 1. Security runs *before* your controller: the filter chain

The single most important mental model: **Spring Security is a servlet `Filter`, not something inside Spring MVC.** It sits in front of the `DispatcherServlet` ([[04 - Building REST APIs]]), so an unauthenticated or unauthorized request is rejected *before your handler method ever runs*. There is no `@Secured` check buried in your controller doing the work — the chain already decided.

The wiring has three layers:

1. **`DelegatingFilterProxy`** — a standard Jakarta servlet filter (`jakarta.servlet.Filter`) that Boot registers in the container under the name `springSecurityFilterChain`. It owns no logic; it delegates to a Spring bean so the real filters can be Spring-managed and dependency-injected.
2. **`FilterChainProxy`** — the bean it delegates to. It holds an **ordered list of `SecurityFilterChain`s** and, for each request, runs the **first chain whose request matcher matches** (this ordering matters — see §2).
3. **The ordered filters** inside the matched chain, each with one job:

| Order | Filter | Responsibility |
|---|---|---|
| early | `SecurityContextHolderFilter` | loads any existing `Authentication` into the `SecurityContext` (replaced `SecurityContextPersistenceFilter` in 6.x) |
| | `CsrfFilter` | validates the CSRF token for state-changing requests (§8) |
| | `CorsFilter` | applies CORS policy before auth (§9) |
| | *auth filters* | `UsernamePasswordAuthenticationFilter`, `BearerTokenAuthenticationFilter` (JWT), OAuth2 login filters — whichever the config enabled |
| | `ExceptionTranslationFilter` | turns `AuthenticationException`/`AccessDeniedException` into a 401/403 or a redirect to login |
| last | `AuthorizationFilter` | the final authorization decision (replaced `FilterSecurityInterceptor` in 6.x) |

> [!tip] The one-sentence framing interviewers want
> "Spring Security is a chain of servlet filters in front of the DispatcherServlet — `DelegatingFilterProxy` hands off to `FilterChainProxy`, which picks the first matching `SecurityFilterChain` and runs its ordered filters; authentication happens early, authorization is the last filter, and my controller only executes if both pass." Naming `AuthorizationFilter` (not the removed `FilterSecurityInterceptor`) is a current-version signal.

---

## 2. Modern component-based configuration

The old `WebSecurityConfigurerAdapter` base class was **deprecated in Spring Security 5.7 and removed in 6.0** — do not use it, and flag it if you see it in a codebase. Modern config is a `SecurityFilterChain` `@Bean` built with the **lambda DSL** (in 7.x the lambda form is the only form; the chained non-lambda methods were removed).

```java
@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/actuator/health", "/login").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated())          // deny-by-default catch-all
            .oauth2ResourceServer(oauth2 -> oauth2       // stateless JWT (§5)
                .jwt(Customizer.withDefaults()))
            .sessionManagement(sm -> sm
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .csrf(csrf -> csrf.disable());               // SAFE here — token API, no cookies (§8)
        return http.build();
    }
}
```

You can define **multiple** `SecurityFilterChain` beans (e.g. one for `/api/**`, one for the browser UI), each with a `securityMatcher(...)` and an `@Order`. `FilterChainProxy` uses the first whose matcher matches — so ordering the beans wrong is a real footgun.

> [!warning] Gotcha #1 — request-matcher order: a broad `permitAll` shadows a protected route
> Authorization rules are evaluated **top to bottom, first match wins**. Write `.requestMatchers("/**").permitAll()` (or `/api/**`) above `.requestMatchers("/api/admin/**").hasRole("ADMIN")` and the admin rule is **dead code** — every request matches the broad rule first and sails through unauthenticated. Nothing warns you; it compiles, starts, and quietly leaves an endpoint wide open.
> **Mitigation:** order rules **most-specific first, broadest last**, and always end with `.anyRequest().authenticated()` (or `.denyAll()`) so the default is *closed*, not open. Add a test that hits the protected route unauthenticated and asserts 401/403.

---

## 3. Authentication: who are you?

Authentication establishes identity and stores an `Authentication` in the `SecurityContext`. The collaborators:

| Component | Role |
|---|---|
| `AuthenticationManager` | entry point; usually a `ProviderManager` delegating to a list of providers |
| `AuthenticationProvider` | one strategy (DAO/username-password, JWT, LDAP…); the first that supports the token handles it |
| `UserDetailsService` | loads a `UserDetails` (username, hashed password, authorities) by username — your bridge to the user store |
| `PasswordEncoder` | hashes and verifies passwords (§10) — **never** compares plaintext |

A username/password provider (`DaoAuthenticationProvider`) is auto-wired when you expose a `UserDetailsService` and a `PasswordEncoder`:

```java
@Bean
UserDetailsService users(UserRepository repo) {
    return username -> repo.findByUsername(username)          // load from your DB
        .map(u -> User.withUsername(u.getUsername())
            .password(u.getPasswordHash())                    // ALREADY a {bcrypt}… hash (§10)
            .authorities(u.getAuthorities())
            .build())
        .orElseThrow(() -> new UsernameNotFoundException("Bad credentials"));  // see gotcha
}

@Bean
PasswordEncoder passwordEncoder() {
    return PasswordEncoderFactories.createDelegatingPasswordEncoder();  // bcrypt by default (§10)
}
```

> [!warning] Gotcha #2 — user enumeration: leaking whether a username exists
> Returning `404 "no such user"` for an unknown username but `401 "wrong password"` for a known one lets an attacker **enumerate valid accounts** — a reconnaissance step for credential stuffing. The same leak comes from timing (bailing out early when the user is missing) and from a "forgot password" flow that says "no account with that email."
> **Mitigation:** respond identically for "unknown user" and "wrong password" — one generic *Bad credentials* / same status code, same body. Keep timing constant by still running a dummy password hash when the user is missing (`DaoAuthenticationProvider` has `hideUserNotFoundExceptions=true` on by default; don't defeat it). Return neutral "if that account exists, we sent an email" for password reset.

---

## 4. Authorization: what may you do?

Once identity is known, authorization decides access. Rules live in `authorizeHttpRequests` (§2) and match on paths, HTTP methods, or custom `RequestMatcher`s.

**Roles vs authorities — the `ROLE_` prefix trips everyone up:**

- `hasAuthority("ADMIN")` requires a `GrantedAuthority` of **exactly** `"ADMIN"`.
- `hasRole("ADMIN")` is a shortcut that requires `"ROLE_ADMIN"` — Spring adds the `ROLE_` prefix for you.

They are the same mechanism; a "role" is just an authority conventionally prefixed `ROLE_`. Mismatches (`hasRole("ROLE_ADMIN")` looking for `ROLE_ROLE_ADMIN`, or authorities stored without the prefix that `hasRole` expects) cause silent 403s.

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/products/**").permitAll()      // public reads
    .requestMatchers(HttpMethod.POST, "/products/**").hasRole("EDITOR")
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated())
```

> [!important] Deny by default
> Authorization should be **allowlist, not denylist**. End every chain with `.anyRequest().authenticated()` or `.denyAll()`; a route you forgot to list is then *closed*, and a code review catches the missing `permitAll` rather than a pen-tester finding an open endpoint. Fine-grained, data-dependent checks ("is this *my* order?") belong in method security (§7), not in path rules.

---

## 5. Stateless JWT vs server-side session — the core architectural choice

This is the decision interviewers push on. A **session** stores auth state server-side (a `JSESSIONID` cookie points at it); a **stateless JWT resource server** trusts a signed token on every request and stores nothing.

The JWT side is a few lines — Boot's `oauth2ResourceServer().jwt()` validates the token's signature, `exp`, and issuer against your identity provider's JWKS:

```java
// SecurityFilterChain fragment — validate a Bearer JWT on every request
.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(jwt -> jwt.jwtAuthenticationConverter(rolesConverter())))
```

```yaml
# application.yml — point at the IdP; Boot builds the JwtDecoder from the JWKS
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/store   # discovers jwk-set-uri
```

| Dimension | Stateless JWT | Server-side session | When to pick which |
|---|---|---|---|
| **Revocation** | hard — token is valid until `exp`; needs a denylist/short TTL + refresh | trivial — delete the session | need **instant logout / ban** → session |
| **Horizontal scale** | trivial — any node validates the signature, no shared state | needs sticky sessions or a shared store (Redis via Spring Session) | **stateless microservices / autoscaling** → JWT |
| **Primary attack surface** | **XSS** (steal a token in JS-readable storage) | **CSRF** (browser auto-sends the cookie) → §8 | browser app with server rendering → session + CSRF |
| **Token/cookie size** | larger — full claims sent every request | tiny opaque id | chatty low-latency APIs favor a small id |
| **Best fit** | SPA/mobile → API, service-to-service | classic server-rendered web app, admin portals | — |

> [!tip] The committed recommendation
> For a **service or SPA/mobile-facing API**, go **stateless JWT resource server** and accept the revocation cost by keeping access-token TTLs short (minutes) with refresh tokens — it scales horizontally with zero shared state. For a **server-rendered browser app** (admin console, internal tool), a **server-side session** is simpler and safer: instant revocation and the mature CSRF defenses of the framework. Don't put a raw JWT in `localStorage` for a browser app — that trades a solved CSRF problem for an XSS token-theft problem.

---

## 6. OAuth2 / OIDC login & client credentials

Spring Security is both a **resource server** (validates tokens, §5) and an **OAuth2 client**:

- **`oauth2Login()`** — OIDC *login*: users sign in via Google/Okta/Keycloak; Spring runs the authorization-code flow and creates an authenticated session. Configure providers under `spring.security.oauth2.client.registration.*`.
- **Client credentials** — *service-to-service* auth with no user; the app fetches its own token. Use an `OAuth2AuthorizedClientManager` (or the `RestClient`/`WebClient` OAuth2 integration) and grant type `client_credentials`.

```java
// browser login via an OIDC provider
http.oauth2Login(Customizer.withDefaults());
```

The rule of thumb: **resource server = you *validate* tokens; client = you *obtain* tokens.** Many services are both — accept user tokens on the way in, use client-credentials tokens on the way out to call a downstream service.

---

## 7. Method security: `@PreAuthorize` and the AOP catch

Path rules can't express "only the owner may edit this order." **Method security** puts the check on the method:

```java
@EnableMethodSecurity          // on a @Configuration class; enables the annotations below
public class MethodSecurityConfig { }

@Service
public class OrderService {

    @PreAuthorize("hasRole('ADMIN') or #order.ownerId == authentication.name")
    public void update(Order order) { /* ... */ }

    @PostAuthorize("returnObject.ownerId == authentication.name")
    public Order find(long id) { /* ... */ }
}
```

`@PreAuthorize` checks **before** the method runs (SpEL over arguments); `@PostAuthorize` checks the **return value** after. Method security is implemented with **Spring AOP proxies** — the check lives in a proxy wrapping your bean ([[02 - IoC Container, Beans & Dependency Injection]]).

> [!warning] Gotcha #3 — `@PreAuthorize` silently doesn't apply on self-invocation
> Because the check is on the **proxy**, it only fires when the call comes **through the proxy** — i.e. from another bean. If a method in the same class calls `this.update(order)` (self-invocation), the call bypasses the proxy entirely and **the `@PreAuthorize` never runs**. No error, no log — the security check is simply skipped, and the method executes unprotected.
> **Mitigation:** don't rely on internal self-calls for secured methods — call through an injected reference to the bean, split the secured method into a separate bean, or (last resort) use `AopContext.currentProxy()`. This is the exact same proxy-boundary trap as `@Transactional` self-invocation ([[02 - IoC Container, Beans & Dependency Injection]]) — one mental model covers both.

---

## 8. CSRF: the most misunderstood setting

CSRF (cross-site request forgery) exploits **ambient credentials** — anything the browser attaches automatically. A cookie (like `JSESSIONID`) is sent on *every* request to your domain, so a malicious page can forge a state-changing request and the browser helpfully authenticates it. Spring Security's `CsrfFilter` defends this by requiring a per-session token that a cross-site attacker can't read.

The decision hinges entirely on **how you authenticate**:

> [!warning] Gotcha #4 — disabling CSRF on a cookie/session browser app opens a real hole
> `csrf(csrf -> csrf.disable())` is copy-pasted from JWT tutorials into **cookie/session** apps constantly. If your auth rides on a session cookie, disabling CSRF means any malicious site can submit `POST /transfer` and the browser will attach the victim's cookie — a textbook CSRF exploit that moves money or changes settings. This is one of the most common serious misconfigurations in real Spring codebases.
> **Mitigation:** for a **cookie/session** app, **leave CSRF enabled** (`CookieCsrfTokenRepository.withHttpOnlyFalse()` for SPAs reading the token) and mark session cookies `SameSite=Lax/Strict`. Only disable CSRF when auth is a **`Authorization: Bearer` token** that the browser does *not* send automatically — then there is no ambient credential to forge, and disabling it is correct and expected.

Rule: **stateless token API → safe to disable CSRF. Cookie/session browser app → never disable it.**

---

## 9. CORS: not a security feature, but a security-adjacent one

CORS governs whether a browser lets JavaScript on *origin A* read a response from *origin B*. It is enforced by the **browser**, not your server — it protects users, it does not authorize requests. Configure it explicitly so your SPA can call the API:

```java
http.cors(Customizer.withDefaults());   // picks up the CorsConfigurationSource bean below

@Bean
CorsConfigurationSource corsSource() {
    var cfg = new CorsConfiguration();
    cfg.setAllowedOrigins(List.of("https://app.example.com"));   // NOT "*" with credentials
    cfg.setAllowedMethods(List.of("GET", "POST", "PUT", "DELETE"));
    var source = new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", cfg);
    return source;
}
```

> [!important] CORS must be wired *through* Spring Security
> Put CORS config in the security chain via `http.cors(...)` (backed by a `CorsConfigurationSource`), not only as an MVC `@CrossOrigin`. Otherwise the security filters run before MVC and reject the browser's preflight `OPTIONS` request, and you get mystifying CORS errors that look like an MVC bug but are a filter-order bug. Never combine `allowedOrigins("*")` with `allowCredentials(true)` — the browser rejects it, and it would be unsafe anyway.

---

## 10. Password storage: `DelegatingPasswordEncoder`

Never store plaintext or fast hashes (MD5/SHA-256) — those are brute-forced at billions/sec on a GPU. Use an **adaptive** hash: BCrypt or Argon2. Spring's default `PasswordEncoderFactories.createDelegatingPasswordEncoder()` stores an **id prefix** so you can migrate algorithms without a flag day:

```text
{bcrypt}$2a$10$N9qo8uLOickgx2ZMRZoMy...     ← the prefix tells Spring which encoder verifies it
{argon2}$argon2id$v=19$m=16384,t=2,p=1$...
```

> [!warning] Gotcha #5 — weak or missing hashing (and the `NoOpPasswordEncoder` trap)
> Storing passwords with no hash, a plain SHA-256, or `NoOpPasswordEncoder` (plaintext, deprecated for a reason) means a single database leak exposes every user's actual password — and because people reuse passwords, your breach becomes their bank's breach. `NoOpPasswordEncoder` shows up in tutorials and then survives into production.
> **Mitigation:** use the delegating encoder (BCrypt default, or Argon2id for new systems). Because the hash carries its algorithm/cost prefix, you can **upgrade cost or algorithm transparently** — verify with the old encoder on login, re-hash with the new one. Set a sensible BCrypt strength (10–12) and never log or echo password fields.

---

## 11. Securing Actuator

Actuator ([[12 - Actuator, Metrics & Observability]]) exposes operational endpoints — `/actuator/env`, `/heapdump`, `/mappings`, `/loggers` — that leak configuration and secrets or allow live changes. They are **not** public by default, and must not become public.

```java
@Bean
SecurityFilterChain actuator(HttpSecurity http) throws Exception {
    http
        .securityMatcher(EndpointRequest.toAnyEndpoint())        // this chain owns /actuator/**
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(EndpointRequest.to("health")).permitAll()  // health for k8s probes
            .anyRequest().hasRole("ACTUATOR_ADMIN"));            // everything else locked down
    return http.build();
}
```

> [!tip] Expose deliberately, protect always
> Only expose the endpoints you need — `management.endpoints.web.exposure.include=health,info,metrics`, **never `*`** in production. Put management on a **separate port** (`management.server.port`) that isn't internet-facing, keep `management.endpoint.health.show-details=when-authorized`, and require a role for everything except liveness/readiness. See [[12 - Actuator, Metrics & Observability]] for the endpoint catalog.

---

## 12. Caveats & risk mitigation (summary)

- **Deny by default (§2, §4).** End every chain with `anyRequest().authenticated()`/`denyAll()`; order matchers specific-first so a broad `permitAll` can't shadow a protected route.
- **CSRF depends on the credential (§8).** Disable only for `Bearer`-token APIs; keep it on for anything cookie/session-based.
- **Method security is proxy-based (§7).** Self-invocation bypasses `@PreAuthorize` — same trap as `@Transactional`.
- **Hash adaptively (§10).** BCrypt/Argon2 via the delegating encoder; never plaintext, fast hashes, or `NoOpPasswordEncoder`.
- **Don't leak identity signals (§3).** Uniform responses for unknown-user vs wrong-password to prevent enumeration.
- **Lock down Actuator (§11).** Expose the minimum, protect the rest, prefer a separate management port.
- **Version facts are volatile.** Spring Boot 4.1.x / Spring Security 7.1.x (7.0.x and 6.5.x also maintained) / Jakarta EE 11 (`jakarta.servlet`) / JDK 17 baseline are current as of mid-2026 — **re-verify** GA versions and DSL details before relying on them; the lambda DSL and `SecurityFilterChain` bean are the current shape, `WebSecurityConfigurerAdapter` is gone.

---

## 13. In practice

```java
// SecurityConfig.java — a stateless JWT API with a locked-down default
@Configuration
@EnableWebSecurity
@EnableMethodSecurity                                  // turns on @PreAuthorize (§7)
public class SecurityConfig {

    @Bean
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/actuator/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/products/**").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated())          // deny-by-default (§4)
            .oauth2ResourceServer(o -> o.jwt(Customizer.withDefaults()))  // JWT (§5)
            .sessionManagement(s -> s.sessionCreationPolicy(STATELESS))
            .cors(Customizer.withDefaults())            // wire CORS via security (§9)
            .csrf(c -> c.disable());                    // SAFE: Bearer-token API, no cookies (§8)
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {                 // BCrypt default, prefix-tagged (§10)
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }
}
```

**Interview talking points to be able to defend:**
- "Security is a servlet filter chain in front of the DispatcherServlet — `DelegatingFilterProxy` → `FilterChainProxy` → the ordered filters; authorization is the last filter, so my controller only runs if auth and authz pass."
- "`WebSecurityConfigurerAdapter` is gone since 6.0 — config is a `SecurityFilterChain` bean with the lambda DSL, and I end with `anyRequest().authenticated()` so the default is closed."
- "Roles are just authorities with a `ROLE_` prefix that `hasRole` adds for me — `hasAuthority` doesn't."
- "Stateless JWT scales without shared state but revocation is hard; sessions revoke instantly but need sticky/shared state — JWT's surface is XSS, a cookie session's is CSRF."
- "I disable CSRF only for Bearer-token APIs; for cookie/session apps disabling it opens a CSRF hole."
- "`@PreAuthorize` is AOP-proxy-based, so self-invocation silently skips it — same boundary as `@Transactional`."
- "Passwords go through the delegating encoder (BCrypt/Argon2) so I can upgrade the algorithm transparently; never plaintext or `NoOpPasswordEncoder`."

---

## 14. Sources

- [Spring Security Reference — Architecture (filter chain, DelegatingFilterProxy, FilterChainProxy)](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security Reference — Authorize HTTP Requests (`authorizeHttpRequests`, roles vs authorities)](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security Reference — OAuth2 Resource Server (JWT)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security Reference — Method Security (`@EnableMethodSecurity`, `@PreAuthorize`)](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security Reference — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security Reference — Password Storage (`DelegatingPasswordEncoder`, BCrypt/Argon2)](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html)
- [Spring Security Reference — What's New in 7.1](https://docs.spring.io/spring-security/reference/whats-new.html)
- [Spring Boot Reference — Securing Actuator endpoints (`EndpointRequest`)](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [OWASP — Cross-Site Request Forgery (CSRF) Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
- [OWASP — Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
- [OWASP — Authentication Cheat Sheet (user enumeration)](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [Spring Security 7.0.0 GA announcement (2025-11-17)](https://spring.io/blog/2025/11/17/spring-security-releases/)
