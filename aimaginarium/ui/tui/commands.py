"""Command palette entries. Dev entries appear only to the dev role."""

from textual.command import DiscoveryHit, Hit, Hits, Provider

from ...api import Role


class DevCommands(Provider):
    """Out-of-character dev commands: undo the last turn, preview a roll, show or hide the dev dock or a stand-in party."""

    def _entries(self):
        app = self.app
        if getattr(getattr(app, "session", None), "role", None) is not Role.DEV:
            return []
        return [
            ("Undo last turn", "Take back the latest turn", app.action_undo),
            ("Preview a roll", "Open the roll window on a made-up check", app.action_preview_roll),
            ("Toggle dev panels", "Show or hide the dock", app.action_toggle_dock),
            ("Toggle stand-in party", "Show a made-up party of four on the party bar", app.action_toggle_demo_party),
        ]

    async def discover(self) -> Hits:
        for name, help_text, callback in self._entries():
            yield DiscoveryHit(name, callback, help=help_text)

    async def search(self, query: str) -> Hits:
        matcher = self.matcher(query)
        for name, help_text, callback in self._entries():
            score = matcher.match(name)
            if score > 0:
                yield Hit(score, matcher.highlight(name), callback, help=help_text)
