from gi.repository import Gio, GLib
from logging import getLogger
import os
import subprocess
import time
from typing import TYPE_CHECKING, List

from tps import executil
from tps.configuration import features
from tps.configuration.config_file import ConfigFile, InvalidStatError
from tps.configuration.feature import ConflictingProcessesError
from tps.dbus.object import DBusObject
from tps.device import udisks, BootDevice, Partition, InvalidBootDeviceError
from tps.job import ServiceUsingJobs
from tps.udisks_monitor import UDisksCreationMonitor
from tps import DBUS_ROOT_OBJECT_PATH, DBUS_SERVICE_INTERFACE, \
    PERSISTENT_STORAGE_MOUNT_POINT

if TYPE_CHECKING:
    from tps.configuration.feature import Feature
    from tps.job import Job

logger = getLogger(__name__)

ON_ACTIVATED_HOOKS_DIR="/usr/local/lib/persistent-storage/on-activated-hooks"

class AlreadyCreatedError(Exception):
    pass

class NotCreatedError(Exception):
    pass

class Service(DBusObject, ServiceUsingJobs):
    dbus_info = '''
        <node>
            <interface name='org.boum.tails.PersistentStorage'>
                <method name='Quit'/>
                <method name='Create'>
                    <arg name='passphrase' direction='in' type='s'/>
                </method>
                <method name='ChangePassphrase'>
                    <arg name='passphrase' direction='in' type='s'/>
                    <arg name='new_passphrase' direction='in' type='s'/>
                </method>
                <method name='Delete'/>
                <method name='Activate'/>
                <method name='Unlock'>
                    <arg name='passphrase' direction='in' type='s'/>
                </method>
                <property name="IsCreated" type="b" access="read"/>
                <property name="BootDeviceIsSupported" type="b" access="read"/>
                <property name="Device" type="s" access="read"/>
                <property name="Job" type="o" access="read"/>
            </interface>
        </node>
        '''

    dbus_path = DBUS_ROOT_OBJECT_PATH

    def __init__(self, connection: Gio.DBusConnection, loop: GLib.MainLoop):
        super().__init__(connection=connection)
        self.connection = connection
        self.mainloop = loop
        self.config_file = ConfigFile(PERSISTENT_STORAGE_MOUNT_POINT)
        self.bus_id = None
        self.features = list()  # type: List[Feature]

        # Check if the partition already exists
        partition = Partition.find()
        if partition:
            self._created = True
            self._device = partition.device_path
        else:
            self._created = False
            self._device = ""

        try:
            BootDevice.get_tails_boot_device()
            self._boot_device_is_supported = True
        except InvalidBootDeviceError:
            self._boot_device_is_supported = False

    # ----- Exported methods ----- #

    def Quit_method_call_handler(self, connection: Gio.DBusConnection,
                                 parameters: GLib.Variant,
                                 invocation: Gio.DBusMethodInvocation):
        """Terminate the Persistent Storage service"""
        # Make the D-Bus method return first, else our main thread
        # might exit before we can call return, resulting in a NoReply
        # error on the client.
        invocation.return_value(None)
        connection.flush_sync()
        logger.info("Quit() was called, terminating...")
        self.stop()

    def Create(self, passphrase: str):
        """Create the Persistent Storage partition and activate the
        default features"""
        if Partition.exists():
            raise AlreadyCreatedError(
                "The Persistent Storage was already created")

        boot_device = BootDevice.get_tails_boot_device()
        with self.new_job() as job:
            with UDisksCreationMonitor(job, boot_device):
                partition = Partition.create(job, passphrase)
        self.Device = partition.device_path

        self.refresh_is_created()

        # Activate all features that should be enabled by default
        for feature in self.features:
            if feature.enabled_by_default:
                try:
                    feature.do_activate(None, non_blocking=True)
                except ConflictingProcessesError as e:
                    # We can't automatically activate the feature, but
                    # lets not bother the user about that, because they
                    # did not explicitly enable the feature. If they try
                    # to enable it explicitly, they will see a message
                    # about the conflicting process.
                    logger.warning(e)

        self.run_on_activated_hooks()

    def Delete(self):
        """Delete the Persistent Storage partition"""

        # Check if we can delete the Persistent Storage
        partition = Partition.find()
        if not partition:
            raise NotCreatedError("No Persistent Storage found")

        # Delete the option
        partition.delete()

        # Refresh IsCreated
        self.refresh_is_created()

        # Refresh IsActive of all features
        for feature in self.features:
            feature.refresh_is_active()

    def Activate(self):
        """Activate all Persistent Storage features which are currently
        configured in the persistence.conf config file."""

        # Wait for all udev and UDisks events to finish
        executil.check_call(["/sbin/udevadm", "settle"])
        udisks.settle()

        partition = Partition.find()
        if not partition:
            raise NotCreatedError("No Persistent Storage found")

        cleartext_device = partition.get_cleartext_device()
        if not cleartext_device.is_mounted():
            cleartext_device.mount()

        # Check that the config file has secure ownership and
        # permissions. If not, disable the file and create an empty
        # file.
        try:
            self.config_file.check_file_stat()
        except InvalidStatError as e:
            logger.warning(f"Disabling invalid config file: {e}")
            self.config_file.disable_and_create_empty()
            self.run_on_activated_hooks()
            raise

        mounts = self.config_file.parse()
        for mount in mounts:
            mount.activate()

        self.run_on_activated_hooks()

    def Unlock(self, passphrase: str):
        """Unlock the Persistent Storage"""
        partition = Partition.find()
        if not partition:
            raise NotCreatedError("No Persistent Storage found")
        partition.unlock(passphrase)

    def ChangePassphrase(self, passphrase: str, new_passphrase: str):
        """Change the passphrase of the Persistent Storage encrypted
        partition"""
        partition = Partition.find()
        if not partition:
            raise NotCreatedError("No Persistent Storage found")

        partition.change_passphrase(passphrase, new_passphrase)

    # ----- Exported properties ----- #

    @property
    def IsCreated(self) -> bool:
        """Whether the Persistent Storage partition is created"""
        return self._created

    @IsCreated.setter
    def IsCreated(self, value: bool):
        if self._created == value:
            # Nothing to do
            return
        self._created = value
        changed_properties = {"IsCreated": GLib.Variant("b", value)}
        self.emit_properties_changed_signal(
            self.connection,
            DBUS_SERVICE_INTERFACE,
            changed_properties,
        )

    @property
    def BootDeviceIsSupported(self) -> bool:
        return self._boot_device_is_supported

    @property
    def Device(self) -> str:
        return self._device

    @Device.setter
    def Device(self, value: str):
        if self._device == value:
            # Nothing to do
            return
        self._device = value
        changed_properties = {"Device": GLib.Variant("s", value)}
        self.emit_properties_changed_signal(
            self.connection,
            DBUS_SERVICE_INTERFACE,
            changed_properties,
        )

    @property
    def Job(self) -> str:
        return self._job.dbus_path if self._job else "/"

    @Job.setter
    def Job(self, job: "Job"):
        self._job = job
        changed_properties = {"Job": GLib.Variant("s", self.Job)}
        self.emit_properties_changed_signal(
            self.connection,
            DBUS_SERVICE_INTERFACE,
            changed_properties,
        )

    # ----- Non-exported functions ----- #

    def start(self):
        """Start the Persistent Storage service"""
        try:
            self.register(self.connection)

            for FeatureClass in features.get_classes():
                feature = FeatureClass(self)
                feature.register(self.connection)
                self.features.append(feature)
            logger.debug("Done registering objects")
        except:
            self.stop()
            raise

    def stop(self):
        self.mainloop.quit()

    def settle(self):
        # Wait until all pending events on the main loop were handled
        context = self.mainloop.get_context()  # type: GLib.MainContext
        while context.iteration(may_block=False):
            logger.debug("Waiting for mainloop events to be handled")
            time.sleep(0.1)

    def save_config_file(self):
        """Save all currently active features to the config file"""
        active_features = [feature for feature in self.features
                           if feature.IsActive]
        self.config_file.save(active_features)

    def refresh_is_created(self) -> bool:
        """Refresh the IsCreated property, i.e. check if the
        Persistent Storage partition exists"""
        partition = Partition.find()
        if partition:
            self.IsCreated = True
            self.Device = partition.device_path
        else:
            self.IsCreated = False
            self.Device = ""
        return self.IsCreated

    @staticmethod
    def run_on_activated_hooks():
        for file in os.listdir(ON_ACTIVATED_HOOKS_DIR):
            subprocess.check_call(os.path.join(ON_ACTIVATED_HOOKS_DIR, file))
