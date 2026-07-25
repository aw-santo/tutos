"""
gen_springboot_gifs.py — animated explainer GIFs for the Spring Boot track.

Built on the `animated-diagrams` engine (Pillow). Each build_* function writes
one GIF into this folder. Re-run to regenerate:

    python3 gen_springboot_gifs.py            # all figures
    python3 gen_springboot_gifs.py autoconfig # one figure by key

Figures:
  autoconfig   01 - starter on classpath -> @Conditional evaluation -> beans registered
  ioc          02 - bean definitions -> container wiring -> dependency injection + lifecycle
  request      05 - HTTP request through the filter chain -> DispatcherServlet -> controller
  nplus1       06 - the N+1 query problem, then collapsed to 1 by a fetch join
  security     08 - a request travelling the Spring Security filter chain
  observ       12 - request -> Micrometer meters -> export to Prometheus / OTLP
  startup      14 - JVM (JIT) vs native (AOT) startup time race
"""

import os, sys

# locate the engine shipped with the animated-diagrams skill
ENGINE_DIR = os.path.expanduser("~/.claude/skills/animated-diagrams")
sys.path.insert(0, ENGINE_DIR)

from engine import (
    Canvas, save_gif, eseq, ease, back, tween, mix, seg_point,
    SKY, MINT, GRAPE, TANG, PINK, TEAL, CORAL, SUN, INDIGO, GRAY,
    INK, SUB, FAINT, HAIR,
)

HERE = os.path.dirname(os.path.abspath(__file__))
def out(name): return os.path.join(HERE, name)


# ---------------------------------------------------------------------------
# 01 — Auto-configuration: starter on classpath -> @Conditional -> beans
# ---------------------------------------------------------------------------
def build_autoconfig():
    frames = []
    starter = (80, 250, 210, 96)     # x, y, w, h
    cond    = (415, 220, 210, 156)
    ctx     = (760, 200, 200, 240)
    checks  = ["@ConditionalOnClass", "@ConditionalOnMissingBean", "@ConditionalOnProperty"]
    beans   = ["DispatcherServlet", "TomcatServletWeb…", "Jackson ObjectMapper", "DataSource"]

    def base(c):
        c.header("1", "How auto-configuration wires your app", SKY)
        c.card(*starter, fill=SKY["soft"], line=SKY["bold"])
        c.text(starter[0] + starter[2] / 2, starter[1] + 34, "spring-boot-", size=15, weight="Semibold", fill=SKY["ink"], anchor="mm")
        c.text(starter[0] + starter[2] / 2, starter[1] + 58, "starter-web", size=15, weight="Semibold", fill=SKY["ink"], anchor="mm")
        c.tag(starter[0] + starter[2] / 2 - 26, starter[1] - 18, "on classpath")
        c.card(*cond, fill=GRAPE["soft"], line=GRAPE["bold"])
        c.text(cond[0] + cond[2] / 2, cond[1] + 22, "Auto-config classes", size=13, weight="Semibold", fill=GRAPE["ink"], anchor="mm")
        c.card(*ctx, fill=MINT["soft"], line=MINT["bold"])
        c.text(ctx[0] + ctx[2] / 2, ctx[1] + 22, "ApplicationContext", size=13, weight="Semibold", fill=MINT["ink"], anchor="mm")
        c.line(starter[0] + starter[2], starter[1] + starter[3] / 2, cond[0], cond[1] + cond[3] / 2, fill=HAIR)
        c.line(cond[0] + cond[2], cond[1] + cond[3] / 2, ctx[0], ctx[1] + ctx[3] / 2, fill=HAIR)

    # SCENE 1 — packet: starter -> condition evaluator
    path1 = [((starter[0] + starter[2], starter[1] + starter[3] / 2), (cond[0], cond[1] + cond[3] / 2))]
    for t in eseq(26):
        c = Canvas(style="bytebytego"); base(c)
        px, py = seg_point(path1, t)
        c.glow(px, py, SKY["bold"])
        c.footer("A starter puts libraries on the classpath — that's the only trigger.", SKY, step=0, total=3)
        frames.append(c.img)

    # SCENE 2 — conditions light up one by one (all pass -> green ✓)
    for t in eseq(30):
        c = Canvas(style="bytebytego"); base(c)
        for i, name in enumerate(checks):
            lit = max(0.0, min(1.0, t * 1.7 - i * 0.28))
            y = cond[1] + 52 + i * 34
            col = mix(FAINT, MINT["bold"], lit)
            c.text(cond[0] + 16, y, ("✓ " if lit > 0.6 else "• ") + name, size=11.5,
                   weight="Medium", fill=col, anchor="lm")
        c.footer("Each auto-config is guarded by @Conditional checks — it backs off if they fail.", GRAPE, step=1, total=3)
        frames.append(c.img)

    # SCENE 3 — beans pop into the context
    for t in eseq(30):
        c = Canvas(style="bytebytego"); base(c)
        for i, name in enumerate(checks):
            y = cond[1] + 52 + i * 34
            c.text(cond[0] + 16, y, "✓ " + name, size=11.5, weight="Medium", fill=MINT["bold"], anchor="lm")
        for i, name in enumerate(beans):
            grow = back(max(0.0, min(1.0, t * 1.8 - i * 0.22)))
            if grow <= 0.02:
                continue
            w, h = 168 * grow, 30 * grow
            bx = ctx[0] + (ctx[2] - w) / 2
            by = ctx[1] + 54 + i * 42
            c.card(bx, by + (30 - h) / 2, w, h, fill="#FFFFFF", line=MINT["bold"], r=8)
            if grow > 0.75:
                c.text(ctx[0] + ctx[2] / 2, by + 15, name, size=10.5, weight="Medium", fill=INK, anchor="mm")
        c.footer("Beans you never declared appear — sensible defaults you can still override.", MINT, step=2, total=3)
        frames.append(c.img)

    save_gif(frames, out("springboot-autoconfig.gif"), frame_ms=72)


# ---------------------------------------------------------------------------
# 02 — IoC container: definitions -> singletons -> dependency injection
# ---------------------------------------------------------------------------
def build_ioc():
    frames = []
    container = (150, 150, 740, 340)
    # three beans inside the container
    ctrl = (250, 250, 170, 84)
    svc  = (520, 250, 170, 84)
    repo = (520, 380, 170, 84)  # unused position; keep repo to the right lower

    def outer(c, title_pal=GRAPE):
        c.header("2", "The IoC container wires your beans", title_pal)
        c.card(*container, fill=GRAPE["soft"], line=GRAPE["bold"], r=18)
        c.text(container[0] + 20, container[1] + 22, "ApplicationContext", size=13, weight="Semibold", fill=GRAPE["ink"], anchor="lm")

    def bean(c, box, label, pal, lit=1.0):
        fill = mix("#FFFFFF", pal["soft"], lit)
        c.card(*box, fill=fill, line=pal["bold"], r=12)
        c.text(box[0] + box[2] / 2, box[1] + box[3] / 2, label, size=13, weight="Semibold", fill=pal["ink"], anchor="mm")

    repo = (610, 360, 170, 84)

    # SCENE 1 — beans pop in from their definitions
    for t in eseq(26):
        c = Canvas(style="playful"); outer(c)
        for i, (box, label, pal) in enumerate([(ctrl, "@RestController", SKY), (svc, "@Service", MINT), (repo, "@Repository", TANG)]):
            grow = back(max(0.0, min(1.0, t * 1.7 - i * 0.25)))
            if grow <= 0.02:
                continue
            w, h = box[2] * grow, box[3] * grow
            bean(c, (box[0] + (box[2] - w) / 2, box[1] + (box[3] - h) / 2, w, h), label if grow > 0.7 else "", pal)
        c.footer("The container instantiates one singleton per bean definition.", GRAPE, step=0, total=2)
        frames.append(c.img)

    # SCENE 2 — dependencies injected (arrows draw controller<-service<-repo)
    seg_a = [((ctrl[0] + ctrl[2], ctrl[1] + ctrl[3] / 2), (svc[0], svc[1] + svc[3] / 2))]
    seg_b = [((svc[0] + svc[2] / 2, svc[1] + svc[3]), (repo[0] + repo[2] / 2, repo[1]))]
    for t in eseq(34):
        c = Canvas(style="playful"); outer(c)
        bean(c, ctrl, "@RestController", SKY)
        bean(c, svc, "@Service", MINT)
        bean(c, repo, "@Repository", TANG)
        # arrow 1 grows in first half, arrow 2 in second half
        a1 = min(1.0, t * 2)
        a2 = max(0.0, t * 2 - 1)
        x0, y0 = ctrl[0] + ctrl[2], ctrl[1] + ctrl[3] / 2
        c.arrow(x0, y0, x0 + (svc[0] - x0) * a1, y0, fill=SKY["bold"], width=3)
        if a1 > 0.9:
            c.tag((x0 + svc[0]) / 2 - 18, y0 - 20, "injects")
        if a2 > 0:
            xb0, yb0 = svc[0] + svc[2] / 2, svc[1] + svc[3]
            c.arrow(xb0, yb0, xb0, yb0 + (repo[1] - yb0) * a2, fill=MINT["bold"], width=3)
        c.footer("Then it injects each bean's dependencies — you never call `new`.", MINT, step=1, total=2)
        frames.append(c.img)

    save_gif(frames, out("ioc-container.gif"), frame_ms=74)


# ---------------------------------------------------------------------------
# 05 — Request lifecycle: filter chain -> DispatcherServlet -> controller
# ---------------------------------------------------------------------------
def build_request():
    frames = []
    stages = [("Filters", TEAL, 70), ("Dispatcher\nServlet", SKY, 300),
              ("Handler\nMapping", GRAPE, 530), ("@Controller", MINT, 760)]
    bw, bh, by = 190, 96, 270

    def base(c, lit=-1):
        c.header("5", "The servlet request lifecycle", SKY)
        for i, (name, pal, x) in enumerate(stages):
            on = (i == lit)
            fill = mix(pal["soft"], pal["bold"], 1.0) if on else pal["soft"]
            c.card(x, by, bw, bh, fill=fill, line=pal["bold"])
            lines = name.split("\n")
            yy = by + bh / 2 - (len(lines) - 1) * 9
            for ln in lines:
                c.text(x + bw / 2, yy, ln, size=14, weight="Semibold",
                       fill=(pal["on"] if on else pal["ink"]), anchor="mm")
                yy += 18
            if i < len(stages) - 1:
                c.line(x + bw, by + bh / 2, stages[i + 1][2], by + bh / 2, fill=HAIR)

    path = [((stages[i][2] + bw, by + bh / 2), (stages[i + 1][2], by + bh / 2)) for i in range(len(stages) - 1)]
    # incoming from the left edge into first box
    lead = [((20, by + bh / 2), (stages[0][2], by + bh / 2))]

    for t in eseq(20):  # request enters
        c = Canvas(style="bytebytego"); base(c, lit=0)
        px, py = seg_point(lead, t)
        c.glow(px, py, TANG["bold"])
        c.footer("An HTTP request first passes the servlet filter chain (CORS, security, etc.).", TEAL, step=0, total=2)
        frames.append(c.img)

    for t in eseq(46):  # travel through the chain
        c = Canvas(style="bytebytego")
        lit = min(len(stages) - 1, int(t * len(stages)))
        base(c, lit=lit)
        px, py = seg_point(path, t)
        c.glow(px, py, TANG["bold"])
        c.footer("DispatcherServlet is the front controller: it finds the handler and invokes it.", SKY, step=1, total=2)
        frames.append(c.img)

    save_gif(frames, out("request-lifecycle.gif"), frame_ms=66)


# ---------------------------------------------------------------------------
# 06 — The N+1 query problem, then collapsed to 1 by a fetch join
# ---------------------------------------------------------------------------
def build_nplus1():
    frames = []
    app = (90, 250, 180, 90)
    db = (820, 300)  # cylinder center-ish
    N = 5

    def base(c, pal, title):
        c.header("6", title, pal)
        c.card(*app, fill=SKY["soft"], line=SKY["bold"])
        c.text(app[0] + app[2] / 2, app[1] + app[3] / 2, "JPA / Hibernate", size=14, weight="Semibold", fill=SKY["ink"], anchor="mm")
        c.icon_db(db[0], db[1], 120, GRAY["bold"])
        c.text(db[0], db[1] + 92, "orders + items", size=11, weight="Medium", fill=SUB, anchor="mm")

    # SCENE 1 — the parent query + N child queries fan out; counter counts up
    ax, ay = app[0] + app[2], app[1] + app[3] / 2
    targets = [(db[0] - 60, 150 + i * 70) for i in range(N)]
    parent_seg = [((ax, ay), (db[0] - 60, ay))]
    for t in eseq(46):
        c = Canvas(style="bytebytego"); base(c, CORAL, "The N+1 problem")
        # parent query fires first (t<0.25)
        pt = min(1.0, t / 0.22)
        px, py = seg_point(parent_seg, pt)
        c.glow(px, py, MINT["bold"])
        count = 1
        if t > 0.24:
            u = (t - 0.24) / 0.76
            revealed = min(N, int(u * N) + 1)
            for i in range(revealed):
                seg = [((ax, ay), targets[i])]
                sub_u = max(0.0, min(1.0, u * N - i))
                qx, qy = seg_point(seg, sub_u)
                c.arrow(ax, ay, targets[i][0], targets[i][1], fill=mix(HAIR, CORAL["bold"], min(1.0, sub_u * 1.5)), width=2)
                c.glow(qx, qy, CORAL["bold"])
            count = 1 + revealed
        c.badge(500, 500, f"queries: {count}", CORAL if count > 1 else MINT, size=13)
        c.footer("Load N orders, then lazily load each order's items — 1 + N round-trips.", CORAL, step=0, total=2)
        frames.append(c.img)

    # SCENE 2 — the fix: a single fetch-join query, counter collapses to 1
    for t in eseq(30):
        c = Canvas(style="bytebytego"); base(c, MINT, "Fixed: one fetch join")
        u = min(1.0, t * 1.4)
        qx, qy = seg_point(parent_seg, u)
        c.arrow(ax, ay, db[0] - 60, ay, fill=mix(HAIR, MINT["bold"], u), width=4)
        c.glow(qx, qy, MINT["bold"])
        c.tag((ax + db[0] - 60) / 2 - 70, ay - 24, "JOIN FETCH o.items")
        c.badge(500, 500, "queries: 1", MINT, size=13)
        c.footer("`join fetch` (or an entity graph) loads parents and children in one query.", MINT, step=1, total=2)
        frames.append(c.img)

    save_gif(frames, out("jpa-n-plus-one.gif"), frame_ms=70)


# ---------------------------------------------------------------------------
# 08 — Spring Security filter chain
# ---------------------------------------------------------------------------
def build_security():
    frames = []
    filters = [
        ("SecurityContext\nPersistence", INDIGO),
        ("Authentication\nFilter", SKY),
        ("Authorization\nFilter", GRAPE),
    ]
    fw, fh, fy = 175, 92, 210
    xs = [110, 330, 550]
    app = (790, 210, 150, 92)

    def base(c, lit=-1, blocked=False):
        c.header("8", "The Spring Security filter chain", INDIGO)
        for i, (name, pal) in enumerate(filters):
            on = (i == lit)
            fill = mix(pal["soft"], pal["bold"], 1.0) if on else pal["soft"]
            c.card(xs[i], fy, fw, fh, fill=fill, line=pal["bold"])
            lines = name.split("\n")
            yy = fy + fh / 2 - (len(lines) - 1) * 9
            for ln in lines:
                c.text(xs[i] + fw / 2, yy, ln, size=12.5, weight="Semibold",
                       fill=(pal["on"] if on else pal["ink"]), anchor="mm")
                yy += 18
            if i < len(filters) - 1:
                c.line(xs[i] + fw, fy + fh / 2, xs[i + 1], fy + fh / 2, fill=HAIR)
        c.line(xs[2] + fw, fy + fh / 2, app[0], fy + fh / 2, fill=HAIR)
        appfill = CORAL["soft"] if blocked else MINT["soft"]
        appline = CORAL["bold"] if blocked else MINT["bold"]
        c.card(*app, fill=appfill, line=appline)
        c.text(app[0] + app[2] / 2, app[1] + app[3] / 2, "your\n@Controller".split("\n")[0], size=12.5, weight="Semibold", fill=INK, anchor="mm")
        c.text(app[0] + app[2] / 2, app[1] + app[3] / 2 + 16, "@Controller", size=12.5, weight="Semibold", fill=INK, anchor="mm")

    seg = ([((20, fy + fh / 2), (xs[0], fy + fh / 2))] +
           [((xs[i] + fw, fy + fh / 2), (xs[i + 1], fy + fh / 2)) for i in range(len(filters) - 1)] +
           [((xs[2] + fw, fy + fh / 2), (app[0], fy + fh / 2))])

    # SCENE 1 — authorized request passes all filters and reaches the controller
    for t in eseq(50):
        c = Canvas(style="bytebytego")
        lit = min(len(filters) - 1, int(t * (len(filters) + 1)))
        base(c, lit=lit)
        px, py = seg_point(seg, t)
        c.glow(px, py, TANG["bold"])
        c.footer("Every request runs the filter chain BEFORE your controller — authN then authZ.", INDIGO, step=0, total=2)
        frames.append(c.img)

    # SCENE 2 — unauthorized request blocked at the authorization filter
    stop_u = 2.0 / (len(seg))  # roughly at authZ filter
    for t in eseq(30):
        c = Canvas(style="bytebytego")
        tt = min(t, 0.55)
        lit = min(2, int(tt * (len(filters) + 1)))
        base(c, lit=lit, blocked=(t > 0.5))
        px, py = seg_point(seg, tt)
        col = CORAL["bold"] if t > 0.5 else TANG["bold"]
        c.glow(px, py, col)
        if t > 0.5:
            c.text(xs[2] + fw / 2, fy - 22, "403 ✗", size=15, weight="Bold", fill=CORAL["bold"], anchor="mm")
        c.footer("No/insufficient authority -> rejected at the chain, never reaching your code.", CORAL, step=1, total=2)
        frames.append(c.img)

    save_gif(frames, out("security-filter-chain.gif"), frame_ms=64)


# ---------------------------------------------------------------------------
# 12 — Observability pipeline: request -> Micrometer -> exporters
# ---------------------------------------------------------------------------
def build_observ():
    frames = []
    req = (70, 260, 150, 84)
    meter = (330, 240, 190, 130)
    prom = (720, 180, 210, 70)
    otlp = (720, 300, 210, 70)

    def base(c):
        c.header("12", "The observability pipeline", TEAL)
        c.card(*req, fill=SKY["soft"], line=SKY["bold"])
        c.text(req[0] + req[2] / 2, req[1] + req[3] / 2, "request", size=14, weight="Semibold", fill=SKY["ink"], anchor="mm")
        c.card(*meter, fill=TEAL["soft"], line=TEAL["bold"])
        c.text(meter[0] + meter[2] / 2, meter[1] + 24, "Micrometer", size=13, weight="Semibold", fill=TEAL["ink"], anchor="mm")
        c.card(*prom, fill=TANG["soft"], line=TANG["bold"])
        c.text(prom[0] + prom[2] / 2, prom[1] + prom[3] / 2, "Prometheus", size=12.5, weight="Semibold", fill=TANG["ink"], anchor="mm")
        c.card(*otlp, fill=GRAPE["soft"], line=GRAPE["bold"])
        c.text(otlp[0] + otlp[2] / 2, otlp[1] + otlp[3] / 2, "OTLP / traces", size=12.5, weight="Semibold", fill=GRAPE["ink"], anchor="mm")
        c.line(req[0] + req[2], req[1] + req[3] / 2, meter[0], meter[1] + meter[3] / 2, fill=HAIR)
        c.line(meter[0] + meter[2], meter[1] + 40, prom[0], prom[1] + prom[3] / 2, fill=HAIR)
        c.line(meter[0] + meter[2], meter[1] + 90, otlp[0], otlp[1] + otlp[3] / 2, fill=HAIR)

    seg_in = [((req[0] + req[2], req[1] + req[3] / 2), (meter[0], meter[1] + meter[3] / 2))]
    seg_p = [((meter[0] + meter[2], meter[1] + 40), (prom[0], prom[1] + prom[3] / 2))]
    seg_o = [((meter[0] + meter[2], meter[1] + 90), (otlp[0], otlp[1] + otlp[3] / 2))]

    for t in eseq(56):
        c = Canvas(style="bytebytego"); base(c)
        # incoming request pulses in, counter counts up
        n_req = int(tween(0, 128, ease(min(1.0, t * 1.3))))
        lat = tween(0, 42, ease(min(1.0, t * 1.3)))
        c.text(meter[0] + meter[2] / 2, meter[1] + 62, f"http.requests: {n_req}", size=11, weight="Medium", fill=INK, anchor="mm")
        c.text(meter[0] + meter[2] / 2, meter[1] + 84, f"p99: {lat:.0f} ms", size=11, weight="Medium", fill=INK, anchor="mm")
        c.text(meter[0] + meter[2] / 2, meter[1] + 106, "Timer · Counter", size=10, weight="Regular", fill=SUB, anchor="mm")
        # request packet in
        ip = min(1.0, t * 2.2)
        gx, gy = seg_point(seg_in, ip)
        c.glow(gx, gy, SKY["bold"])
        # export packets out (second half)
        if t > 0.45:
            u = (t - 0.45) / 0.55
            for seg, col in [(seg_p, TANG["bold"]), (seg_o, GRAPE["bold"])]:
                ex, ey = seg_point(seg, u)
                c.glow(ex, ey, col)
        c.footer("One instrumentation API (Micrometer) records timers/counters, exports anywhere.", TEAL, step=0, total=1)
        frames.append(c.img)

    save_gif(frames, out("observability-pipeline.gif"), frame_ms=64)


# ---------------------------------------------------------------------------
# 14 — Startup race: JVM (JIT) vs native image (AOT)
# ---------------------------------------------------------------------------
def build_startup():
    frames = []
    jvm_target = 2.6      # seconds (illustrative)
    nat_target = 0.05
    bar_x, bar_w = 300, 560
    jvm_y, nat_y, bh = 250, 360, 54

    def base(c):
        c.header("14", "Startup: JVM (JIT) vs native (AOT)", MINT)
        c.text(bar_x - 20, jvm_y + bh / 2, "JVM jar", size=14, weight="Semibold", fill=TANG["ink"], anchor="rm")
        c.text(bar_x - 20, nat_y + bh / 2, "Native", size=14, weight="Semibold", fill=MINT["ink"], anchor="rm")
        c.card(bar_x, jvm_y, bar_w, bh, fill="#FFFFFF", line=HAIR, r=10, shadow=False)
        c.card(bar_x, nat_y, bar_w, bh, fill="#FFFFFF", line=HAIR, r=10, shadow=False)

    for t in eseq(56):
        c = Canvas(style="playful"); base(c)
        # native finishes almost instantly; jvm crawls
        nat_p = min(1.0, t / 0.06)
        jvm_p = ease(min(1.0, t))
        # native bar
        c.card(bar_x, nat_y, max(6, bar_w * nat_p), bh, fill=MINT["soft"], line=MINT["bold"], r=10, shadow=False)
        nat_val = nat_target * nat_p
        c.text(bar_x + max(6, bar_w * nat_p) + 12, nat_y + bh / 2, f"{nat_val:.2f}s", size=13, weight="Bold", fill=MINT["bold"], anchor="lm")
        # jvm bar
        c.card(bar_x, jvm_y, max(6, bar_w * jvm_p), bh, fill=TANG["soft"], line=TANG["bold"], r=10, shadow=False)
        jvm_val = jvm_target * jvm_p
        c.text(bar_x + max(6, bar_w * jvm_p) + 12, jvm_y + bh / 2, f"{jvm_val:.2f}s", size=13, weight="Bold", fill=TANG["bold"], anchor="lm")
        c.footer("AOT does at build time what the JVM does at startup — seconds become milliseconds.", MINT, step=0, total=1)
        frames.append(c.img)

    save_gif(frames, out("startup-jit-vs-native.gif"), frame_ms=60)


# ---------------------------------------------------------------------------
# 03 — Config precedence: env var beats the profile file beats application.yml
# ---------------------------------------------------------------------------
def build_config():
    frames = []
    sources = [
        ("CLI args", "(none set)", GRAY),
        ("System props", "(none set)", GRAY),
        ("OS env vars", "SERVER_PORT=9000", TANG),
        ("application-prod.yml", "server.port=8080", SKY),
        ("application.yml", "server.port=8081", GRAY),
    ]
    x, w, h, gap = 320, 400, 62, 14
    top = 110

    def card_y(i): return top + i * (h + gap)

    def base(c, lit=None, dim=None):
        c.header("3", "Property-source precedence", TANG)
        c.text(x + w / 2, 90, "highest priority", size=11, weight="Medium", fill=SUB, anchor="mm")
        for i, (name, val, pal) in enumerate(sources):
            y = card_y(i)
            active = (lit is not None and i == lit)
            faded = (dim is not None and i > dim)
            fill = mix("#FFFFFF", MINT["soft"], 1.0) if active else ("#F3F5F8" if faded else "#FFFFFF")
            line = MINT["bold"] if active else (HAIR if faded else pal["bold"])
            c.card(x, y, w, h, fill=fill, line=line, r=10, shadow=not faded)
            tcol = FAINT if faded else INK
            c.text(x + 16, y + 20, name, size=13, weight="Semibold", fill=tcol, anchor="lm")
            c.text(x + 16, y + 44, val, size=12, weight="Regular", fill=(MINT["bold"] if active else (FAINT if faded else SUB)), anchor="lm")
            if active:
                c.text(x + w - 16, y + h / 2, "✓", size=20, weight="Bold", fill=MINT["bold"], anchor="rm")
            if faded:
                c.text(x + w - 16, y + h / 2, "✗", size=16, weight="Bold", fill=FAINT, anchor="rm")

    # SCENE 1 — a lookup packet drops down the stack, checking each source
    path = [((x + w / 2, card_y(i) + h / 2), (x + w / 2, card_y(i + 1) + h / 2)) for i in range(4)]
    for t in eseq(60):
        c = Canvas(style="playful")
        stage = t * 3  # reaches env-var card (index 2) at t=1.0
        lit_idx = min(2, int(stage))
        base(c)
        px, py = seg_point(path[:3], t)
        c.glow(px, py, TANG["bold"])
        c.footer("Spring reads server.port top-down and stops at the first source that sets it.", TANG, step=0, total=2)
        frames.append(c.img)

    # SCENE 2 — settle: env var wins, the file below is unreached
    for t in eseq(34):
        c = Canvas(style="playful")
        base(c, lit=2, dim=2)
        c.text(x + w / 2, card_y(4) + h + 40, "Effective: 9000  (8080 in the file never applies)",
               size=14, weight="Semibold", fill=mix("#FFFFFF", TANG["bold"], min(1.0, t * 2)), anchor="mm")
        c.footer("The env var outranks the profile file — no error, no warning, just silence.", TANG, step=1, total=2)
        frames.append(c.img)

    save_gif(frames, out("config-precedence.gif"), frame_ms=65)


# ---------------------------------------------------------------------------
# 04 — DTOs strip over-posted fields; binding the entity directly lets them through
# ---------------------------------------------------------------------------
def build_dto():
    frames = []
    src = (400, 130, 240, 70)
    wrong_e = (120, 320, 220, 100)
    right_dto = (700, 300, 220, 70)
    right_e = (700, 420, 220, 90)

    def base(c):
        c.header("4", "DTO binding vs. binding the entity", CORAL)
        c.card(*src, fill=GRAY["soft"], line=GRAY["bold"], r=10)
        c.text(src[0] + src[2] / 2, src[1] + 22, "incoming JSON", size=12, weight="Semibold", fill=INK, anchor="mm")
        c.text(src[0] + src[2] / 2, src[1] + 46, '{ role: "ADMIN", ... }', size=11.5, weight="Regular", fill=SUB, anchor="mm")
        c.tag(wrong_e[0] + 60, wrong_e[1] - 22, "WRONG — bind Order entity")
        c.tag(right_dto[0] + 40, right_dto[1] - 22, "RIGHT — bind CreateOrderRequest DTO")
        c.line(src[0], src[1] + src[3] * 0.8, wrong_e[0] + wrong_e[2] / 2, wrong_e[1], fill=HAIR)
        c.line(src[0] + src[2], src[1] + src[3] * 0.8, right_dto[0] + right_dto[2] / 2, right_dto[1], fill=HAIR)

    # SCENE 1 — packet splits into two lanes
    seg_wrong = [((src[0] + 40, src[1] + src[3]), (wrong_e[0] + wrong_e[2] / 2, wrong_e[1]))]
    seg_right = [((src[0] + src[2] - 40, src[1] + src[3]), (right_dto[0] + right_dto[2] / 2, right_dto[1]))]
    for t in eseq(30):
        c = Canvas(style="playful"); base(c)
        c.glow(*seg_point(seg_wrong, t), CORAL["bold"])
        c.glow(*seg_point(seg_right, t), MINT["bold"])
        c.footer("The same request body, bound two different ways.", CORAL, step=0, total=2)
        frames.append(c.img)

    # SCENE 2 — wrong lane: role passes through unfiltered; right lane: DTO drops it
    for t in eseq(40):
        c = Canvas(style="playful"); base(c)
        c.card(*wrong_e, fill=CORAL["soft"], line=CORAL["bold"], r=10)
        c.text(wrong_e[0] + wrong_e[2] / 2, wrong_e[1] + 26, "Order entity", size=12.5, weight="Semibold", fill=CORAL["ink"], anchor="mm")
        role_y = wrong_e[1] + 26 + 32 * ease(t)
        c.text(wrong_e[0] + wrong_e[2] / 2, min(role_y, wrong_e[1] + wrong_e[3] - 16), 'role = "ADMIN"',
               size=12, weight="Bold", fill=CORAL["bold"], anchor="mm")
        c.card(*right_dto, fill=MINT["soft"], line=MINT["bold"], r=10)
        c.text(right_dto[0] + right_dto[2] / 2, right_dto[1] + right_dto[3] / 2, "CreateOrderRequest", size=12.5, weight="Semibold", fill=MINT["ink"], anchor="mm")
        drop = ease(t)
        drop_y = right_dto[1] + right_dto[3] + 10 + 26 * drop
        opac = max(0.0, 1.0 - drop * 1.4)
        if opac > 0.05:
            c.text(right_dto[0] + right_dto[2] / 2, drop_y, 'role = "ADMIN"  ✗',
                   size=11.5, weight="Medium", fill=mix("#FFFFFF", CORAL["bold"], opac), anchor="mm")
        c.card(*right_e, fill="#FFFFFF", line=MINT["bold"], r=10, shadow=False)
        c.text(right_e[0] + right_e[2] / 2, right_e[1] + 22, "Order entity", size=12, weight="Semibold", fill=INK, anchor="mm")
        c.text(right_e[0] + right_e[2] / 2, right_e[1] + 48, "customerRef, items only", size=11, weight="Regular", fill=MINT["bold"], anchor="mm")
        c.footer("A DTO only has the fields you declared — there's no `role` to bind.", MINT, step=1, total=2)
        frames.append(c.img)

    save_gif(frames, out("dto-vs-entity.gif"), frame_ms=70)


# ---------------------------------------------------------------------------
# 07 — A checked exception mid-transaction commits the half-done work
# ---------------------------------------------------------------------------
def build_rollback():
    frames = []
    steps = ["debit(A)", "checkBalance()", "throw InsufficientFundsException", "credit(B)"]
    rail_x, rail_y, rail_w = 140, 230, 760
    boundary = (100, 150, 840, 340)

    def base(c, boundary_label="@Transactional", boundary_pal=SKY):
        c.header("7", "Checked exceptions don't roll back by default", CORAL)
        c.card(*boundary, fill=boundary_pal["soft"], line=boundary_pal["bold"], r=16)
        c.text(boundary[0] + 20, boundary[1] + 24, boundary_label, size=13, weight="Semibold", fill=boundary_pal["ink"], anchor="lm")
        for i, s in enumerate(steps):
            sx = rail_x + i * (rail_w / (len(steps) - 1))
            c.dot(sx, rail_y, 5, fill=HAIR)
            c.text(sx, rail_y + 26, s, size=10.5, weight="Medium", fill=SUB, anchor="mm")
        c.line(rail_x, rail_y, rail_x + rail_w, rail_y, fill=HAIR)
        c.card(240, 400, 220, 90, fill="#FFFFFF", line=MINT["bold"], r=10, shadow=False)
        c.card(560, 400, 220, 90, fill="#FFFFFF", line=MINT["bold"], r=10, shadow=False)

    def balances(c, a, b):
        c.text(240 + 110, 424, "Account A", size=12, weight="Semibold", fill=INK, anchor="mm")
        c.text(240 + 110, 456, f"${a:.0f}", size=18, weight="Bold", fill=(CORAL["bold"] if a < 100 else INK), anchor="mm")
        c.text(560 + 110, 424, "Account B", size=12, weight="Semibold", fill=INK, anchor="mm")
        c.text(560 + 110, 456, f"${b:.0f}", size=18, weight="Bold", fill=INK, anchor="mm")

    # SCENE 1 — execution runs the rail: debit succeeds, throw hits, credit never runs
    for t in eseq(56):
        c = Canvas(style="playful"); base(c)
        prog = t * 3  # 3 segments across 4 steps
        idx = min(3, int(prog) + 1)
        for i in range(idx):
            sx0 = rail_x + i * (rail_w / (len(steps) - 1))
            sx1 = rail_x + (i + 1) * (rail_w / (len(steps) - 1))
            frac = 1.0 if i < int(prog) else (prog - int(prog))
            c.line(sx0, rail_y, sx0 + (sx1 - sx0) * frac, rail_y, fill=CORAL["bold"], width=3)
        a = 100 - 100 * min(1.0, prog)
        balances(c, a, 50)
        if prog >= 2.0:
            bolt_t = min(1.0, prog - 2.0)
            c.text(rail_x + 2 * (rail_w / 3), rail_y - 24, "✗ throws", size=13, weight="Bold",
                   fill=mix("#FFFFFF", CORAL["bold"], bolt_t), anchor="mm")
        c.footer("debit(A) runs, the exception fires, credit(B) never executes.", CORAL, step=0, total=2)
        frames.append(c.img)

    # SCENE 2 — the transaction still commits: $50 is gone, nowhere
    for t in eseq(40):
        c = Canvas(style="playful"); base(c, boundary_label="@Transactional  →  COMMIT", boundary_pal=CORAL)
        for i in range(3):
            sx0 = rail_x + i * (rail_w / (len(steps) - 1))
            sx1 = rail_x + (i + 1) * (rail_w / (len(steps) - 1))
            c.line(sx0, rail_y, sx1, rail_y, fill=(CORAL["bold"] if i < 2 else HAIR), width=3)
        balances(c, 0, 50)
        ghost = ease(t)
        c.text(400, 330, "$50 vanished — checked exceptions don't trigger rollback",
               size=13, weight="Semibold", fill=mix("#FFFFFF", CORAL["bold"], ghost), anchor="mm")
        c.footer("Fix: rollbackFor = Exception.class, or throw an unchecked exception.", CORAL, step=1, total=2)
        frames.append(c.img)

    save_gif(frames, out("transaction-rollback.gif"), frame_ms=65)


# ---------------------------------------------------------------------------
# 09 — Cache stampede on TTL expiry, and sync=true fixing it
# ---------------------------------------------------------------------------
def build_cache_stampede():
    frames = []
    cache = (430, 180, 200, 110)
    db = (430, 420, 200, 90)
    clients = [(140, 160), (140, 260), (140, 360), (860, 160), (860, 260), (860, 360)]

    def base(c, ttl_frac, title="Cache stampede on expiry"):
        c.header("9", title, TANG)
        c.card(*cache, fill=TANG["soft"], line=TANG["bold"], r=12)
        c.text(cache[0] + cache[2] / 2, cache[1] + 26, "product-42", size=13, weight="Semibold", fill=TANG["ink"], anchor="mm")
        bar_w = cache[2] - 30
        c.card(cache[0] + 15, cache[1] + 50, bar_w, 10, fill="#FFFFFF", line=HAIR, r=5, shadow=False)
        c.card(cache[0] + 15, cache[1] + 50, bar_w * max(0, ttl_frac), 10, fill=MINT["bold"], line=None, r=5, shadow=False)
        c.text(cache[0] + cache[2] / 2, cache[1] + 78, f"TTL {'expired' if ttl_frac <= 0 else f'{int(ttl_frac*100)}%'}",
               size=10.5, weight="Medium", fill=(CORAL["bold"] if ttl_frac <= 0 else SUB), anchor="mm")
        c.icon_db(db[0] + db[2] / 2, db[1] + db[3] / 2, 90, GRAY["bold"])
        c.text(db[0] + db[2] / 2, db[1] + db[3] + 22, "database", size=11, weight="Medium", fill=SUB, anchor="mm")
        for cx, cy in clients:
            c.dot(cx, cy, 6, fill=SKY["bold"])

    # SCENE 1 — steady traffic hits the cache while TTL counts down
    for t in eseq(40):
        c = Canvas(style="playful")
        ttl = 1.0 - t
        base(c, ttl)
        for cx, cy in clients:
            c.dashed(cx, cy, cache[0] + cache[2] / 2, cache[1] + cache[3] / 2, fill=HAIR, dash=6, gap=5)
        c.footer("Every request hits the cache — the database stays quiet.", TANG, step=0, total=3)
        frames.append(c.img)

    # SCENE 2 — TTL hits zero: everyone falls through to the DB at once
    for t in eseq(40):
        c = Canvas(style="playful")
        base(c, 0)
        for cx, cy in clients:
            px, py = seg_point([((cx, cy), (db[0] + db[2] / 2, db[1] + db[3] / 2))], min(1.0, t * 1.3))
            c.glow(px, py, CORAL["bold"])
        overload = ease(t)
        c.card(db[0] - 10, db[1] - 10, db[2] + 20, db[3] + 20, fill=None, line=mix(HAIR, CORAL["bold"], overload), width=3, r=14, shadow=False)
        c.footer("The herd: six requests, six identical cache misses, one overloaded database.", CORAL, step=1, total=3)
        frames.append(c.img)

    # SCENE 3 — replay with sync=true: one leader, the rest wait
    for t in eseq(40):
        c = Canvas(style="playful")
        base(c, 0, title="Fixed with @Cacheable(sync = true)")
        leader = clients[0]
        px, py = seg_point([((leader[0], leader[1]), (db[0] + db[2] / 2, db[1] + db[3] / 2))], min(1.0, t * 1.4))
        c.glow(px, py, MINT["bold"])
        for cx, cy in clients[1:]:
            c.dot(cx, cy, 6, fill=GRAY["bold"])
            if t > 0.4:
                c.text(cx, cy + 18, "waiting…", size=9.5, weight="Medium", fill=FAINT, anchor="mm")
        if t > 0.75:
            c.text(db[0] + db[2] / 2, db[1] - 22, "one query", size=11, weight="Semibold", fill=MINT["bold"], anchor="mm")
        c.footer("sync=true lets one caller refill the entry while the rest queue for the same result.", MINT, step=2, total=3)
        frames.append(c.img)

    save_gif(frames, out("cache-stampede.gif"), frame_ms=60)


# ---------------------------------------------------------------------------
# 10 — Dual-write problem vs. the transactional outbox
# ---------------------------------------------------------------------------
def build_outbox():
    frames = []
    svc = (130, 260, 200, 90)
    dbA = (450, 160, 200, 90)
    kafkaA = (450, 380, 200, 90)
    dbB = (450, 160, 200, 90)
    outboxB = (450, 380, 200, 90)
    kafkaB = (760, 270, 200, 90)

    def wrong_base(c):
        c.header("10", "Dual write: a crash between two commits", CORAL)
        c.card(*svc, fill=SKY["soft"], line=SKY["bold"], r=10)
        c.text(svc[0] + svc[2] / 2, svc[1] + svc[3] / 2, "OrderService", size=13, weight="Semibold", fill=SKY["ink"], anchor="mm")
        c.card(*dbA, fill=GRAY["soft"], line=GRAY["bold"], r=10)
        c.text(dbA[0] + dbA[2] / 2, dbA[1] + dbA[3] / 2, "Postgres: order row", size=12, weight="Semibold", fill=INK, anchor="mm")
        c.card(*kafkaA, fill=GRAY["soft"], line=GRAY["bold"], r=10)
        c.text(kafkaA[0] + kafkaA[2] / 2, kafkaA[1] + kafkaA[3] / 2, "Kafka: OrderPlaced", size=12, weight="Semibold", fill=INK, anchor="mm")

    # SCENE 1 — DB commit succeeds, crash before Kafka publish
    seg1 = [((svc[0] + svc[2], svc[1] + svc[3] / 2), (dbA[0], dbA[1] + dbA[3] / 2))]
    seg2 = [((svc[0] + svc[2], svc[1] + svc[3] / 2), (kafkaA[0], kafkaA[1] + kafkaA[3] / 2))]
    for t in eseq(50):
        c = Canvas(style="playful"); wrong_base(c)
        p1 = min(1.0, t * 1.6)
        c.glow(*seg_point(seg1, p1), MINT["bold"])
        if p1 >= 1.0:
            c.card(*dbA, fill=MINT["soft"], line=MINT["bold"], r=10)
            c.text(dbA[0] + dbA[2] / 2, dbA[1] + dbA[3] / 2, "Postgres: order row ✓", size=12, weight="Semibold", fill=MINT["ink"], anchor="mm")
        p2 = max(0.0, min(1.0, t * 1.6 - 1.0))
        if p2 > 0:
            c.glow(*seg_point(seg2, min(p2, 0.55)), CORAL["bold"])
        if t > 0.85:
            c.text(600, 300, "✗ CRASH", size=20, weight="Heavy", fill=CORAL["bold"], anchor="mm")
        c.footer("The DB commit lands. The process dies before the Kafka publish goes out.", CORAL, step=0, total=2)
        frames.append(c.img)

    # SCENE 2 — outbox: one local transaction writes both rows atomically, then a relay ships it
    tx = (dbB[0] - 24, dbB[1] - 24, 248, (outboxB[1] + outboxB[3]) - dbB[1] + 48)
    for t in eseq(50):
        c = Canvas(style="playful")
        c.header("10", "Fixed: the transactional outbox", MINT)
        c.card(*svc, fill=SKY["soft"], line=SKY["bold"], r=10)
        c.text(svc[0] + svc[2] / 2, svc[1] + svc[3] / 2, "OrderService", size=13, weight="Semibold", fill=SKY["ink"], anchor="mm")
        lit = mix(HAIR, MINT["bold"], min(1.0, t * 2))
        c.card(*tx, fill=None, line=lit, width=3, r=16, shadow=False)
        c.text(tx[0] + 14, tx[1] - 10, "ONE transaction", size=11, weight="Semibold", fill=MINT["bold"], anchor="lm")
        c.card(*dbB, fill=MINT["soft"] if t > 0.15 else GRAY["soft"], line=MINT["bold"], r=10)
        c.text(dbB[0] + dbB[2] / 2, dbB[1] + dbB[3] / 2, "order row", size=12, weight="Semibold", fill=MINT["ink"], anchor="mm")
        c.card(*outboxB, fill=MINT["soft"] if t > 0.15 else GRAY["soft"], line=MINT["bold"], r=10)
        c.text(outboxB[0] + outboxB[2] / 2, outboxB[1] + outboxB[3] / 2, "outbox row", size=12, weight="Semibold", fill=MINT["ink"], anchor="mm")
        c.card(*kafkaB, fill=MINT["soft"] if t > 0.7 else GRAY["soft"], line=MINT["bold"] if t > 0.7 else GRAY["bold"], r=10)
        c.text(kafkaB[0] + kafkaB[2] / 2, kafkaB[1] + kafkaB[3] / 2, "Kafka: OrderPlaced", size=12, weight="Semibold", fill=(MINT["ink"] if t > 0.7 else INK), anchor="mm")
        if t > 0.55:
            relay_t = min(1.0, (t - 0.55) / 0.35)
            px, py = seg_point([((outboxB[0] + outboxB[2], outboxB[1] + outboxB[3] / 2), (kafkaB[0], kafkaB[1] + kafkaB[3] / 2))], relay_t)
            c.glow(px, py, TANG["bold"])
            c.tag(outboxB[0] + outboxB[2] + 10, outboxB[1] + outboxB[3] / 2 - 26, "relay polls outbox")
        c.footer("Both rows commit atomically; a relay ships the outbox row afterward, at least once.", MINT, step=1, total=2)
        frames.append(c.img)

    save_gif(frames, out("transactional-outbox.gif"), frame_ms=68)


# ---------------------------------------------------------------------------
# 11 — Test-context caching: matching config reuses one context
# ---------------------------------------------------------------------------
def build_context_cache():
    frames = []
    tests = [("Test A", "ctx: {web=MOCK,\nprofiles=[test]}", 1), ("Test B", "ctx: {web=MOCK,\nprofiles=[test]}", 1),
              ("Test C", "ctx: {web=RANDOM_PORT}", 2), ("Test D", "ctx: {web=MOCK} +\n@DirtiesContext", 1)]
    tx = [150, 400, 650, 900]
    ty = 150

    def base(c):
        c.header("11", "The test-context cache", GRAPE)
        for i, (name, fp, _) in enumerate(tests):
            c.card(tx[i] - 90, ty, 180, 90, fill=SKY["soft"], line=SKY["bold"], r=10)
            c.text(tx[i], ty + 24, name, size=13, weight="Semibold", fill=SKY["ink"], anchor="mm")
            c.text(tx[i], ty + 58, fp, size=9.5, weight="Regular", fill=SUB, anchor="mm")
        c.card(300, 420, 500, 100, fill="#F3F5F8", line=HAIR, r=12, shadow=False)
        c.text(550, 400, "context cache", size=11, weight="Medium", fill=SUB, anchor="mm")

    ctx_slots = {}

    def draw_contexts(c, built, active_idx=None):
        slots_x = {1: 420, 2: 660}
        for cid, x in slots_x.items():
            if cid in built:
                fade = built[cid]
                fill = mix("#F3F5F8", MINT["soft"], fade)
                c.card(x - 80, 440, 160, 60, fill=fill, line=mix(HAIR, MINT["bold"], fade), r=10, shadow=False)
                c.text(x, 470, f"Context #{cid}", size=12, weight="Semibold", fill=mix(SUB, MINT["ink"], fade), anchor="mm")

    # SCENE 1 — A builds ctx 1 (spinner), B reuses it instantly, C builds ctx 2, D dirties its own
    built = {}
    for t in eseq(70):
        c = Canvas(style="playful"); base(c)
        # A: 0.0-0.3 build context 1
        if t < 0.3:
            built[1] = t / 0.3 * 0.6
            c.dashed(tx[0], ty + 90, 420, 440, fill=SKY["bold"], dash=6, gap=5)
        else:
            built[1] = 1.0
        draw_contexts(c, built)
        # B: 0.3-0.4 reuse instantly (green flash, no build)
        if 0.3 <= t < 0.5:
            c.dashed(tx[1], ty + 90, 420, 440, fill=MINT["bold"], dash=6, gap=5)
            c.text(tx[1], ty + 100, "reused ✓", size=10.5, weight="Bold", fill=MINT["bold"], anchor="mm")
        # C: 0.4-0.7 build context 2 (different fingerprint)
        if t >= 0.4:
            built[2] = min(1.0, (t - 0.4) / 0.3)
            if built[2] < 1.0:
                c.dashed(tx[2], ty + 90, 660, 440, fill=TANG["bold"], dash=6, gap=5)
        draw_contexts(c, built)
        # D: 0.7-1.0 uses ctx 1 then dirties it
        if t >= 0.7:
            c.dashed(tx[3], ty + 90, 420, 440, fill=SKY["bold"], dash=6, gap=5)
            crumble = (t - 0.7) / 0.3
            if crumble > 0.3:
                built[1] = max(0.15, 1.0 - crumble)
                c.text(tx[3], ty + 100, "…then @DirtiesContext discards it", size=9.5, weight="Medium", fill=CORAL["bold"], anchor="mm")
        draw_contexts(c, built)
        c.footer("Same fingerprint, same cached context — a difference (or @DirtiesContext) builds a new one.", GRAPE, step=0, total=2)
        frames.append(c.img)

    # SCENE 2 — count-up comparison: 2 contexts / fast suite vs 4 contexts / slow suite
    for t in eseq(46):
        c = Canvas(style="playful")
        c.header("11", "Why the same suite runs in 8s one day, 22s the next", GRAPE)
        good_n = tween(0, 2, t)
        bad_n = tween(0, 4, t)
        good_time = tween(0, 8, t)
        bad_time = tween(0, 22, t)
        c.card(200, 220, 280, 200, fill=MINT["soft"], line=MINT["bold"], r=14)
        c.text(340, 260, "standardized config", size=12, weight="Semibold", fill=MINT["ink"], anchor="mm")
        c.text(340, 320, f"{int(round(good_n))} contexts built", size=16, weight="Bold", fill=MINT["bold"], anchor="mm")
        c.text(340, 360, f"{good_time:.0f}s suite", size=20, weight="Heavy", fill=MINT["bold"], anchor="mm")
        c.card(560, 220, 280, 200, fill=CORAL["soft"], line=CORAL["bold"], r=14)
        c.text(700, 260, "config drift + @DirtiesContext", size=12, weight="Semibold", fill=CORAL["ink"], anchor="mm")
        c.text(700, 320, f"{int(round(bad_n))} contexts built", size=16, weight="Bold", fill=CORAL["bold"], anchor="mm")
        c.text(700, 360, f"{bad_time:.0f}s suite", size=20, weight="Heavy", fill=CORAL["bold"], anchor="mm")
        c.footer("Every new context is a full Spring Boot startup — treat config as a shared resource.", GRAPE, step=1, total=2)
        frames.append(c.img)

    save_gif(frames, out("test-context-cache.gif"), frame_ms=68)


# ---------------------------------------------------------------------------
# 13 — Circuit breaker: closed -> open -> half-open
# ---------------------------------------------------------------------------
def build_circuit_breaker():
    frames = []
    nodes = {"CLOSED": (220, 320), "OPEN": (520, 150), "HALF-OPEN": (820, 320)}
    dep = (520, 480)

    def base(c, active, fail_frac=0.0):
        c.header("13", "Circuit breaker: closed → open → half-open", INDIGO)
        for name, (x, y) in nodes.items():
            on = (name == active)
            fill = mix("#FFFFFF", INDIGO["soft"], 1.0) if on else "#FFFFFF"
            line = INDIGO["bold"] if on else HAIR
            c.circle(x, y, 62, fill=fill, line=line, width=3)
            c.text(x, y, name, size=13, weight="Bold", fill=(INDIGO["ink"] if on else FAINT), anchor="mm")
        c.arrow(nodes["CLOSED"][0] + 55, nodes["CLOSED"][1] - 40, nodes["OPEN"][0] - 55, nodes["OPEN"][1] + 30, fill=HAIR)
        c.arrow(nodes["OPEN"][0] + 55, nodes["OPEN"][1] + 30, nodes["HALF-OPEN"][0] - 55, nodes["HALF-OPEN"][1] - 40, fill=HAIR)
        c.arrow(nodes["HALF-OPEN"][0] - 20, nodes["HALF-OPEN"][1] + 55, nodes["CLOSED"][0] + 20, nodes["CLOSED"][1] + 55, fill=HAIR)
        c.icon_db(dep[0], dep[1], 90, GRAY["bold"])
        c.text(dep[0], dep[1] + 56, "downstream dependency", size=10.5, weight="Medium", fill=SUB, anchor="mm")
        if fail_frac > 0:
            c.card(nodes["CLOSED"][0] - 70, nodes["CLOSED"][1] + 90, 140, 14, fill="#FFFFFF", line=HAIR, r=7, shadow=False)
            c.card(nodes["CLOSED"][0] - 70, nodes["CLOSED"][1] + 90, 140 * min(1, fail_frac), 14, fill=CORAL["bold"], line=None, r=7, shadow=False)
            c.text(nodes["CLOSED"][0], nodes["CLOSED"][1] + 118, "failure rate", size=9.5, weight="Medium", fill=SUB, anchor="mm")

    # SCENE 1 — CLOSED: healthy calls flow through
    for t in eseq(34):
        c = Canvas(style="playful"); base(c, "CLOSED")
        px, py = seg_point([((nodes["CLOSED"][0], nodes["CLOSED"][1] + 62), (dep[0] - 60, dep[1] - 30))], t)
        c.glow(px, py, MINT["bold"])
        c.footer("Closed: calls pass through; failures are just being counted.", MINT, step=0, total=3)
        frames.append(c.img)

    # SCENE 2 — failures climb past threshold -> trips OPEN, calls now rejected instantly
    for t in eseq(40):
        c = Canvas(style="playful"); base(c, "CLOSED" if t < 0.7 else "OPEN", fail_frac=min(1.0, t * 1.3))
        if t >= 0.7:
            c.text(nodes["OPEN"][0], nodes["OPEN"][1] - 90, "fallback()", size=12, weight="Semibold", fill=CORAL["bold"], anchor="mm")
        c.footer("Past the failure threshold, the breaker trips OPEN — calls fail fast, no network round-trip.", CORAL, step=1, total=3)
        frames.append(c.img)

    # SCENE 3 — wait duration elapses -> HALF-OPEN trial calls -> success closes the loop
    for t in eseq(46):
        c = Canvas(style="playful")
        active = "OPEN" if t < 0.35 else "HALF-OPEN"
        base(c, active)
        if t >= 0.35:
            trial_t = min(1.0, (t - 0.35) / 0.35)
            px, py = seg_point([((nodes["HALF-OPEN"][0], nodes["HALF-OPEN"][1] + 62), (dep[0] + 60, dep[1] - 20))], trial_t)
            c.glow(px, py, TANG["bold"])
        if t >= 0.75:
            c.text((nodes["HALF-OPEN"][0] + nodes["CLOSED"][0]) / 2, nodes["CLOSED"][1] + 80, "✓ recovered", size=12, weight="Bold", fill=MINT["bold"], anchor="mm")
        c.footer("Half-open lets a few trial calls through; success closes the loop, failure reopens it.", INDIGO, step=2, total=3)
        frames.append(c.img)

    save_gif(frames, out("circuit-breaker.gif"), frame_ms=65)


# ---------------------------------------------------------------------------
# 15 — Layered Docker images: only the changed layer re-pushes
# ---------------------------------------------------------------------------
def build_layers():
    frames = []
    wrong_layer = (150, 220, 260, 120)
    right_layers = [
        (620, 160, 260, 56, "deps: 280MB", GRAY),
        (620, 222, 260, 56, "spring-boot-loader", GRAY),
        (620, 284, 260, 56, "snapshot-deps", GRAY),
        (620, 346, 260, 56, "application: 200KB", TANG),
    ]

    def base(c):
        c.header("15", "Layer by volatility, not one fat COPY", TANG)
        c.tag(wrong_layer[0] + 40, wrong_layer[1] - 22, "WRONG — one COPY app.jar")
        c.tag(right_layers[0][0] + 40, right_layers[0][1] - 22, "RIGHT — spring-boot:layertools")

    # SCENE 1 — a one-line code edit triggers a rebuild in both images
    for t in eseq(50):
        c = Canvas(style="playful"); base(c)
        pulse = mix(HAIR, CORAL["bold"], min(1.0, t * 2))
        c.card(*wrong_layer, fill=mix(GRAY["soft"], CORAL["soft"], min(1.0, t * 1.6)), line=pulse, r=12)
        c.text(wrong_layer[0] + wrong_layer[2] / 2, wrong_layer[1] + wrong_layer[3] / 2, "app.jar — 300MB", size=13, weight="Semibold", fill=INK, anchor="mm")
        for i, (x, y, w, h, label, pal) in enumerate(right_layers):
            is_top = (i == 3)
            fill = mix(pal["soft"], CORAL["soft"], min(1.0, t * 1.6)) if is_top else pal["soft"]
            line = mix(pal["bold"], CORAL["bold"], min(1.0, t * 1.6)) if is_top else HAIR
            c.card(x, y, w, h, fill=fill, line=line, r=8, shadow=False)
            c.text(x + w / 2, y + h / 2, label, size=11.5, weight="Semibold", fill=INK, anchor="mm")
        if t > 0.5:
            c.text(wrong_layer[0] + wrong_layer[2] / 2, wrong_layer[1] - 40, "✎ one-line code change", size=11, weight="Medium", fill=SUB, anchor="mm")
        c.footer("The same edit hits both images — watch what each one has to re-push.", TANG, step=0, total=2)
        frames.append(c.img)

    # SCENE 2 — upload counters: 300MB slow vs 200KB fast
    for t in eseq(50):
        c = Canvas(style="playful"); base(c)
        c.card(*wrong_layer, fill=CORAL["soft"], line=CORAL["bold"], r=12)
        c.text(wrong_layer[0] + wrong_layer[2] / 2, wrong_layer[1] + 34, "app.jar", size=13, weight="Semibold", fill=CORAL["ink"], anchor="mm")
        wrong_mb = tween(0, 300, min(1.0, t))
        c.text(wrong_layer[0] + wrong_layer[2] / 2, wrong_layer[1] + 78, f"{wrong_mb:.0f} MB pushed", size=15, weight="Bold", fill=CORAL["bold"], anchor="mm")
        for i, (x, y, w, h, label, pal) in enumerate(right_layers):
            is_top = (i == 3)
            fill = MINT["soft"] if is_top else pal["soft"]
            line = MINT["bold"] if is_top else HAIR
            c.card(x, y, w, h, fill=fill, line=line, r=8, shadow=False)
            txt = label if not is_top else f"application — {tween(0, 200, min(1.0, t * 3)):.0f}KB pushed"
            c.text(x + w / 2, y + h / 2, txt, size=11, weight="Semibold", fill=(MINT["ink"] if is_top else FAINT), anchor="mm")
            if not is_top:
                c.text(x + w + 14, y + h / 2, "cached", size=9.5, weight="Medium", fill=FAINT, anchor="lm")
        c.footer("300MB re-pushed vs. 200KB — the dependency layers never move again.", MINT, step=1, total=2)
        frames.append(c.img)

    save_gif(frames, out("docker-layers.gif"), frame_ms=65)


BUILDERS = {
    "autoconfig": build_autoconfig,
    "ioc": build_ioc,
    "request": build_request,
    "nplus1": build_nplus1,
    "security": build_security,
    "observ": build_observ,
    "startup": build_startup,
    "config": build_config,
    "dto": build_dto,
    "rollback": build_rollback,
    "stampede": build_cache_stampede,
    "outbox": build_outbox,
    "contextcache": build_context_cache,
    "circuitbreaker": build_circuit_breaker,
    "layers": build_layers,
}

if __name__ == "__main__":
    keys = sys.argv[1:] or list(BUILDERS)
    for k in keys:
        if k not in BUILDERS:
            print(f"unknown figure: {k}; options: {', '.join(BUILDERS)}"); continue
        print(f"building {k} ...")
        BUILDERS[k]()
    print("done.")
