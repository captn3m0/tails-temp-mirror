from logging import getLogger
from gi.repository import Gtk
import subprocess

from tps_frontend import WELCOME_VIEW_UI_FILE
from tps_frontend.view import View

logger = getLogger(__name__)

class WelcomeView(View):
    _ui_file = WELCOME_VIEW_UI_FILE

    def __init__(self, window):
        super().__init__(window)
        self.continue_button = self.builder.get_object("continue_button")

    def show(self):
        super().show()
        self.continue_button.grab_focus()

    def on_cancel_button_clicked(self, button: Gtk.Button):
        self.window.destroy()

    @staticmethod
    def on_activate_link(label: Gtk.Label, uri: str):
        logger.debug("Opening documentation")
        subprocess.Popen(["xdg-open", uri])
        return True

    def on_continue_button_clicked(self, button: Gtk.Button):
        self.window.passphrase_view.show()
