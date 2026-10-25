"""Ordered Jellyfin playback reports. Network I/O runs on a serial background worker."""
from concurrent.futures import ThreadPoolExecutor


class PlaybackReports:
    def __init__(self, client, item_id, source_id, session_id, on_error, on_refresh):
        self.client = client
        self.identity = {'ItemId': item_id, 'MediaSourceId': source_id, 'PlaySessionId': session_id}
        self.on_error, self.on_refresh = on_error, on_refresh
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.started = False
        self.stopped = False
        self.pending = None

    def send(self, endpoint, state, refresh=False):
        payload = dict(self.identity, **state)
        def work():
            try:
                self.client.request(endpoint, body=payload)
                if refresh:
                    self.on_refresh(self.client.detail(self.identity['ItemId']))
            except Exception as exc:
                self.on_error(str(exc))
        self.pending = self.executor.submit(work)

    def start(self, state):
        if not self.started and not self.stopped:
            self.started = True
            self.send('Sessions/Playing', state)

    def progress(self, state):
        if self.started and not self.stopped and (self.pending is None or self.pending.done()):
            self.send('Sessions/Playing/Progress', state)

    def stop(self, state, failed=False):
        if self.stopped:
            return
        self.stopped = True
        if self.started:
            self.send('Sessions/Playing/Stopped', {'PositionTicks': state['PositionTicks'], 'Failed': failed}, refresh=True)
        self.executor.shutdown(wait=False)
