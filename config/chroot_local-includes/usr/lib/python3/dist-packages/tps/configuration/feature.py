import abc
from gi.repository import GLib
from logging import getLogger
import os
from pathlib import Path
import psutil
import time
from typing import TYPE_CHECKING, Dict, List, Optional

from tps import executil
from tps import State, DBUS_FEATURE_INTERFACE, DBUS_FEATURES_PATH, \
    ON_ACTIVATED_HOOKS_DIR, ON_DEACTIVATED_HOOKS_DIR
from tps.configuration.mount import Mount, IsActiveException, \
    IsInactiveException, IncorrectOwnerException
from tps.dbus.errors import ActivationFailedError, \
    AlreadyActivatedError, NotActivatedError, \
    FailedPreconditionError, IncorrectOwnerError
from tps.dbus.object import DBusObject
from tps.job import ServiceUsingJobs

if TYPE_CHECKING:
    from tps.configuration.conflicting_app import ConflictingApp
    from tps.service import Service

logger = getLogger(__name__)


class ConflictingProcessesError(Exception):
    pass


class Feature(DBusObject, ServiceUsingJobs, metaclass=abc.ABCMeta):
    dbus_info = '''
    <node>
        <interface name='org.boum.tails.PersistentStorage.Feature'>
            <method name='Activate'/>
            <method name='Deactivate'/>
            <property name="Id" type="s" access="read"/>
            <property name="IsActive" type="b" access="read"/>
            <property name="Job" type="o" access="read"/>
        </interface>
    </node>
    '''

    @property
    def dbus_path(self):
        return os.path.join(DBUS_FEATURES_PATH, self.Id)

    def __init__(self, service: "Service"):
        logger.debug("Initializing feature %r", self.Id)
        super().__init__(connection=service.connection)
        self.service = service
        self._is_active = False

        self.refresh_is_active()

    # ----- Exported functions ----- #

    def Activate(self):
        # Check if we can activate the feature
        if self.service.state != State.UNLOCKED:
            msg = "Can't activate features when state is '%s'" % \
                  self.service.state.name
            return FailedPreconditionError(msg)

        # Check if feature is active
        is_active = self.refresh_is_active()
        if is_active:
            raise AlreadyActivatedError("Feature %r is already activated"
                                        % self.Id)

        # If there is still a job running, cancel it
        if self._job:
            self._job.Cancel()

        # Create a job for the activation. We do this to allow the user
        # to cancel the job. During activation / deactivation, we wait
        # until all conflicting processes were terminated. Sometimes it
        # might not be possible / desirable for the user to terminate
        # conflicting processes, so we want to support cancellation.
        #
        # The simpler alternative would be to raise an error if any
        # conflicting processes are running and let the user
        # re-trigger the activation / deactivation once they
        # terminated the conflicting processes. But that would provide
        # worse UX, because a conflicting process might take quite
        # some time to terminate after the user closed the
        # corresponding application window. They would have to keep
        # re-triggering the activation / deactivation until the process
        # terminated.
        try:
            with self.new_job() as job:
                self.do_activate(job)
        except IncorrectOwnerException as e:
            # Convert the internal exception into a D-Bus error
            raise IncorrectOwnerError(e) from e

    def Deactivate(self):
        # Check if we can deactivate the feature
        if self.service.state != State.UNLOCKED:
            msg = "Can't deactivate features when state is '%s'" % \
                  self.service.state.name
            return FailedPreconditionError(msg)

        # Check if feature is active
        is_active = self.refresh_is_active()
        if not is_active:
            raise NotActivatedError("Feature %r is not activated" % self.Id)

        # If there is still a job running, cancel it
        if self._job:
            self._job.Cancel()

        # Create a job for the deactivation. For rationale on why we
        # use a job here, see the comment in Activate().
        try:
            with self.new_job() as job:
                self.do_deactivate(job)
        except IncorrectOwnerException as e:
            # Convert the internal exception into a D-Bus error
            raise IncorrectOwnerError(e) from e

    # ----- Exported properties ----- #

    @property
    def IsActive(self) -> bool:
        return self._is_active

    @IsActive.setter
    def IsActive(self, value: bool):
        if self._is_active == value:
            # Nothing to do
            return
        self._is_active = value
        changed_properties = {"IsActive": GLib.Variant("b", value)}
        self.emit_properties_changed_signal(self.service.connection,
                                            DBUS_FEATURE_INTERFACE,
                                            changed_properties)
        if value:
            self.on_activated()
        else:
            self.on_deactivated()

    @property
    def Job(self) -> str:
        return self._job.dbus_path if self._job else "/"

    @Job.setter
    def Job(self, job: "Job"):
        self._job = job
        changed_properties = {"Job": GLib.Variant("s", self.Job)}
        self.emit_properties_changed_signal(self.service.connection,
                                            DBUS_FEATURE_INTERFACE,
                                            changed_properties)

    @property
    @abc.abstractmethod
    def Id(self) -> str:
        """The name of the feature. It must only contain the ASCII
        characters "[A-Z][a-z][0-9]_"."""
        return str()

    @property
    @abc.abstractmethod
    def Mounts(self) -> List[Mount]:
        """A list of mounts, which are mappings of source directories
        to target paths. The source directories will be mounted to the
        target paths when the feature is activated."""
        return list()

    # ----- Non-exported properties ------ #

    @property
    def conflicting_apps(self) -> List["ConflictingApp"]:
        """A list of applications which must not be currently running
        when the feature is activated/deactivated."""
        return list()

    @property
    def enabled_by_default(self) -> bool:
        """Whether this feature should be enabled by default"""
        return False

    # ----- Non-exported functions ----- #

    def do_activate(self, job: Optional["Job"], non_blocking=False):
        logger.info(f"Activating feature {self.Id}")

        apps = self.get_running_conflicting_apps()
        if apps and non_blocking:
            # Note that we don't translate this error message because
            # it's not meant to be passed to the user, but only logged
            # for debugging purposes.
            raise ConflictingProcessesError(
                f"Can't activate feature {self.Id}: Conflicting "
                f"applications are running ({' '.join(apps)})")
        elif apps:
            # Wait for conflicting processes to terminate. If the job is
            # cancelled by the user before the conflicting processes
            # terminate, an exception will be thrown, which will be passed
            # on to the client and handled there.
            job.wait_for_apps_to_terminate(apps)

        for mount in self.Mounts:
            mount.activate()

        # Check if the directories were actually mounted
        try:
            for mount in self.Mounts: mount.check_is_active()
        except IsInactiveException as e:
            msg = f"Activation of feature '{self.Id}' failed unexpectedly"
            raise ActivationFailedError(msg) from e

        try:
            self.IsActive = True
        finally:
            self.service.save_config_file()

    def do_deactivate(self, job: Optional["Job"]):
        logger.info(f"Deactivating feature {self.Id}")

        # Wait for conflicting processes to terminate. If the job is
        # cancelled by the user before the conflicting processes
        # terminate, an exception will be thrown, which will be passed
        # on to the client and handled there.
        apps = self.get_running_conflicting_apps()
        if apps:
            job.wait_for_apps_to_terminate(apps)

        for mount in self.Mounts:
            mount.deactivate()

        # Check if the directories were actually unmounted
        try:
            for mount in self.Mounts: mount.check_is_inactive()
        except IsActiveException as e:
            msg = f"Deactivation of feature '{self.Id}' failed unexpectedly"
            raise ActivationFailedError(msg) from e

        try:
            self.IsActive = False
        finally:
            self.service.save_config_file()

    def on_activated(self):
        hooks_dir = Path(ON_ACTIVATED_HOOKS_DIR, self.Id)
        executil.execute_hooks(hooks_dir)

    def on_deactivated(self):
        hooks_dir = Path(ON_DEACTIVATED_HOOKS_DIR, self.Id)
        executil.execute_hooks(hooks_dir)

    def refresh_is_active(self) -> bool:
        print("XXX: service state: ", self.service.state)
        if self.service.state in (State.NOT_CREATED, State.NOT_UNLOCKED):
            return False

        config_file = self.service.config_file
        is_active = config_file.exists() and config_file.contains(self)
        self.IsActive = is_active
        return is_active

    def get_running_conflicting_apps(self) -> Dict[str, List[int]]:
        res = dict()
        for app in self.conflicting_apps:
            # Get the list of currently running processes which belong
            # to the app
            processes = app.get_processes()
            if not processes:
                continue
            name = app.try_get_translated_name()
            pids = [p.pid for p in processes]
            res[name] = pids
        return res
