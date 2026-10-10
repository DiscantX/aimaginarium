"""Command palette entries. Dev entries appear only to the dev role."""

from textual.command import DiscoveryHit, Hit, Hits, Provider

from ...api import Role


class DevCommands(Provider):
    """Out-of-character dev commands: undo the last turn, preview a roll, show or hide the dev dock or a stand-in party."""

    def _entries(self):
        app = self.app
        if getattr(getattr(app, "session", None), "role", None) is not Role.DEV:
            return []
        side = "bottom" if app.settings.dock_placement == "right" else "right"
        return [
            ("Undo last turn", "Take back the latest turn", app.action_undo),
            ("Preview a roll", "Open the roll window on a made-up check", app.action_preview_roll),
            ("Toggle dev panels", "Show or hide the dock", app.action_toggle_dock),
            (f"Move dev panels to the {side}", "Switch the dock between a column and a bottom panel", app.action_move_dock),
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


class PlayerCommands(Provider):
    """Out-of-character commands for every role: layout choices of the player panels."""

    def _entries(self):
        app = self.app
        side = "top" if app.settings.party_placement == "right" else "right"
        return [
            ("Toggle party bar", "Show or hide the party bar (F3)", app.action_toggle_party),
            ("Toggle character panel", "Show or hide the character panel (F5)", app.action_toggle_character),
            (f"Move party bar to the {side}", "Switch between a row under the header and a column", app.action_move_party),
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
