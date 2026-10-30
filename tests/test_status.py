from mina.popup import MinaWindows


class FakeRoot:
    def __init__(self):
        self.jobs = {}
        self.cancelled = []

    def after(self, delay, callback):
        job = f"after-{len(self.jobs) + 1}"
        self.jobs[job] = (delay, callback)
        return job

    def after_cancel(self, job):
        self.cancelled.append(job)
        self.jobs.pop(job, None)


class FakeCanvas:
    def __init__(self):
        self.items = {}

    def itemconfigure(self, item, **kwargs):
        self.items[item] = kwargs


class FakeRenderer:
    def render(self, text, size, color, max_width=None):
        return (text, size, color, max_width)


def make_status_window():
    window = object.__new__(MinaWindows)
    window.root = FakeRoot()
    window.config = {"ui": {"companion_size": [280, 84]}}
    window._text_renderer = FakeRenderer()
    window._companion_canvas = FakeCanvas()
    window._companion_status = 1
    window._status_clear_job = None
    return window


def test_transient_status_clears_after_short_delay():
    window = make_status_window()

    window.set_status("A temporary status", transient_ms=2500)

    job = window._status_clear_job
    assert window.root.jobs[job][0] == 2500
    window.root.jobs[job][1]()
    assert window._status == ""
    assert window._status_clear_job is None


def test_replacing_temporary_status_cancels_its_clear_timer():
    window = make_status_window()

    window.set_status("A temporary status", transient_ms=2500)
    old_job = window._status_clear_job
    window.set_status("Model load failed.", error=True)

    assert old_job in window.root.cancelled
    assert window._status == "Model load failed."
    assert window._status_clear_job is None


def test_transient_status_does_not_clear_newer_message():
    window = make_status_window()
    window.set_status("A temporary status", transient_ms=2500)
    old_job = window._status_clear_job
    window.set_status("Thinking…")

    window.root.jobs.get(old_job, (None, lambda: None))[1]()

    assert window._status == "Thinking…"
