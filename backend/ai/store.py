"""SQLite store: tasks, steps, audit log. Survives restarts; interrupted tasks are marked on startup."""
import sqlite3, threading, time


class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        with self.lock:
            self.db.executescript("""
            CREATE TABLE IF NOT EXISTS tasks(id INTEGER PRIMARY KEY, user TEXT NOT NULL, goal TEXT NOT NULL,
                status TEXT NOT NULL, result TEXT, created REAL, updated REAL);
            CREATE TABLE IF NOT EXISTS steps(id INTEGER PRIMARY KEY, task_id INTEGER NOT NULL, idx INTEGER NOT NULL,
                kind TEXT NOT NULL, content TEXT NOT NULL, ts REAL);
            CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, ts REAL, user TEXT, event TEXT, detail TEXT);
            """)
            self.db.commit()

    def _x(self, sql, args=()):
        with self.lock:
            cur = self.db.execute(sql, args)
            self.db.commit()
            return cur

    def create_task(self, user, goal):
        now = time.time()
        return self._x("INSERT INTO tasks(user,goal,status,created,updated) VALUES(?,?,?,?,?)",
                       (user, goal, "running", now, now)).lastrowid

    def set_status(self, tid, status, result=None):
        self._x("UPDATE tasks SET status=?, result=COALESCE(?,result), updated=? WHERE id=?",
                (status, result, time.time(), tid))

    def get_task(self, tid, user):
        """A user can only ever read their own tasks."""
        with self.lock:
            r = self.db.execute("SELECT * FROM tasks WHERE id=? AND user=?", (tid, user)).fetchone()
        return dict(r) if r else None

    def list_tasks(self, user, limit=50):
        with self.lock:
            rows = self.db.execute("SELECT * FROM tasks WHERE user=? ORDER BY id DESC LIMIT ?", (user, limit)).fetchall()
        return [dict(r) for r in rows]

    def add_step(self, tid, kind, content):
        with self.lock:
            n = self.db.execute("SELECT COUNT(*) FROM steps WHERE task_id=?", (tid,)).fetchone()[0]
            self.db.execute("INSERT INTO steps(task_id,idx,kind,content,ts) VALUES(?,?,?,?,?)",
                            (tid, n, kind, content[:20000], time.time()))
            self.db.commit()
        return n

    def steps(self, tid, after=-1):
        with self.lock:
            rows = self.db.execute("SELECT idx,kind,content,ts FROM steps WHERE task_id=? AND idx>? ORDER BY idx", (tid, after)).fetchall()
        return [dict(r) for r in rows]

    def audit(self, user, event, detail=""):
        self._x("INSERT INTO audit(ts,user,event,detail) VALUES(?,?,?,?)", (time.time(), user, event, str(detail)[:2000]))

    def recover_interrupted(self):
        """Called at startup: tasks left 'running' by a crash or restart cannot silently continue."""
        c = self._x("UPDATE tasks SET status='interrupted', updated=? WHERE status='running'", (time.time(),))
        return c.rowcount
