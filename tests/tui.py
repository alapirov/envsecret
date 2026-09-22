"""Drives the real TUI through a pty against fake security/osascript/pbcopy.
No keychain, no clipboard. Run: python3 tests/tui.py (exit 1 on any failure)."""
import os, pty, sys, time, json, select, signal, fcntl, termios, struct
HERE=os.path.dirname(os.path.abspath(__file__))
import tempfile
TMP=tempfile.mkdtemp(prefix="envsecret-tui-")
ST=os.path.join(TMP,"store.json"); LOG=os.path.join(TMP,"calls.log")
BASE={"LONGKEY":{"label":"envsecret [growth] LONGKEY","acct":"u","value":"L"*988,"cdat":"20260901000000"},
      "BBB":{"label":"envsecret [flightr] BBB","acct":"u","value":"bbb-secret","cdat":"20260902000000"},
      "CCC":{"label":"envsecret [flight] CCC","acct":"u","value":"ccc","cdat":"20260903000000"}}
def reset():
    json.dump(BASE,open(ST,"w")); open(LOG,"w").close()
def store(): return json.load(open(ST))
def calls(): return open(LOG).read().splitlines()
def setsize(fd,r,c): fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH",r,c,0,0))
class TUI:
    def __init__(s, *args, env=None, rows=30, cols=100):
        e=dict(os.environ, FAKE_STORE=ST, FAKE_LOG=LOG, FAKE_HOME=TMP, TERM="xterm-256color", USER="u", **(env or {}))
        e.pop("ESCDELAY",None)
        s.pid, s.fd = pty.fork()
        if s.pid==0:
            os.execve(sys.executable,[sys.executable,os.path.join(HERE,"launch.py"),*args],e)
        setsize(s.fd,rows,cols); os.kill(s.pid, signal.SIGWINCH)
        s.buf=b""; s.read(0.6)
    def read(s,t=0.3):
        end=time.time()+t
        while time.time()<end:
            r,_,_=select.select([s.fd],[],[],0.05)
            if r:
                try: s.buf+=os.read(s.fd,65536)
                except OSError: break
        return s.buf
    def send(s,data,t=0.35):
        os.write(s.fd, data if isinstance(data,bytes) else data.encode()); return s.read(t)
    def seen(s,text): return text.encode() in s.buf
    def mark(s): s.buf=b""
    def wait_exit(s,t=3):
        end=time.time()+t
        while time.time()<end:
            s.read(0.1)
            p,st=os.waitpid(s.pid,os.WNOHANG)
            if p: return st
        os.kill(s.pid,9); os.waitpid(s.pid,0); return "killed"
PS,PE=b"\x1b[200~",b"\x1b[201~"
results=[]
def ok(c,m): results.append(c); print(("PASS " if c else "FAIL ")+m)

# 1 card hidden by default, concealed copy, quick quit leaves the clear timer in charge
reset(); t=TUI(); t.mark()
t.send("/"); t.send("BBB\r"); t.mark(); t.send("\r",0.5)
ok(t.seen("10 chars") and not t.seen("bbb-secret"), "card opens hidden")
t.send("r"); ok(t.seen("bbb-secret"), "r reveals"); t.send("\x1b",0.4); t.send("/"); t.send("\x15LONG\r"); t.send("\r",0.5)
t.mark(); t.send("c",0.5); ok(t.seen("hidden from clipboard history"), "copy message says concealed")
t.send("q"); t.send("q"); st=t.wait_exit()
c=calls(); ok("osa-copy len=988" in c and "osa-clear cc=7 after=45" in c and not any(x.startswith("pbcopy") for x in c), f"osascript copy + 45 s clear, no pbcopy wipe: {c}")

# 2 esc latency
reset(); t=TUI(); t.mark(); t0=time.time(); os.write(t.fd,b"\x1b")
while not t.seen("quit envsecret?") and time.time()-t0<2: t.read(0.01)
lat=time.time()-t0; ok(lat<0.3, f"esc -> quit prompt in {lat*1000:.0f} ms")
t.send("n"); t.send("q"); t.wait_exit()

# 3 group move of the 988-char item with an empty value keeps it whole
reset(); t=TUI(); t.send("/"); t.send("LONG\r"); t.send("e",0.5); t.send("\x15"); t.send("growth2"); t.send("\x13",0.8)
s=store(); ok(s["LONGKEY"]["value"]=="L"*988 and s["LONGKEY"]["label"]=="envsecret [growth2] LONGKEY", "move keeps 988 chars, label updated")
t.send("q"); t.wait_exit()

# 4 bracketed multi-line paste into value is refused, nothing runs
reset(); t=TUI(); t.send("a",0.5); t.send("grp\t"); t.send("NEWK\t"); t.mark()
t.send(PS+b"line1\nline2dy\nq"+PE,0.6)
ok(t.seen("line break or a tab"), "bracketed multi-line paste refused")
t.send("\x1b",0.4); t.send("q"); st=t.wait_exit()
c=calls(); s=store(); ok("NEWK" not in s and "BBB" in s and not any(x.startswith(("add","delete")) for x in c), f"no write, no delete: {c}")

# 5 unbracketed paste with a newline in the edit value field
reset(); t=TUI(); t.send("/"); t.send("BBB\r"); t.send("e",0.5); t.send("\t"); t.send("\t"); t.mark()
os.write(t.fd,b"newval\rdy"); t.read(0.6)
ok(t.seen("line break or a tab"), "raw paste with newline refused")
t.send("\x1b",0.4); t.send("q"); t.wait_exit()
s=store(); ok(s.get("BBB",{}).get("value")=="bbb-secret", "BBB untouched")

# 6 tab inside a raw paste does not spill into the group
reset(); t=TUI(); t.send("a",0.5); t.send("grp\t"); t.send("NEWK\t"); t.mark(); os.write(t.fd,b"ab\tcd"); t.read(0.5)
ok(t.seen("line break or a tab"), "raw paste with tab refused")
t.send("\x1b",0.4); t.send("q"); t.wait_exit(); ok("NEWK" not in store(), "nothing added")

# 7 group validation
reset(); t=TUI(); t.send("a",0.5); t.send("a]b\t"); t.send("XK\t"); t.send("val\r",0.6)
ok(t.seen("one lowercase word"), "group with ] refused"); t.send("\x1b",0.4); t.send("q"); t.wait_exit(); ok("XK" not in store(), "not written")

# 8 add of an existing name refused; uppercase group normalised
reset(); t=TUI(); t.send("a",0.5); t.send("Cloud\t"); t.send("new_one\t"); t.send("v1\r",0.8)
s=store(); ok(s.get("NEW_ONE",{}).get("label")=="envsecret [cloud] NEW_ONE", "group lowercased, name normalised")
t.send("a",0.5); t.send("x\t"); t.send("BBB\t"); t.send("v\r",0.6); ok(t.seen("already exists"), "existing name refused"); t.send("\x1b",0.4); t.send("q"); t.wait_exit()

# 9 failed dump: no add possible
reset(); t=TUI(env={"FAKE_DUMP_FAIL":"1"}); ok(t.seen("keychain not readable"), "title says keychain not readable")
t.send("a",0.6); ok(t.seen("nothing can be added"), "add refused"); t.send("q"); t.wait_exit()
ok(not any(x.startswith("add") for x in calls()), "no add call")

# 10 typed accent refused
reset(); t=TUI(); t.send("a",0.5); t.send("grp\t"); t.send("K\t"); t.mark(); t.send("p\xe4ss".encode(),0.4)
ok(t.seen("plain ASCII only"), "non-ASCII refused with a message"); t.send("\x1b",0.4); t.send("q"); t.wait_exit()

# 11 pbcopy fallback wiped on ctrl-c and on hangup
for how in ("ctrl-c","sighup"):
    reset(); t=TUI(env={"FAKE_OSA_FAIL":"1"}); t.send("/"); t.send("BBB\r"); t.send("\r",0.5); t.send("c",0.5)
    if how=="ctrl-c": t.send("\x03",0.5)
    else: os.kill(t.pid, signal.SIGHUP)
    t.wait_exit(); c=calls()
    ok("pbcopy len=10" in c and "pbcopy len=0" in c, f"fallback copy wiped on {how}: {c}")

# 12 resize to tiny inside card and inside form: no crash
reset(); t=TUI(); t.send("/"); t.send("BBB\r"); t.send("\r",0.5)
setsize(t.fd,6,12); os.kill(t.pid,signal.SIGWINCH); t.read(0.4); t.send("r",0.3)
setsize(t.fd,30,100); os.kill(t.pid,signal.SIGWINCH); t.send("\x1b",0.4)
t.send("a",0.5); t.send("grp")
setsize(t.fd,10,30); os.kill(t.pid,signal.SIGWINCH); t.mark(); t.read(0.4); t.send("x",0.3)
ok(t.seen("enlarge the terminal"), "form shows enlarge message when too small")
setsize(t.fd,30,100); os.kill(t.pid,signal.SIGWINCH); t.read(0.4); t.mark(); t.send("\x15",0.3)
t.send("\x1b",0.4); t.send("q"); st=t.wait_exit()
ok(st==0, f"no crash through resizes (exit status {st})")

# 13 filter paste becomes filter text, no forms
reset(); t=TUI(); t.send("/"); t.mark(); t.send(PS+b"flightr"+PE,0.4); t.send("\r",0.4)
ok(t.seen("filter: flightr"), "pasted filter text lands in the filter"); t.send("q"); t.wait_exit()
ok(not any(x.startswith(("add","delete")) for x in calls()), "no side effects")

# 14 paste on the list is ignored
reset(); t=TUI(); t.send(PS+b"dyq"+PE,0.5); t.send("q"); t.wait_exit(); ok("BBB" in store() and not any(x.startswith("delete") for x in calls()), "paste on list does nothing")

# 15 flash dismissed by next key
reset(); t=TUI(); t.send("/"); t.send("BBB\r"); t.send("\r",0.4); t0=time.time(); os.write(t.fd,b"c\x1b")
while not t.seen("secrets") and time.time()-t0<3: t.read(0.02)
ok(time.time()-t0<0.5, f"copy then esc back to list in {1000*(time.time()-t0):.0f} ms"); t.send("q"); t.wait_exit()

# 16 edit with no changes writes nothing
reset(); t=TUI(); t.send("/"); t.send("BBB\r"); t.send("e",0.5); t.send("\x13",0.5); ok(t.seen("no changes"), "no-op edit says no changes"); t.send("q"); t.wait_exit()
ok(not any(x.startswith("add") for x in calls()), "no rewrite")

# 17 rename
reset(); t=TUI(); t.send("/"); t.send("BBB\r"); t.send("e",0.5); t.send("\t"); t.send("\x15"); t.send("BBB2"); t.send("\x13",0.8); t.send("q"); t.wait_exit()
s=store(); ok("BBB" not in s and s.get("BBB2",{}).get("value")=="bbb-secret", "rename moves the value and removes the old item")
print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
