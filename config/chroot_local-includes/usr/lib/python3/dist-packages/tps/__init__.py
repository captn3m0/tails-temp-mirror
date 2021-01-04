import gettext
import gi
gi.require_version('UDisks', '2.0')
from gi.repository import UDisks

_ = gettext.gettext

# noinspection PyArgumentList
udisks = UDisks.Client.new_sync()  # type: UDisks.Client

DBUS_SERVICE_NAME = "org.boum.tails.PersistentStorage"
DBUS_ROOT_OBJECT_PATH = "/org/boum/tails/PersistentStorage"
DBUS_FEATURES_PATH = "/org/boum/tails/PersistentStorage/Features"
DBUS_JOBS_PATH = "/org/boum/tails/PersistentStorage/Jobs"
DBUS_SERVICE_INTERFACE = "org.boum.tails.PersistentStorage"
DBUS_FEATURE_INTERFACE = "org.boum.tails.PersistentStorage.Feature"
DBUS_JOB_INTERFACE = "org.boum.tails.PersistentStorage.Job"

PERSISTENT_STORAGE_MOUNT_POINT = "/live/persistence/TailsData_unlocked"
