from logging import getLogger
from gi.repository import Gio, GLib, GObject, Gtk

import gi
gi.require_version('Handy', '1')
from gi.repository import Handy

Handy.init()

from tps.dbus.errors import IncorrectPassphraseError

from tps_frontend import _, WINDOW_UI_FILE
from tps_frontend.change_passphrase_dialog import ChangePassphraseDialog
from tps_frontend.views.creation_view import CreationView
from tps_frontend.views.deletion_view import DeletionView
from tps_frontend.views.fail_view import FailView
from tps_frontend.views.features_view import FeaturesView
from tps_frontend.views.passphrase_view import PassphraseView
from tps_frontend.views.welcome_view import WelcomeView

# Only required for type hints
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from tps_frontend.application import Application

logger = getLogger(__name__)

@Gtk.Template.from_file(WINDOW_UI_FILE)
class Window(Gtk.ApplicationWindow):

    __gtype_name__ = "Window"

    view_box = Gtk.Template.Child()  # type: Gtk.Box
    change_passphrase_button = Gtk.Template.Child()  # type: Gtk.Button
    delete_button = Gtk.Template.Child()  # type: Gtk.Button

    def __init__(self, app: "Application", bus: Gio.DBusConnection):
        """Initialize the main window"""
        super().__init__(application=app, title=_("Persistent Storage"))
        self.app = app
        self.service_proxy = self.app.service_proxy
        self.active_view = None

        # Initialize the fail view (we do this early because it's being
        # used by self.display_error())
        self.fail_view = FailView(self)

        # Initialize the views
        self.creation_view = CreationView(self, self.service_proxy)
        self.deletion_view = DeletionView(self)
        self.features_view = FeaturesView(self, bus)
        self.passphrase_view = PassphraseView(self)
        self.welcome_view = WelcomeView(self)

        # Subscribe to changes of the service name owner, so that we
        # notice when the service exits unexpectedly.
        self.service_proxy.connect("notify::g-name-owner",
                                   self.on_name_owner_changed)

        # Subscribe to changes of the service's properties, so that we
        # can react to the Persistent Storage being created or deleted.
        self.service_proxy.connect("g-properties-changed",
                                   self.on_properties_changed)

        name_owner = self.service_proxy.get_name_owner()
        variant = self.service_proxy.get_cached_property("IsCreated")
        created = variant and variant.get_boolean()

        if not name_owner:
            self.fail_view.show()
        elif not created:
            self.welcome_view.show()
        else:
            self.features_view.show()

    def on_name_owner_changed(self, proxy: Gio.DBusProxy,
                              pspec: GObject.ParamSpec):
        name_owner = proxy.get_name_owner()
        if not name_owner:
            self.on_service_vanished()
        if name_owner:
            self.on_service_appeared()

    def on_service_vanished(self):
        logger.warning("Persistent Storage D-Bus service vanished")
        self.fail_view.show()

    def on_service_appeared(self):
        logger.info("Persistent Storage D-Bus service appeared")
        if self.service_proxy.get_cached_property("IsCreated"):
            self.features_view.show()
        else:
            self.welcome_view.show()

    def on_properties_changed(self, proxy: Gio.DBusProxy,
                              changed_properties: GLib.Variant,
                              invalidated_properties: List[str]):
        if not "IsCreated" in changed_properties.keys():
            return

        if changed_properties["IsCreated"]:
            self.features_view.show()
        else:
            self.welcome_view.show()

    @Gtk.Template.Callback()
    def on_delete_button_clicked(self, button: Gtk.Button):
        dialog = Gtk.MessageDialog(self,
                                   Gtk.DialogFlags.DESTROY_WITH_PARENT,
                                   Gtk.MessageType.WARNING,
                                   Gtk.ButtonsType.NONE,
                                   _("Delete Persistent Storage?"))
        dialog.format_secondary_text(_("All data on your Persistent Storage "
                                       "will be permanently deleted."))
        dialog.add_button(_("_Cancel"), Gtk.ResponseType.CANCEL)
        dialog.add_button(_("_Delete Persistent Storage"), Gtk.ResponseType.OK)
        dialog.set_default_response(Gtk.ResponseType.CANCEL)
        button = dialog.get_widget_for_response(Gtk.ResponseType.OK)
        style_context = button.get_style_context()
        style_context.add_class("destructive-action")
        result = dialog.run()
        dialog.destroy()
        if result == Gtk.ResponseType.OK:
            self.deletion_view.show()
            self.service_proxy.call(
                method_name="Delete",
                parameters=None,
                flags=Gio.DBusCallFlags.NONE,
                timeout_msec=GLib.MAXINT,
                cancellable=None,
                callback=self.on_delete_call_finished,
            )

    @Gtk.Template.Callback()
    def on_change_passphrase_button_clicked(self, button: Gtk.Button):
        dialog = ChangePassphraseDialog(self, self.service_proxy)
        dialog.run()

    def on_create_call_finished(self, proxy: GObject.Object,
                                res: Gio.AsyncResult):
        try:
            proxy.call_finish(res)
        except GLib.Error as e:
            logger.error(f"failed to create Persistent Storage: {e.message}")
            self.display_error(_("Failed to create Persistent Storage"),
                               e.message)
            if self.active_view == self.creation_view:
                self.close()
            return

    def on_delete_call_finished(self, proxy: GObject.Object,
                                res: Gio.AsyncResult):
        try:
            proxy.call_finish(res)
        except GLib.Error as e:
            logger.error(f"failed to delete Persistent Storage: {e.message}")
            self.display_error(_("Error deleting Persistent Storage"),
                               e.message)
            if self.active_view == self.deletion_view:
                self.close()
            return

    def display_error(self, title: str, msg: str,
                      with_send_report_button: bool = None):
        if with_send_report_button is None:
            # Don't show the send report button if the failure view is the
            # active view, because we already show a send report button
            # there.
            with_send_report_button = self.active_view != self.fail_view
        self.app.display_error(title, msg, with_send_report_button)
