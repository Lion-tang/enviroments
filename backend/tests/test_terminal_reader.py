from app.api.v1.routers import terminal


class FakeChannel:
    def __init__(self, outcome=b"", ready=True, closed=False, exit_ready=False):
        self.outcome = outcome
        self.ready = ready
        self.closed = closed
        self.exit_ready = exit_ready

    def recv_ready(self):
        return self.ready

    def exit_status_ready(self):
        return self.exit_ready

    def recv(self, _size):
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def test_channel_poll_distinguishes_idle_from_eof():
    idle = FakeChannel(ready=False)
    eof = FakeChannel(outcome=b"", ready=True)

    assert terminal._poll_channel(idle) is terminal.CHANNEL_IDLE
    assert terminal._poll_channel(eof) == b""


def test_channel_poll_marks_read_errors_as_closed():
    assert terminal._poll_channel(FakeChannel(OSError("closed"))) is None
