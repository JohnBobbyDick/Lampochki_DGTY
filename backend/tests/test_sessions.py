import threading
import uuid

import pytest
from fastapi.testclient import TestClient

import state
from main import app

JAVA = "public class Alpha { public static int f(int x) { if (x > 0) { return 1; } return 2; } }"
PY = "def g(x):\n    if x:\n        return 1\n    return 2\n"


@pytest.fixture(autouse=True)
def fresh_store(monkeypatch):
    store = state.SessionStore()
    monkeypatch.setattr(state, "STORE", store)
    monkeypatch.setattr(state, "_current", state.contextvars.ContextVar("jb_session_t", default=state._Ctx(store.default)))


def _hdr(sid):
    return {"X-Session-Id": sid}


def _graph(c, sid=None):
    r = c.get("/api/graph", params={"type": "class"}, headers=_hdr(sid) if sid else {})
    return r


def test_two_sessions_are_isolated():
    c = TestClient(app)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    assert c.post("/api/parse", json={"code": JAVA}, headers=_hdr(a)).status_code == 200
    assert c.post("/api/parse", json={"code": PY, "language": "python"}, headers=_hdr(b)).status_code == 200
    ga = c.get("/api/graph", params={"type": "cfg", "method": "Alpha.f"}, headers=_hdr(a))
    gb = c.get("/api/graph", params={"type": "cfg", "method": "Module.g"}, headers=_hdr(b))
    assert ga.status_code == 200 and gb.status_code == 200
    assert ga.json() != gb.json()
    assert "Alpha" in str(_graph(c, a).json()) and "Alpha" not in str(_graph(c, b).json())


def test_new_session_has_no_code():
    c = TestClient(app)
    r = c.get("/api/graph", params={"type": "cfg"}, headers=_hdr(str(uuid.uuid4())))
    assert r.status_code == 409


def test_no_header_uses_default_session():
    c = TestClient(app)
    assert c.post("/api/parse", json={"code": JAVA}).status_code == 200
    assert c.get("/api/graph", params={"type": "class"}).status_code == 200
    # a header-less request does not see a named session's code and vice versa
    assert c.get("/api/graph", params={"type": "class"}, headers=_hdr(str(uuid.uuid4()))).status_code == 409


@pytest.mark.parametrize("bad", ["abc", "123", "../../etc", "x" * 200])
def test_invalid_id_is_400(bad):
    c = TestClient(app)
    r = c.get("/api/health", headers=_hdr(bad))
    assert r.status_code == 400
    assert "X-Session-Id" in r.json()["detail"]


def test_lru_eviction():
    store = state.SessionStore(max_sessions=3, idle_seconds=3600)
    ids = [str(uuid.uuid4()) for _ in range(4)]
    objs = [store.get(i) for i in ids[:3]]
    store.get(ids[0])  # touch: ids[1] is now the oldest
    store.get(ids[3])
    assert len(store) == 3
    assert ids[1] not in store
    assert ids[0] in store and ids[3] in store
    assert store.get(ids[0]) is objs[0]


def test_idle_expiry():
    now = [1000.0]
    store = state.SessionStore(max_sessions=10, idle_seconds=3600, clock=lambda: now[0])
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    store.get(a)
    now[0] += 3000
    store.get(b)
    now[0] += 700  # a idle 3700 s, b 700 s
    store.get(str(uuid.uuid4()))
    assert a not in store and b in store


def test_default_session_never_evicted():
    now = [0.0]
    store = state.SessionStore(max_sessions=2, idle_seconds=10, clock=lambda: now[0])
    d = store.default
    d.code = "x"
    now[0] += 100
    for _ in range(5):
        store.get(str(uuid.uuid4()))
    assert store.default is d and d.code == "x"


def test_limit_constants():
    assert state.MAX_SESSIONS == 200 and state.IDLE_SECONDS == 3600


def test_store_thread_safe():
    store = state.SessionStore(max_sessions=20, idle_seconds=3600)
    errors = []

    def work():
        try:
            for _ in range(300):
                store.get(str(uuid.uuid4()))
        except Exception as e:  # pragma: no cover
            errors.append(e)

    ts = [threading.Thread(target=work) for _ in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert not errors and len(store) <= 20


def test_unknown_ids_on_reads_do_not_create_or_evict(monkeypatch):
    monkeypatch.setattr(state, "STORE", state.SessionStore(max_sessions=3))
    c = TestClient(app)
    mine = [str(uuid.uuid4()) for _ in range(3)]
    for sid in mine:
        assert c.post("/api/parse", json={"code": JAVA}, headers=_hdr(sid)).status_code == 200
    for _ in range(50):
        assert c.get("/api/graph", params={"type": "class"}, headers=_hdr(str(uuid.uuid4()))).status_code == 409
    assert len(state.STORE) == 3
    assert all(sid in state.STORE for sid in mine)
    assert c.get("/api/graph", params={"type": "class"}, headers=_hdr(mine[0])).status_code == 200


def test_per_ip_new_session_limit():
    c = TestClient(app)
    for _ in range(state.NEW_SESSIONS_PER_IP):
        assert c.post("/api/parse", json={"code": JAVA}, headers=_hdr(str(uuid.uuid4()))).status_code == 200
    r = c.post("/api/parse", json={"code": JAVA}, headers=_hdr(str(uuid.uuid4())))
    assert r.status_code == 429
    assert r.json()["detail"] == "Слишком много новых сессий, попробуйте позже"
    # an existing session keeps working
    sid = next(iter(state.STORE._items))
    assert c.post("/api/parse", json={"code": JAVA}, headers=_hdr(sid)).status_code == 200


def test_limit_window_expires():
    now = [0.0]
    store = state.SessionStore(clock=lambda: now[0])
    for _ in range(state.NEW_SESSIONS_PER_IP):
        store.register(str(uuid.uuid4()), state.Session(), ip="1.1.1.1")
    with pytest.raises(state.HTTPException):
        store.register(str(uuid.uuid4()), state.Session(), ip="1.1.1.1")
    store.register(str(uuid.uuid4()), state.Session(), ip="2.2.2.2")
    now[0] += state.NEW_SESSIONS_WINDOW + 1
    store.register(str(uuid.uuid4()), state.Session(), ip="1.1.1.1")


def test_forwarded_for_only_from_trusted_proxy():
    from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
    from fastapi import FastAPI, Request

    def build(trusted):
        a = FastAPI()

        @a.get("/ip")
        def ip(request: Request):
            return {"ip": request.client.host}

        return TestClient(ProxyHeadersMiddleware(a, trusted_hosts=trusted))

    h = {"X-Forwarded-For": "203.0.113.7"}
    assert build("testclient").get("/ip", headers=h).json() == {"ip": "203.0.113.7"}
    assert build("10.0.0.0/8").get("/ip", headers=h).json() == {"ip": "testclient"}
