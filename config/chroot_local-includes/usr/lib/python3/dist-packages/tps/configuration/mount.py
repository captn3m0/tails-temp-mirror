import logging
import os
from pathlib import Path
import shlex
import subprocess
import sys
from typing import List, Union, Optional

from tps import _, PERSISTENT_STORAGE_MOUNT_POINT
from tps import executil
from tps.dbus.errors import TargetIsBusyError

logger = logging.getLogger(__name__)

AMNESIA_UID=1000

class FailedPrecondition(Exception):
    pass

class IncorrectOwnerException(Exception):
    pass

class InvalidMountError(Exception):
    pass

class IsActiveException(Exception):
    pass

class IsInactiveException(Exception):
    pass


class Mount(object):
    """A mapping of a source file or directory to a target file or
    directory. When a feature is activated, all of its mounts are
    mounted, i.e. for each mount the source file or directory is mounted
    to the target file or directory.

    By default, the source is mounted via a bind mount. If uses_symlinks
    is true, instead of using a bind mount, symlinks are created from
    the source file or, if the source is a directory, each file in the
    source directory, to the target file or directory. This corresponds
    to the "link" option of live-boot(5). Below is the description of
    that option from the live-boot(5) man page:

    Create the directory structure of the source directory on the persistence media in DIR
    and create symbolic links from the corresponding place in DIR  to  each  file  in  the
    source  directory.   Existing files or directories with the same name as any link will
    be overwritten. Note that deleting the links in DIR will only remove the link, not the
    corresponding  file  in  the  source;  removed  links will reappear after a reboot. To
    permanently add or delete a file one must do so directly in the source directory.

    Effectively link will make only files already in the source directory persistent,  not
    any  other files in DIR. These files must be manually added to the source directory to
    make use of this option, and they will appear in DIR  in  addition  to  files  already
    there.  This  option  is useful when only certain files need to be persistent, not the
    whole directory they're in, e.g. some configuration files in a user's home directory."""

    def __init__(self, src: Union[str, Path], dest: Union[str, Path],
                 is_file=False, uses_symlinks=False,
                 persistent_storage_mount_point: str = PERSISTENT_STORAGE_MOUNT_POINT):

        self.persistent_storage_mount_point = persistent_storage_mount_point

        # If the source is not an absolute path, we make it an absolute
        # path below the Persistent Storage mount point.
        if not Path(src).is_absolute():
            self.src = Path(self.persistent_storage_mount_point, src).resolve()
        else:
            self.src = Path(src).resolve()
        self.dest = Path(dest)
        self.is_file = is_file
        self.uses_symlinks = uses_symlinks
        try:
            self._relative_src = \
                self.src.relative_to(self.persistent_storage_mount_point)
        except ValueError:
            # XXX: Do we want to translate errors like this?
            raise InvalidMountError(f"Mount source {self.src} is outside of "
                                    f"the Persistent Storage mount point "
                                    f"{self.persistent_storage_mount_point}")

        # Check that the mount's source is below the Persistent Storage
        # mount point
        if Path(self.persistent_storage_mount_point) not in self.src.parents:
            raise InvalidMountError(f"Mount's source is outside of the "
                                    f"Persistent Storage mount point: {self}")

    def __str__(self):
        """The string representation of a mount. This is in the format
        of a persistence.conf line."""
        options = ','.join(shlex.quote(option) for option in self.options)
        return shlex.quote(str(self.dest)) + '\t' + options

    def __repr__(self):
        return "%s(%r)" % (self.__class__, self.__dict__)

    def __eq__(self, other: Union["Mount", str]):
        """Check if the mount is equal to another mount or the string
        representation of another mount"""

        # Ensure that the other object is a string
        other = str(other)

        # Remove leading and trailing whitespace
        other = other.strip()
        # Get the white-space separated elements of the other object
        elements = shlex.split(other, comments=True)

        if len(elements) != 2:
            # The other object has an invalid number of white-space
            # separated elements
            return False

        if elements[0] != str(self.dest):
            # The destination doesn't match
            return False

        options = set(elements[1].split(','))
        if options != set(self.options):
            # The options don't match
            return False

        return True

    def __hash__(self):
        return hash(str(self))

    @property
    def options(self) -> List[str]:
        options = [f"source={str(self._relative_src)}"]
        if self.uses_symlinks:
            options.append("link")
        return options

    def activate(self):
        try:
            self.check_is_inactive()
        except IsActiveException:
            # The mount is already active. It could be that two
            # different features have the same mount, which would
            # cause the mount to be activated again. To support that
            # case, we ignore the error here and just log a warning.
            logger.warning(f"Is already mounted: {self}")
            return

        # Check if anything else is mounted on the destination
        src = _what_is_mounted_on(self.dest)
        if src:
            raise FailedPrecondition(f"Path {src} is mounted on {self.dest}")

        # Create the mountpoint if it doesn't exist
        if not self.dest.exists():
            if self.is_file:
                self.dest.touch(mode=0o600)
            else:
                _create_dest_directory(self.dest)

        # Check that the mountpoint has the expected type (file or
        # directory)
        if self.is_file and not self.dest.is_file():
            raise FailedPrecondition(f"Destination {self.dest} exists but "
                                     f"is not a regular file")
        if not self.is_file and not self.dest.is_dir():
            raise FailedPrecondition(f"Destination {self.dest} exists but "
                                     f"is not a directory")

        if self.uses_symlinks:
            self._activate_using_symlinks()
        else:
            self._activate_using_bind_mount()

    def _activate_using_symlinks(self):
        if self.is_file:
            # Create the source file if it doesn't exist
            if not self.src.exists():
                self.src.touch(mode=0o700)
            # Create the symlink
            self._create_symlink(self.src, self.dest)
            return

        # Create the source directory if it doesn't exist
        if not self.src.exists():
            self.src.mkdir(mode=0o700, parents=True)
            # Set the same ownership and permissions of the destination
            # directory on the source directory
            _chown_ref(self.dest, self.src)
            _chmod_ref(self.dest, self.src)
            # The directory is empty, so there are no symlinks to create
            return

        # Create symlinks for all files in the directory
        for dir, subdirs, files in os.walk(self.src):
            dest_dir = os.path.join(self.dest, os.path.relpath(dir, self.src))
            for f in subdirs + files:
                src = Path(dir, f)
                dest = Path(dest_dir, f)
                self._create_symlink(src, dest)

    @staticmethod
    def _create_symlink(src: Path, dest: Path):
        # If the destination exists and is not owned by the same user
        # as the source, we *don't* want to change its owner and
        # permissions, else we would allow the owner of the source to
        # change arbitrary files on the filesystem. An exception is if
        # the source is owned by root, because then the user who created
        # it has root privileges anyway.
        if dest.exists():
            source_owner = os.stat(src).st_uid
            dest_owner = os.stat(dest).st_uid
            if source_owner != 0 and source_owner != dest_owner:
                # Translators: Don't translate {source} and
                # {destination}, they are placeholders.
                errmsg = _("The owner of {source} differs from the "
                           "owner of {destination}.").format(
                    source=str(src), destination=str(dest))
                raise IncorrectOwnerException(errmsg)

        if src.is_dir():
            # Create the destination directory if it doesn't exist
            dest.mkdir(mode=0o700, parents=True, exist_ok=True)
            # Make the destination have the same owner and permissions
            # as the source directory.
            _chown_ref(src, dest)
            _chmod_ref(src, dest)
        else:
            # Delete the destination file if it already exists
            if dest.exists():
                logger.info(f"Deleting file {dest} because it's in the way")
                dest.unlink()
            dest.symlink_to(src)
            # Make the symlink have the same owner as the source directory.
            _chown_ref(src, dest)

    def _activate_using_bind_mount(self):
        # If the source doesn't exist on the Persistent Storage, we
        # bootstrap it with the content of the destination, as it's done
        # by live-boot's activate_custom_mounts() function.
        if not self.src.exists():
            # Create the parent directory
            self.src.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            executil.check_call(["cp", "-a", self.dest, self.src])

        # Bind-mount the source to the destination
        executil.check_call(["mount", "--bind", self.src, self.dest])

    def deactivate(self):
        try:
            self.check_is_active()
        except IsInactiveException:
            # The mount is not inactive. It could be that two
            # different features have the same mount, which would
            # cause the mount to be deactivated again. To support that
            # case, we ignore the error here and just log a warning.
            logger.warning(f"Is not mounted: {self}")
            return

        if self.uses_symlinks:
            self._deactivate_using_symlinks()
        else:
            self._deactivate_using_bind_mount()

    def _deactivate_using_symlinks(self):
        # Remove symlinks
        for dir, subdirs, files in os.walk(self.src):
            dest_dir = os.path.join(self.dest, os.path.relpath(dir, self.src))
            for f in files:
                src = Path(dir, f)
                dest = Path(dest_dir, f)
                if not dest.is_symlink():
                    continue
                # Same as when creating symlinks, we don't remove files
                # from the destination if they are not owned by the
                # same user as the source.
                source_owner = os.stat(src).st_uid
                dest_owner = os.stat(dest).st_uid
                if source_owner != 0 and source_owner != dest_owner:
                    # Translators: Don't translate {source} and
                    # {destination}, they are placeholders.
                    errmsg = _("The owner of {source} differs from the "
                               "owner of {destination}.").format(
                        source=str(src), destination=str(dest))
                    raise IncorrectOwnerException(errmsg)
                dest.unlink()

    def _deactivate_using_bind_mount(self):
        # Unmount the destination directory
        try:
            executil.run(["umount", self.dest], check=True, text=True,
                         stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as e:
            # Print the subprocess stderr
            print(e.stderr, file=sys.stderr)
            if e.returncode == 32 and "target is busy" in e.stderr:
                # Translators: Don't translate {target}, it's a placeholder
                msg = _(
                    "Can't unmount target {target}, some process is still"
                    " using it. Please close all applications that could"
                    " be accessing the the target and try again."
                ).format(target=self.dest)
                raise TargetIsBusyError(msg) from e
            raise

    def check_is_active(self):
        """Check if the mount is active. Raise a IsInactiveException
        if the feature is inactive."""
        if self.uses_symlinks:
            if not any(files for _, _, files in os.walk(self.src)):
                # If the source directory doesn't contain files,
                # then we can't check if the feature is active.
                return
            if not self._is_active_using_symlinks():
                raise IsInactiveException()
        elif not self._is_active_using_bind_mount():
            raise IsInactiveException()

    def check_is_inactive(self):
        """Check if the mount is active. Raise a IsInactiveException
        if the feature is inactive."""
        if self.uses_symlinks:
            if not self.src.exists() or not any(files for _, _, files in
                                                os.walk(self.src)):
                # If the source directory doesn't exist, the feature
                # can't be active. If the source directory is empty,
                # then we can't check if the feature is active.
                return
            if self._is_active_using_symlinks():
                raise IsActiveException()
        elif self._is_active_using_bind_mount():
            raise IsActiveException()

    def _is_active_using_symlinks(self):
        for dir, _, files in os.walk(self.src):
            dest_dir = os.path.join(self.dest, os.path.relpath(dir, self.src))
            for f in files:
                src = Path(dir, f)
                dest = Path(dest_dir, f)
                if dest.resolve() != src:
                    logger.info(f"{dest.resolve()} != {src}")
                    return False
        return True

    def _is_active_using_bind_mount(self) -> bool:
        # First, get the Persistent Storage cleartext device path
        device = _what_is_mounted_on(self.persistent_storage_mount_point)
        if not device:
            # The Persistent Storage is not mounted, so this mount can
            # not be active
            return False

        # Check if the Persistent Storage cleartext device is already
        # mounted on the destination
        return _bind_mount_exists(self._relative_src, self.dest, device)


def _what_is_mounted_on(path: str) -> Optional[str]:
    try:
        output = executil.check_output(
            ["findmnt", "--noheadings", "--notruncate", "--canonicalize",
            f"--mountpoint={path}"],
        )
    except subprocess.CalledProcessError:
        # We assume that any non-zero exit code means that no mount was
        # found for the specified mountpoint.
        return None
    return output.split()[1]


def _bind_mount_exists(src: Union[str, Path], dest: Union[str, Path],
                       device: str) -> bool:
    with open("/proc/self/mountinfo") as f:
        lines = f.readlines()
    for line in lines:
        elements = line.split()
        if elements[9] != device:
            # The device doesn't match
            continue
        if elements[3] != "/" + str(src):
            # The source doesn't match
            continue
        if elements[4] != str(dest):
            # The destination doesn't match
            continue
        return True
    return False


def _create_dest_directory(path: Path):
    """Create the destination directory of a mount in the same way as
    it's done in live-boot's activate_custom_mounts() function, i.e.
    by deleting existing files that are in the way and by setting the
    owner to the UID of amnesia (live-boot sets it to 1000) on
    directories below /home"""
    logger.debug(f"Creating mount destination {path}")
    for p in sorted(path.parents) + [path]:
        if p.is_file():
            # Delete existing files that are in the way
            p.unlink()
        p.mkdir(mode=0o700, parents=True, exist_ok=True)
        if Path("/home/amnesia") in p.parents:
            logger.debug(f"Changing owner of mount destination {path} to "
                         f"UID {AMNESIA_UID}")
            # If dest is in /home/amnesia, set ownership to the amnesia
            # user.
            os.chown(p, AMNESIA_UID, AMNESIA_UID)


def _chown_ref(source: Union[str, Path], dest: Union[str, Path]):
    """Change the owner and group of dest to the ones of source"""
    # If the destination is a symlink, we want to change the symlinks
    # owner, so we set --no-dereference.
    executil.check_call(["chown", "--no-dereference", "--reference",
                         source, dest])


def _chmod_ref(source: Union[str, Path], dest: Union[str, Path]):
    """Change the permissions of dest to the ones of source"""
    # chmod doesn't support --no-dereference because it's not possible
    # to change the permissions of a symlink.
    executil.check_call(["chmod", "--reference", source, dest])
