from __future__ import unicode_literals, print_function

from os.path import splitext
import zipfile
import xml.etree.ElementTree as ET

from django.core.files.base import ContentFile
from django.utils import timezone
from django.utils.translation import get_language_info

from common.ir18n.strings import LazyI18nString
from problems.models import Problem, ProblemExtraInfo, TestCase, ProblemRelatedFile, ProblemRelatedSourceFile
from storage.storage import create_storage
from storage.utils import store_and_fill_metadata

HIDE_HEADER_CSS = '.problem-statement .header { display: none; }'


def _langcode_to_language(code):
    return get_language_info(code)['name'].lower()


def _inject_lang(filename, langcode):
    root, ext = splitext(filename)
    return '{}-{}{}'.format(root, langcode, ext)


def get_full_name(root, langcodes):
    remap = {_langcode_to_language(code): code for code in langcodes}
    res = {}
    for name in root.findall('names/name'):
        langcode = remap.get(name.attrib['language'])
        if langcode is not None:
            res[langcode] = name.attrib['value']
    return LazyI18nString(res)


def parse_input_output_file(name):
    if name in (None, 'stdin', 'stdout'):
        return ''
    return name


def get_int(elem, name):
    return int(elem.find(name).text)


def load_source_file(myzip, elem, problem, file_type, compiler):
    path = elem.find('source').attrib['path']
    fd = ContentFile(myzip.read(path), name=path.split('/')[-1])

    related_file = ProblemRelatedSourceFile(problem=problem, file_type=file_type, compiler=compiler)
    store_and_fill_metadata(fd, related_file)
    related_file.full_clean()
    related_file.save()


def load_html_statement(myzip, problem, langcode, language, existing_files):
    prefix = 'statements/.html/{0}/'.format(language)
    for path in myzip.namelist():
        if path.startswith(prefix):
            filename = path[len(prefix):]
            if not filename:
                # skip the directory itself
                continue

            print(filename)
            if filename == 'problem.html':
                file_type = ProblemRelatedFile.STATEMENT_HTML
                target_lang = langcode
                target_filename = _inject_lang(filename, langcode)
            else:
                file_type = ProblemRelatedFile.ADDITIONAL_STATEMENT_FILE
                target_lang = ''
                target_filename = filename

            if target_filename in existing_files:
                continue

            related_file = ProblemRelatedFile(problem=problem, file_type=file_type, language=target_lang)

            data = myzip.read(path)
            # HACK
            if filename == 'problem-statement.css':
                data += HIDE_HEADER_CSS.encode('utf-8')

            fd = ContentFile(data, name=target_filename)
            store_and_fill_metadata(fd, related_file)
            related_file.full_clean()
            related_file.save()
            existing_files.add(target_filename)


def load_tex_statement(myzip, problem, langcode, language):
    lines = []

    def load(fn):
        name = 'statement-sections/{0}/{1}'.format(language, fn)
        try:
            return myzip.read(name).decode('utf-8')
        except (KeyError, UnicodeDecodeError):
            return

    def add(fn, section):
        data = load(fn)
        if data is None:
            return
        if section:
            lines.append('')
            lines.append('\\{}'.format(section))
        lines.append(data)

    add('legend.tex', '')
    add('input.tex', 'InputFile')
    add('output.tex', 'OutputFile')

    example_lines = []
    i = 0
    while True:
        i += 1
        inp = load('example.{:02d}'.format(i))
        ans = load('example.{:02d}.a'.format(i))
        if inp and ans:
            example_lines.append('\\exmp{{{}}}{{{}}}'.format(inp, ans))
        else:
            break

    if example_lines:
        lines.append('')
        lines.append('\\Example' if len(example_lines) == 1 else '\\Examples')
        lines.append('\\begin{example}')
        lines.extend(example_lines)
        lines.append('\\end{example}')

    add('notes.tex', 'Note')

    if lines:
        tex_data = ''.join('{}\n'.format(line) for line in lines)
        related_file = ProblemRelatedFile(problem=problem, file_type=ProblemRelatedFile.STATEMENT_TEX_PYLIGHTEX, language=langcode)
        fd = ContentFile(tex_data.encode('utf-8'), name=_inject_lang('statement.tex', langcode))
        store_and_fill_metadata(fd, related_file)
        related_file.full_clean()
        related_file.save()


def parse_archive(myzip, langcodes, compiler, user):
    problem_xml_data = myzip.read('problem.xml')
    root = ET.fromstring(problem_xml_data)

    problem = Problem()
    problem.short_name = root.attrib['short-name']
    problem.full_name = get_full_name(root, langcodes)

    judging = root.find('judging')
    run_twice = judging.get('run-count') == '2'
    problem.input_filename = parse_input_output_file(judging.get('input-file'))
    problem.output_filename = parse_input_output_file(judging.get('output-file'))
    problem.full_clean()
    problem.save()

    tests = []
    storage = create_storage()

    ts = timezone.now()

    tl_ml_set = False
    total_tests = 0

    extra_info = ProblemExtraInfo(problem=problem, run_twice=run_twice)

    for testset in judging.findall('testset'):
        time_limit = get_int(testset, 'time-limit')
        memory_limit = get_int(testset, 'memory-limit')

        if not tl_ml_set:
            extra_info.default_time_limit = time_limit
            extra_info.default_memory_limit = memory_limit
            tl_ml_set = True

        test_count = get_int(testset, 'test-count')

        input_pattern = testset.find('input-path-pattern').text
        answer_pattern = testset.find('answer-path-pattern').text
        number = 0

        for i, test in enumerate(testset.findall('tests/test')):
            number = i + 1
            total_tests += 1

            if test.get('sample') == 'true':
                if extra_info.sample_test_count + 1 == total_tests:
                    extra_info.sample_test_count += 1

            tc = TestCase(problem=problem, ordinal_number=total_tests, time_limit=time_limit, memory_limit=memory_limit)
            tc.set_input(storage, ContentFile(myzip.read(input_pattern % (number,))))
            tc.set_answer(storage, ContentFile(myzip.read(answer_pattern % (number,))))
            tc.author = user
            tc.creation_time = ts
            tc.full_clean()
            tests.append(tc)

        if number != test_count:
            raise ValueError('"test-count" is {}, number of <test> tags is {}'.format(test_count, number))

    extra_info.save()

    TestCase.objects.bulk_create(tests)

    if compiler is not None:
        for checker in root.findall('assets/checker'):
            load_source_file(myzip, checker, problem, ProblemRelatedSourceFile.CHECKER, compiler)

        for interactor in root.findall('assets/interactor'):
            load_source_file(myzip, interactor, problem, ProblemRelatedSourceFile.INTERACTOR, compiler)

        for validator in root.findall('assets/validators/validator'):
            load_source_file(myzip, validator, problem, ProblemRelatedSourceFile.VALIDATOR, compiler)

        for scorer in root.findall('assets/scorer'):
            load_source_file(myzip, scorer, problem, ProblemRelatedSourceFile.SCORER, compiler)

    existing_files = set()
    for langcode in langcodes:
        language = _langcode_to_language(langcode)
        load_html_statement(myzip, problem, langcode, language, existing_files)
        load_tex_statement(myzip, problem, langcode, language)
    return problem


def import_full_package(upload, langcodes, compiler, user, folder_id=None):
    with zipfile.ZipFile(upload, 'r', allowZip64=True) as myzip:
        problem = parse_archive(myzip, langcodes, compiler, user)
    if folder_id is not None:
        problem.folders.add(folder_id)
