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


BUILDERS = {
    "autoconfig": build_autoconfig,
    "ioc": build_ioc,
    "request": build_request,
    "nplus1": build_nplus1,
    "security": build_security,
    "observ": build_observ,
    "startup": build_startup,
}

if __name__ == "__main__":
    keys = sys.argv[1:] or list(BUILDERS)
    for k in keys:
        if k not in BUILDERS:
            print(f"unknown figure: {k}; options: {', '.join(BUILDERS)}"); continue
        print(f"building {k} ...")
        BUILDERS[k]()
    print("done.")
