#!/usr/bin/env python3

import atexit
import logging
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import mkdtemp, NamedTemporaryFile, TemporaryDirectory
from typing import List, Union
import unittest
from unittest import TestCase
import sys

# To be able to run the tests without installing the module first, we
# tell Python where it can find the tps module relative to the script
# directory.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(SCRIPT_DIR, "..", ".."))

from tps import executil
from tps.configuration.mount import Mount, FailedPrecondition, \
    IncorrectOwnerException, InvalidMountError, IsActiveException, \
    IsInactiveException

logging.basicConfig(level=logging.DEBUG)

device_backing_file: str
device: str
mount_point: str


def setUpModule():
    """Create a file containing an ext4 filesystem and associate it with
    a loop device, which will be used during the tests as the
    Persistent Storage cleartext device (/dev/mapper/TailsData_unlocked
    in a real Tails)."""

    # We need root privileges to be able to set up a loop device (and
    # also for testing mounting and unmounting).
    if os.geteuid() != 0:
        exit("You need to have root privileges to run this test")

    # Create a temporary file
    f = NamedTemporaryFile(prefix="dev-TailsData", delete=False)

    # Store the file name for cleanup
    global device_backing_file
    device_backing_file = f.name

    # Extend the file to 1MB
    f.truncate(1024**2)

    # Format it as ext4
    executil.check_call(["mkfs.ext4", f.name])

    # Associate a loop device with it
    global device
    device = executil.check_output(["losetup", "--find", "--show", f.name])
    device = device.strip()

    # Mount the loop device
    global mount_point
    mount_point = mkdtemp(prefix="TailsData-")
    executil.check_call(["mount", device, mount_point])


def cleanUpModule():
    """Clean up the loop device and the associated file. We register
    this function via atext.register so that it is run even if an
    exception was raised during setUpModule (we tried to use
    unittest.addModuleCleanup instead but it didn't work, cleanUpModule
    was never run)."""

    # To ensure that as much as possible of the cleanup can be done, we
    # don't exit immediately on an exception, but first continue with
    # the cleanup and raise them in the end.
    exceptions = list()

    # Unmount the device
    try:
        executil.run(["umount", "--force", device])
    except Exception as e:
        exceptions.append(e)

    # Remove the mount point
    try:
        os.rmdir(mount_point)
    except Exception as e:
        exceptions.append(e)

    # Detach the loop device. We ignore errors and try to continue the
    # cleanup.
    try:
        executil.run(["losetup", "--detach", device])
    except Exception as e:
        exceptions.append(e)

    # Remove the temporary file
    try:
        os.remove(device_backing_file)
    except Exception as e:
        exceptions.append(e)

    # We can only raise one exception, so we log the rest
    for e in exceptions[1:]:
        logging.exception(e)
    if exceptions:
        raise exceptions[0]


atexit.register(cleanUpModule)


class MountTestCase(TestCase):
    dest_dir: str
    test_mounts: List[Mount]

    @classmethod
    def setUp(cls):
        # Create a temporary directory which is used as the destination
        # directory in the tests.
        cls.dest_dir = mkdtemp(prefix="dest-TailsData")

        cls.test_mounts = [
            Mount("foo", os.path.join(cls.dest_dir, "foo"),
                  persistent_storage_mount_point=mount_point),
            Mount("dotfiles", os.path.join(cls.dest_dir, "dotfiles"),
                  uses_symlinks=True,
                  persistent_storage_mount_point=mount_point)
        ]

    @classmethod
    def tearDown(cls):
        # Remove the temporary destination directory
        shutil.rmtree(cls.dest_dir)
        # Remove the content of the mount point
        _rm_contents(Path(mount_point))


    @classmethod
    def check_same_permissions_and_owner_recursively(cls,
                                                     dir1: Union[str, Path],
                                                     dir2: Union[str, Path]):
        files1 = sorted(Path(dir1).iterdir())
        files2 = sorted(Path(dir2).iterdir())
        for child1, child2 in zip(files1, files2):
            if child1.is_file() != child2.is_file():
                raise AssertionError(f"Only one of {child1} and {child2} is a"
                                     f"regular file (or a symlink pointing to "
                                     f"a regular file)")
            if child1.is_file:
                cls.check_same_permissions_and_owner(child1, child2)
            else:
                cls.check_same_permissions_and_owner_recursively(
                    child1, child2)


    @classmethod
    def check_same_permissions_and_owner(cls, file1: Union[str, Path],
                                         file2: Union[str, Path]):
        stat1 = os.stat(file1)
        stat2 = os.stat(file2)
        if stat1.st_mode != stat2.st_mode:
            raise AssertionError(f"mode {oct(stat1.st_mode)} of {file1} is "
                                 f"different than mode {oct(stat2.st_mode)} "
                                 f"of {file2}")
        if stat1.st_uid != stat2.st_uid:
            raise AssertionError(f"owner {stat1.st_uid} of {file1} is "
                                 f"different than owner {stat2.st_uid} of "
                                 f"{file2}")

        if stat1.st_gid != stat2.st_gid:
            raise AssertionError(f"group {stat1.st_gid} of {file1} is "
                                 f"different than owner {stat2.st_gid} of "
                                 f"{file2}")


class TestActivate(MountTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

    def tearDown(self):
        # Ensure that after each test, all test mounts are unmounted
        # again.
        for mount in self.test_mounts:
            try:
                mount.deactivate()
            except FileNotFoundError:
                pass
        super().tearDown()

    def test_invalid_mount(self):
        # Check that a mount with a source outside of the mount point
        # raises a InvalidMountError.
        with self.assertRaises(InvalidMountError):
            Mount("/foo", "/bar")

    def test_non_existent_src_and_dest_dir(self):
        for mount in self.test_mounts:
            # Check that the mount is inactive
            mount.check_is_inactive()
            # Activate the mount
            mount.activate()
            # Check if the mount was activated
            mount.check_is_active()

    def test_non_existent_src_dir(self):
        # In the case that a dest dir exists, but the src dir does not,
        # live-boot copies the dest dir to the src dir along with its
        # permissions.
        for mount in self.test_mounts:
            # Create the dest dir
            mount.dest.mkdir(mode=0o777)
            # Create a file in the dest dir
            Path(mount.dest, "bar").touch()
            # Change the dest dir owner to a different owner
            # (we run as root, so we have UID 0)
            os.chown(mount.dest, 1000, -1)
            # Check that the mount is inactive
            mount.check_is_inactive()
            # Activate the mount
            mount.activate()
            # Check if the mount was activated
            mount.check_is_active()
            # Check if the src dir has the same permissions as the
            # dest dir
            self.check_same_permissions_and_owner_recursively(
                mount.src, mount.dest)
            if not mount.uses_symlinks:
                # Check that the file we created above in the dest dir
                # now also exists in the src dir
                self.assertTrue(Path(mount.src, "bar").exists())

    def test_non_existent_dest_dir(self):
        for mount in self.test_mounts:
            # Create the source dir
            mount.src.mkdir(mode=0o770)
            # Create a file in the source dir
            Path(mount.src, "bla").touch()
            # Check that the mount is inactive
            mount.check_is_inactive()
            # Check that check_is_active raises an IsInactiveException
            with self.assertRaises(IsInactiveException):
                mount.check_is_active()
            # Activate the mount
            mount.activate()
            # Check if the mount was activated
            mount.check_is_active()
            # Check that check_is_inactive raises an IsActiveException
            with self.assertRaises(IsActiveException):
                mount.check_is_inactive()
            # Check if the newly created dest dir has the same
            # permissions as the source dir.
            self.check_same_permissions_and_owner_recursively(
                mount.src, mount.dest)

    def test_existent_src_and_dest_dir(self):
        for mount in self.test_mounts:
            # Create the source dir
            mount.src.mkdir(mode=0o700)
            # Create the dest dir with a different mode
            mount.dest.mkdir(mode=0o770)
            # Change the dest dir owner to a different owner
            # (we run as root, so we have UID 0)
            os.chown(mount.dest, 1000, -1)
            # Activate the mount
            mount.activate()
            # Check if the mount was activated
            mount.check_is_active()
            # Check if the dest dir now has the same permissions
            # as the src dir, if this mount does not use symlinks
            # (the behavior of live-boot for a symlink mount is to not
            # change permissions of an existing source directory and we
            # want to mirror that behavior).
            if not mount.uses_symlinks:
                self.check_same_permissions_and_owner_recursively(
                    mount.src, mount.dest)

    def test_files_with_different_owner_in_src(self):
        for mount in self.test_mounts:
            # Create the source dir
            mount.src.mkdir(mode=0o700)
            # Change the src dir owner to a different owner
            # (we run as root, so we have UID 0)
            os.chown(mount.src, 1000, -1)
            # Create a subdirectory which is owned by root
            Path(mount.src, "root").mkdir()
            # Create a file that is not owned by root
            Path(mount.src, "root", "public").touch()
            # Create a subdirectory which is not owned by root
            Path(mount.src, "user").mkdir()
            os.chown(Path(mount.src, "user"), 1000, -1)
            # Create a file that is owned by root
            Path(mount.src, "user", "secret").touch()
            # Activate the mount
            mount.activate()
            # Check if the mount was activated
            mount.check_is_active()
            # Check if all the files from the source now also exist
            # in the destination and are symlinks
            Path(mount.dest, "root", "public").is_symlink()
            Path(mount.dest, "user", "secret").is_symlink()
            # Check if the newly created dest dir has the same
            # permissions as the source dir.
            self.check_same_permissions_and_owner_recursively(
                mount.src, mount.dest)
            # Deactivate the mount
            mount.deactivate()
            # Check that no non-directory files are left in the dest dir
            self.assertFalse(any(files for _, _, files in os.walk(mount.dest)))

    def test_symlink_with_different_owner_in_dest(self):
        for mount in self.test_mounts:
            # This test is only for mounts using symlinks
            if not mount.uses_symlinks:
                continue
            # Create the dotfiles source directory owned by UID 1000
            Path(mount.src, "dotfiles").mkdir(mode=0o700, parents=True)
            os.chown(Path(mount.src, "dotfiles"), 1000, 1000)
            # Create the dest dir
            mount.dest.mkdir(mode=0o700)
            # Create a symlink called dotfiles to some dir owned by root
            with TemporaryDirectory() as tmpdir:
                Path(mount.dest, "dotfiles").symlink_to(tmpdir)
                # Make the symlink be owned by UID 1000
                os.chown(Path(mount.dest, "dotfiles"), 1000, 1000,
                         follow_symlinks=False)
                # Assert that activating the mount raises an
                # IncorrectOwnerException
                with self.assertRaises(IncorrectOwnerException):
                    mount.activate()

    def test_already_mounted(self):
        for mount in self.test_mounts:
            # Activate the mount
            mount.activate()
            # Check we don't raise an exception in the case that an
            # already activated mount is activated again (see comment
            # in activate()).
            mount.activate()

    def test_file_in_place_of_dest_dir(self):
        for mount in self.test_mounts:
            # Create a file in the place of the dest dir
            mount.dest.touch()
            # Check that activating the mount raises a
            # FailedPrecondition exception
            with self.assertRaises(FailedPrecondition):
                mount.activate()

    def test_something_else_mounted(self):
        for mount in self.test_mounts:
            # Create the destination directory
            mount.dest.mkdir()
            # Create a temporary directory
            with TemporaryDirectory() as tmpdir:
                # Bind mount the temporary directory to the dest dir
                subprocess.check_call(["mount", "--bind", tmpdir, mount.dest])
                # Check that activating the mount raises a
                # FailedPrecondition exception
                with self.assertRaises(FailedPrecondition):
                    mount.activate()
                # Unmount the temporary directory
                subprocess.check_call(["umount", "--force", mount.dest])


class TestDeactivate(MountTestCase):
    def test_deactivate(self):
        for mount in self.test_mounts:
            # Create the source directory
            mount.src.mkdir()
            # Create a subdirectory
            Path(mount.src, "dir").mkdir()
            # Create a file in the subdirectory
            Path(mount.src, "dir/bla").touch()
            # Activate the mount
            mount.activate()
            # Check that the file exists in the destination
            self.assertTrue(Path(mount.dest, "dir/bla").exists())
            # Deactivate the mount
            mount.deactivate()
            # Check that the file does not exist anymore in the
            # destination
            self.assertFalse(Path(mount.dest, "dir/bla").exists())


def _rm_contents(path: Path):
    for child in path.iterdir():
        if child.is_file():
            child.unlink()
        else:
            _rm_contents(child)
            child.rmdir()


if __name__ == '__main__':
    # We set the module name explicitly to be able to run the tests
    # with `trace`, see https://stackoverflow.com/a/25300465.
    unittest.main("mount_test", failfast=True, buffer=True)
