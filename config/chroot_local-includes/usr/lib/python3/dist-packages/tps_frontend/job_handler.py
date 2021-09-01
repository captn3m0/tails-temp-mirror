from gi.repository import Gio, GLib, Gtk
import logging
from typing import TYPE_CHECKING, Dict, List

from tps_frontend import _, DBUS_SERVICE_NAME, DBUS_JOB_INTERFACE

if TYPE_CHECKING:
    from tps_frontend.window import Window

logger = logging.getLogger(__name__)

class JobHandler(Gio.DBusProxy):
    def __init__(self, window: "Window", bus: Gio.DBusConnection, job_path:
    str):
        self.window = window
        self.dialog = None
        self.cancellable = None

        # noinspection PyArgumentList
        super().__init__(
            connection=bus,
            flags=Gio.DBusProxyFlags.NONE,
            info=None,
            name=DBUS_SERVICE_NAME,
            object_path=job_path,
            interface_name=DBUS_JOB_INTERFACE,
            cancellable=None,
        )  # type: Gio.DBusProxy

        self.proxy.connect("g-properties-changed",
                           self.on_job_properties_changed)

    def on_job_properties_changed(self, proxy: Gio.DBusProxy,
                                  changed_properties: GLib.Variant,
                                  invalidated_properties: List[str]):
        logger.debug("changed job properties: %s", changed_properties)
        if "ConflictingApps" in changed_properties.keys():
            pids = changed_properties["ConflictingApps"]
            self.show_conflicting_apps_message(pids)

    def show_conflicting_apps_message(self, apps: Dict[str, List[int]]):
        msg = self.get_conflicting_apps_message(apps)

        self.dialog = Gtk.MessageDialog(self.window,
                                        Gtk.DialogFlags.MODAL | \
                                        Gtk.DialogFlags.DESTROY_WITH_PARENT,
                                        Gtk.MessageType.INFO,
                                        Gtk.ButtonsType.CANCEL,
                                        msg)
        result = self.dialog.run()  # type: Gtk.ResponseType
        if result == Gtk.ResponseType.CANCEL:
            self.dialog.destroy()
            self.cancellable.cancel()

    def get_conflicting_apps_message(self, apps: Dict[str, List[int]]):
        # We list each app with the conflicting PIDs. The app names are
        # already translated.
        app_reprs = list()
        for app in apps:
            pids_repr = " ".join(str(pid) for pid in apps[app])
            app_reprs.append(
                # Translators: Don't translate {app} and {pids}, they
                # are placeholders.
                _("{app} ({pids})").format(app=app, pids=pids_repr)
            )

        # Translators: Don't translate {applications}, it's a placeholder
        return _("Close {applications} to continue").format(
            applications=_(" and ").join(app_reprs)
        )
