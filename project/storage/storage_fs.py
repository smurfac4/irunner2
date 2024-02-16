# -*- coding: utf-8 -*-

import binascii
import os
import six
import sys
import tempfile

from wsgiref.util import FileWrapper

from django.utils.encoding import force_text

from .resource_id import HASH_SIZE
from .resource_id import ResourceId
from .storage_base import DataStorage, ServedData


def _get_size(fd):
    fd.seek(0, os.SEEK_END)
    size = fd.tell()
    fd.seek(0, os.SEEK_SET)
    return size


class FileSystemStorage(DataStorage):
    def __init__(self, directory):
        self._directory = directory
        if not os.path.exists(directory):
            os.mkdir(directory)

            for subdir in FileSystemStorage._list_subdirectory_names(directory):
                if not os.path.exists(subdir):
                    os.mkdir(subdir)

    @staticmethod
    def _list_subdirectory_names(directory):
        for x in range(256):
            subdir = os.path.join(directory, force_text(binascii.b2a_hex(six.int2byte(x))))
            yield subdir

    def _get_path(self, resource_id):
        s = str(resource_id)
        assert len(s) == HASH_SIZE * 2
        return os.path.join(self._directory, s[:2], s)

    def _get_temp_file(self):
        return tempfile.NamedTemporaryFile(dir=self._directory, delete=False)

    def _do_save(self, resource_id, f):
        target_name = self._get_path(resource_id)

        if not os.path.exists(target_name):
            with self._get_temp_file() as fd:
                for chunk in f.chunks():
                    fd.write(chunk)
                temp_name = fd.name

            if not os.path.exists(target_name):
                try:
                    os.rename(temp_name, target_name)
                except OSError as e:
                    # HACK: The file is locked by antivirus
                    if not (sys.platform.startswith('win') and isinstance(e, WindowsError)):
                        raise
            else:
                os.remove(temp_name)

        return resource_id

    def _do_get_size_on_disk(self, resource_id):
        target_name = self._get_path(resource_id)
        # TODO
        BLOCK = 4096
        try:
            res = os.path.getsize(target_name)
            return (res + BLOCK - 1) // BLOCK * BLOCK
        except FileNotFoundError:
            return 0

    def _do_serve(self, resource_id):
        target_name = self._get_path(resource_id)
        try:
            fd = open(target_name, 'rb')
        except FileNotFoundError:
            return None
        size = _get_size(fd)
        return ServedData(size, FileWrapper(fd))

    def _do_read_with_size(self, resource_id, max_size):
        target_name = self._get_path(resource_id)
        try:
            with open(target_name, 'rb') as fd:
                size = _get_size(fd)
                blob = fd.read() if max_size is None else fd.read(max_size)
                return (blob, size)
        except FileNotFoundError:
            return (None, 0)

    def _do_get_existing_files(self, resource_ids):
        result = set()
        for resource_id in resource_ids:
            target_name = self._get_path(resource_id)
            if os.path.exists(target_name):
                result.add(resource_id)
        return result

    def list_all(self):
        for subdir in FileSystemStorage._list_subdirectory_names(self._directory):
            assert os.path.isdir(subdir)
            with os.scandir(subdir) as it:
                for entry in it:
                    yield (ResourceId.parse(entry.name), entry.stat().st_size)
