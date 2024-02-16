# -*- coding: utf-8 -*-

from __future__ import unicode_literals

from django.test import TestCase
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.utils.encoding import force_text

from .encodings import try_decode_ascii
from .storage_fs import FileSystemStorage
from .resource_id import ResourceId
from .validators import validate_filename
from .representation import ResourseRepresentation, represent_blob

import codecs
import os
import shutil
import tempfile


class DataIdTests(TestCase):
    def test_to_string(self):
        h = ResourceId(b'\0')
        self.assertEqual(force_text(h), '00')

    def test_from_string(self):
        h = ResourceId.parse('ff')
        self.assertEqual(len(h.get_binary()), 1)
        self.assertEqual(h.get_binary(), b'\xff')

        with self.assertRaises(Exception):
            # TypeError on py2
            # binascii.Error on py3
            ResourceId.parse('a')

        with self.assertRaises(Exception):
            ResourceId.parse('ax')


class FileSystemStorageTests(TestCase):
    def _run_simple(self, fs, msg, resource_id_string):
        # msg should be plain ASCII string

        h = fs.save(ContentFile(msg))
        self.assertTrue(type(h) is ResourceId)
        self.assertEqual(force_text(h), resource_id_string)

        # read completely
        blob_read, is_complete = fs.read_blob(h, len(msg) * 10)
        self.assertTrue(is_complete)
        self.assertEqual(blob_read, msg)

        blob_read, is_complete = fs.read_blob(h, len(msg))
        self.assertTrue(is_complete)
        self.assertEqual(blob_read, msg)

        blob_read, is_complete = fs.read_blob(h, None)
        self.assertTrue(is_complete)
        self.assertEqual(blob_read, msg)

        # read partially
        partial_length = len(msg) // 2
        if partial_length < len(msg):
            blob_read, is_complete = fs.read_blob(h, partial_length)
            self.assertFalse(is_complete)
            self.assertEqual(blob_read, msg[:partial_length])

        # represent
        representation = fs.represent(h)
        self.assertTrue(type(representation) is ResourseRepresentation)
        self.assertTrue(representation.is_complete())
        self.assertTrue(representation.is_utf8())
        self.assertEqual(representation.text, msg.decode('ascii'))

    def test_blob(self):
        dirpath = tempfile.mkdtemp()
        try:
            fs = FileSystemStorage(os.path.join(dirpath, 'filestorage'))

            msg = b'The quick brown fox jumps over the lazy dog'
            sha1 = '2fd4e1c67a2d28fced849ee1bb76e7391b93eb12'
            self._run_simple(fs, msg, sha1)

            self._run_simple(fs, b'', '')
            self._run_simple(fs, b'0', '30')  # ASCII '0' = 48 = 0x30
            self._run_simple(fs, b'00', '3030')
            self._run_simple(fs, b'0123456789', '30313233343536373839')
            self._run_simple(fs, b'hello', force_text(codecs.encode(b'hello', 'hex')))

            does_not_exist = ResourceId.parse('59db6ba4a6aff5ed3d980542daf41be65624a1e8')
            self.assertTrue(fs.represent(does_not_exist) is None)

        finally:
            shutil.rmtree(dirpath)

    def test_check_availability(self):
        with tempfile.TemporaryDirectory() as dirpath:
            fs = FileSystemStorage(os.path.join(dirpath, 'filestorage'))
            resource_id = fs.save(ContentFile(b'a' * 100))
            assert isinstance(resource_id, ResourceId)

            small_resource_id = ResourceId(b'hello')
            absent_resource_id = ResourceId.parse('da39a3ee5e6b4b0d3255bfef95601890afd80709')  # SHA1("")

            assert fs.check_availability([]) == []
            assert fs.check_availability([resource_id, small_resource_id, absent_resource_id]) == [True, True, False]
            assert fs.check_availability([small_resource_id, absent_resource_id, resource_id]) == [True, False, True]


class FilenameValidatorTests(TestCase):
    def test_good(self):
        NAMES = (
            'a', '123', 'sol.cpp', '.cpp', 'statement.tex',
            'a plus b.c', 'привет.pas', 'решение участника.exe',
            'Разбор задачи (Пупкин В., 3 курс).doc',
            'Главная — Insight Runner.html',
            'あ',
            'lpt10', 'console', '1.aux',
            '1. cpp', '1 . cpp'
        )
        for name in NAMES:
            validate_filename(name)

    def _check_fail(self, *args):
        for name in args:
            with self.assertRaises(ValidationError):
                validate_filename(name)

    def test_type_mismatch(self):
        self._check_fail(None, 1, 3.14159, [], {})

    def test_empty(self):
        self._check_fail('')

    def test_non_printable_chars(self):
        self._check_fail('tab\tseparated.txt', '\x00', 'hello\x00world.bmp', 'hello\x01world.bmp', '\u001f.dpr')

    def test_reserved(self):
        self._check_fail('a/b.txt', 'a?b.txt', '1.*', '\\fpmi-stud\\source.cpp', '../../etc/passwd')
        self._check_fail('cgi-bin?param-value')
        self._check_fail('BinaryTree <T extends Comparable <T>>.java')

    def test_windows(self):
        self._check_fail('con', 'CON', 'CoN', 'lpt9', 'aux.cpp', 'aux.1.cpp', 'prn')

    def test_end(self):
        self._check_fail('1.cpp.', '1.cpp. ', '1. .', '.', ' ')


class GuessAsciiEncodingTests(TestCase):
    def test_decode_cyrillic(self):
        msg = u'Привет, мир!'
        self.assertEqual(try_decode_ascii(msg.encode('cp1251')), msg)
        self.assertEqual(try_decode_ascii(msg.encode('cp866')), msg)

    def test_decode_plain(self):
        msg = u'Hello, world!'
        self.assertEqual(try_decode_ascii(msg.encode('cp1251')), msg)
        self.assertEqual(try_decode_ascii(msg.encode('cp866')), msg)


class RepresentationTests(TestCase):
    def test_empty(self):
        r = represent_blob(b'', 0)
        self.assertTrue(r.is_utf8())
        self.assertFalse(r.is_binary())
        self.assertTrue(r.is_empty())
        self.assertEqual(r.complete_text, '')

    def test_binary(self):
        r = represent_blob(b'\x00', 1)
        self.assertFalse(r.is_utf8())
        self.assertTrue(r.is_binary())

        r = represent_blob(b'\xFF\xFE\x00\x00', 4)
        self.assertFalse(r.is_utf8())
        self.assertTrue(r.is_binary())

        r = represent_blob(b'\x01\x02\x03', 3)
        self.assertFalse(r.is_utf8())
        self.assertTrue(r.is_binary())

    def test_boms(self):
        r = represent_blob(b'\xEF\xBB\xBF', 3)
        self.assertTrue(r.is_utf8())
        self.assertFalse(r.is_binary())
        self.assertTrue(r.has_bom())
        self.assertEqual(r.editable_text, None)

    def test_ascii(self):
        r = represent_blob(b'aba\tcaba\r\n')
        self.assertTrue(r.is_utf8())
        self.assertEqual(r.text, 'aba\tcaba\r\n')

    def test_utf16(self):
        blob = b'\xFF\xFE' + 'привет hello'.encode('utf_16_le')
        self.assertEqual(len(blob), 2 + 12 * 2)
        self.assertTrue(b'\x00' in blob)

        r = represent_blob(blob, len(blob))
        self.assertEqual(r.text, 'привет hello')
        self.assertFalse(r.is_binary())
        self.assertEqual(r.editable_text, None)

    def test_broken_utf8(self):
        blob = 'Привет'.encode('utf-8')
        r = represent_blob(blob)
        self.assertTrue(r.is_utf8())
        self.assertEqual(r.text, 'Привет')
        self.assertTrue(r.is_complete())

        r = represent_blob(blob[:-1])
        self.assertFalse(r.is_utf8())
        self.assertEqual(r.text, 'РџСЂРёРІРµС')  # UTF-8 bytes as Win-1251
        self.assertTrue(r.is_complete())

        r = represent_blob(blob[:-1], 100500)
        self.assertTrue(r.is_utf8())
        self.assertEqual(r.text, 'Приве')
        self.assertFalse(r.is_complete())
