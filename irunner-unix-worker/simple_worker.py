import configparser
import logging
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import requests

from workerlib.apiclient import IRunnerApiClient
from workerlib.cache import Cache


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
)


config = configparser.ConfigParser()
config.read('config.ini')

API_BASE = config['Server']['endpoint'].rstrip('/')
TOKEN = config['Server']['token']


session = requests.Session()
session.headers.update({
    'Worker-Token': TOKEN,
})


storage_client = IRunnerApiClient(
    'simple-storage-client',
    API_BASE + '/',
    TOKEN,
)

cache = Cache('simple-cache')


def fetch_resource(resource_id):
    rid = storage_client._fetch_resource(
        cache,
        {'resourceId': resource_id},
    )
    return Path(cache[rid])


def normalize_output(data):
    text = data.decode(
        'utf-8',
        errors='replace',
    )
    text = text.replace('\r\n', '\n')
    return text.strip()


def make_result(
    outcome,
    exit_code,
    time_used,
    score,
    message='',
):
    return {
        'outcome': outcome,
        'exit_code': exit_code,
        'time_used': time_used,
        'memory_used': 0,
        'score': score,
        'message': message,
    }


def get_memory_arg(memory_limit):
    if not memory_limit:
        return '256m'

    memory_mb = max(
        64,
        int(memory_limit) // 1024 // 1024,
    )

    return '{}m'.format(memory_mb)


# Universal "harness": the worker copies it along with the checker and
# runs it instead of pytest. The harness itself imports test_solution.py,
# calls all test_* functions in it, catches AssertionError and prints
# EXACTLY WHAT should go into the "Checker message" to STDOUT —
# nothing extra. Therefore, the worker no longer needs to parse/clean the output:
# it just takes the harness's stdout as is.
#
# Contract for checker authors:
#   - the function starts with test_
#   - print() inside the test does not affect anything, only the text of the
#     assert message matters (assert condition, "this text will be shown")
#   - if you need to show something more complex than a single assert,
#     just do `raise AssertionError("custom text")` anywhere
_CHECKER_HARNESS = '''
import sys
import traceback
import importlib.util

spec = importlib.util.spec_from_file_location("checker", "test_solution.py")
module = importlib.util.module_from_spec(spec)

try:
    spec.loader.exec_module(module)
except Exception as exc:
    print("Error in the checker itself: {}".format(exc))
    sys.exit(2)

test_funcs = [
    getattr(module, name)
    for name in dir(module)
    if name.startswith("test_") and callable(getattr(module, name))
]

if not test_funcs:
    print("No test_* functions found in the checker")
    sys.exit(2)

failed = False

for func in test_funcs:
    try:
        func()
    except AssertionError as exc:
        failed = True
        text = str(exc).strip()
        print(text if text else "Check failed: {}".format(func.__name__))
    except Exception as exc:
        failed = True
        print("Error executing check {}: {}".format(func.__name__, exc))

sys.exit(1 if failed else 0)
'''


def run_checker(work, checker_path, elapsed):
    """
    Copies the checker (test_solution.py) to the working directory and runs it
    via the universal harness (see _CHECKER_HARNESS above).

    Returns:
        None                -> checker passed (or was absent), can proceed
        make_result(...)     -> checker failed, this is the final test result

    Important: under the new checker, NO changes are needed in this function —
    whatever the checker prints via the assert message will go into the
    "Checker message" exactly as is.
    """

    local_checker = Path('test_solution.py')
    target_checker = None

    if checker_path and Path(checker_path).exists():
        target_checker = Path(checker_path)
    elif local_checker.exists():
        target_checker = local_checker

    if not target_checker or not target_checker.exists():
        return None

    shutil.copy(target_checker, work / 'test_solution.py')

    harness_path = work / '_checker_harness.py'
    harness_path.write_text(_CHECKER_HARNESS, encoding='utf-8')

    test_proc = subprocess.run(
        [
            '/Users/avans/irunner2/.venv/bin/python',
            str(harness_path),
        ],
        cwd=work,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    if test_proc.returncode != 0:
        message = test_proc.stdout.decode('utf-8', errors='replace').strip()

        stderr_text = test_proc.stderr.decode('utf-8', errors='replace').strip()
        if stderr_text:
            message = (message + '\n' + stderr_text).strip()

        if not message:
            message = 'Check failed'

        return make_result(
            'WRONG_ANSWER',
            test_proc.returncode,
            elapsed,
            0,
            message[:500],
        )

    return None


# ============================================================
# PYTHON
# ============================================================

def run_python_test(
    solution_path,
    input_path,
    expected_path,
    time_limit_ms,
    memory_limit,
):
    with tempfile.TemporaryDirectory(
        prefix='irunner-python-'
    ) as temp:

        work = Path(temp)

        shutil.copy(
            solution_path,
            work / 'solution.py',
        )

        stdin_data = input_path.read_bytes()
        expected_data = expected_path.read_bytes()

        memory_arg = get_memory_arg(
            memory_limit
        )

        cmd = [
            'docker',
            'run',
            '--rm',

            '--network',
            'none',

            '--memory',
            memory_arg,

            '--cpus',
            '1',

            '--pids-limit',
            '64',

            '--read-only',

            '--security-opt',
            'no-new-privileges',

            '--volume',
            '{}:/work:ro'.format(
                work.resolve()
            ),

            'simple-python-runner:latest',

            'python3',
            '/work/solution.py',
        ]

        timeout_seconds = max(
            0.2,
            float(time_limit_ms) / 1000.0,
        )

        started = time.monotonic()

        try:
            proc = subprocess.run(
                cmd,
                input=stdin_data,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout_seconds,
            )

        except subprocess.TimeoutExpired:
            elapsed = int(
                (
                    time.monotonic()
                    - started
                ) * 1000
            )

            return make_result(
                'TIME_LIMIT_EXCEEDED',
                -1,
                elapsed,
                0,
                'Time limit exceeded',
            )

        elapsed = int(
            (
                time.monotonic()
                - started
            ) * 1000
        )

        if proc.returncode != 0:
            message = proc.stderr.decode(
                'utf-8',
                errors='replace',
            )[:255]

            return make_result(
                'RUNTIME_ERROR',
                proc.returncode,
                elapsed,
                0,
                message,
            )

        actual = normalize_output(
            proc.stdout
        )

        expected = normalize_output(
            expected_data
        )

        if actual == expected:
            return make_result(
                'ACCEPTED',
                0,
                elapsed,
                None,
                '',
            )

        return make_result(
            'WRONG_ANSWER',
            0,
            elapsed,
            0,
            'Wrong answer',
        )


# ============================================================
# BASH / SH (with local check via Pytest-checker)
# ============================================================

def run_sh_test(
    solution_path,
    input_path,
    expected_path,
    time_limit_ms,
    memory_limit,
    checker_path=None,
):
    with tempfile.TemporaryDirectory(
        prefix='irunner-sh-'
    ) as temp:

        work = Path(temp)

        # 1. Copy the student's solution
        script_dest = work / 'solution.sh'
        shutil.copy(solution_path, script_dest)
        script_dest.chmod(0o755)

        stdin_data = input_path.read_bytes()
        expected_data = expected_path.read_bytes()
        memory_arg = get_memory_arg(memory_limit)

        # Run the student's bash script in Docker
        cmd = [
            'docker',
            'run',
            '--rm',
            '--network', 'none',
            '--memory', memory_arg,
            '--cpus', '1',
            '--pids-limit', '64',
            '--security-opt', 'no-new-privileges',
            '--volume', '{}:/work'.format(work.resolve()),
            'simple-python-runner:latest',
            'bash',
            '/work/solution.sh',
            '/work/foo.txt',
        ]

        timeout_seconds = max(
            0.2,
            float(time_limit_ms) / 1000.0,
        )

        started = time.monotonic()

        try:
            proc = subprocess.run(
                cmd,
                input=stdin_data,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout_seconds,
            )

        except subprocess.TimeoutExpired:
            elapsed = int((time.monotonic() - started) * 1000)
            return make_result('TIME_LIMIT_EXCEEDED', -1, elapsed, 0, 'Time limit exceeded')

        elapsed = int((time.monotonic() - started) * 1000)

        # If the bash script itself crashes
        if proc.returncode != 0:
            error_msg = proc.stderr.decode('utf-8', errors='replace')
            return make_result(
                'RUNTIME_ERROR',
                proc.returncode,
                elapsed,
                0,
                error_msg[:255],
            )

        # 2. Check the results via Pytest (if there is a local checker)
        checker_result = run_checker(work, checker_path, elapsed)
        if checker_result is not None:
            return checker_result

        return make_result(
            'ACCEPTED',
            0,
            elapsed,
            None,
            '',
        )


# ============================================================
# C++
# ============================================================

def compile_cpp(solution_path):
    """
    Compiles C++ once before running the tests.

    Returns:
        (tempdir, executable_path, None)
    or:
        (None, None, error_message)
    """

    tempdir = tempfile.TemporaryDirectory(
        prefix='irunner-cpp-'
    )

    work = Path(tempdir.name)

    shutil.copy(
        solution_path,
        work / 'solution.cpp',
    )

    compile_cmd = [
        'docker',
        'run',
        '--rm',

        '--network',
        'none',

        '--memory',
        '512m',

        '--cpus',
        '1',

        '--pids-limit',
        '64',

        '--security-opt',
        'no-new-privileges',

        '--volume',
        '{}:/work'.format(
            work.resolve()
        ),

        'simple-cpp-runner:latest',

        'g++',
        '-std=c++17',
        '-O2',
        '-pipe',

        '/work/solution.cpp',

        '-o',
        '/work/solution',
    ]

    logging.info(
        'Compiling C++ solution'
    )

    try:
        proc = subprocess.run(
            compile_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
        )

    except subprocess.TimeoutExpired:
        tempdir.cleanup()

        return (
            None,
            None,
            'Compilation timeout',
        )

    if proc.returncode != 0:
        message = proc.stderr.decode(
            'utf-8',
            errors='replace',
        )

        tempdir.cleanup()

        return (
            None,
            None,
            message[:255],
        )

    executable = work / 'solution'

    if not executable.exists():
        tempdir.cleanup()

        return (
            None,
            None,
            'Compiler did not create executable',
        )

    return (
        tempdir,
        executable,
        None,
    )


def run_cpp_test(
    executable_path,
    input_path,
    expected_path,
    time_limit_ms,
    memory_limit,
    checker_path=None,
):
    work = executable_path.parent

    stdin_data = input_path.read_bytes()
    expected_data = expected_path.read_bytes()

    memory_arg = get_memory_arg(
        memory_limit
    )

    cmd = [
        'docker',
        'run',
        '--rm',

        '--network',
        'none',

        '--memory',
        memory_arg,

        '--cpus',
        '1',

        '--pids-limit',
        '64',

        '--read-only',

        '--security-opt',
        'no-new-privileges',

        '--volume',
        '{}:/work:ro'.format(
            work.resolve()
        ),

        'simple-cpp-runner:latest',

        '/work/solution',
    ]

    timeout_seconds = max(
        0.2,
        float(time_limit_ms) / 1000.0,
    )

    started = time.monotonic()

    try:
        proc = subprocess.run(
            cmd,
            input=stdin_data,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
        )

    except subprocess.TimeoutExpired:
        elapsed = int(
            (
                time.monotonic()
                - started
            ) * 1000
        )

        return make_result(
            'TIME_LIMIT_EXCEEDED',
            -1,
            elapsed,
            0,
            'Time limit exceeded',
        )

    elapsed = int(
        (
            time.monotonic()
            - started
        ) * 1000
    )

    if proc.returncode != 0:
        message = proc.stderr.decode(
            'utf-8',
            errors='replace',
        )[:255]

        return make_result(
            'RUNTIME_ERROR',
            proc.returncode,
            elapsed,
            0,
            message,
        )

    actual = normalize_output(
        proc.stdout
    )

    expected = normalize_output(
        expected_data
    )

    if actual != expected:
        return make_result(
            'WRONG_ANSWER',
            0,
            elapsed,
            0,
            'Wrong answer',
        )

    # The output matched — now additionally run the pytest-checker
    # (for example, checking "is the class keyword used"
    # in the solution.cpp source file located next to it in work/).
    checker_result = run_checker(work, checker_path, elapsed)
    if checker_result is not None:
        return checker_result

    return make_result(
        'ACCEPTED',
        0,
        elapsed,
        None,
        '',
    )


# ============================================================
# API
# ============================================================

def take_job():
    response = session.post(
        API_BASE + '/simple/jobs/take',
        timeout=10,
    )

    if response.status_code == 204:
        return None

    response.raise_for_status()

    return response.json()


def send_result(
    judgement_id,
    payload,
):
    response = session.post(
        API_BASE
        + '/simple/jobs/{}/result'.format(
            judgement_id
        ),
        json=payload,
        timeout=20,
    )

    response.raise_for_status()


# ============================================================
# JOB
# ============================================================

def process_job(job):
    judgement_id = job['judgement_id']
    solution = job['solution']

    compiler = solution.get(
        'compiler',
        '',
    ).lower()

    if compiler not in (
        'python',
        'python3',
        'cpp',
        'c++',
        'g++',
        'sh',
        'bash',
    ):
        raise RuntimeError(
            'Unsupported compiler: {}'.format(
                compiler
            )
        )

    logging.info(
        'Got judgement %s (%s)',
        judgement_id,
        compiler,
    )

    solution_path = fetch_resource(
        solution['resource_id']
    )

    results = []
    final_outcome = 'ACCEPTED'

    cpp_tempdir = None
    cpp_executable = None

    # --------------------------------------------------------
    # C++ compilation
    # --------------------------------------------------------

    if compiler in (
        'cpp',
        'c++',
        'g++',
    ):
        (
            cpp_tempdir,
            cpp_executable,
            compile_error,
        ) = compile_cpp(
            solution_path
        )

        if compile_error is not None:
            logging.info(
                'Judgement %s compilation failed: %s',
                judgement_id,
                compile_error,
            )

            payload = {
                'outcome': 'RUNTIME_ERROR',
                'tests': [],
            }

            send_result(
                judgement_id,
                payload,
            )

            logging.info(
                'Judgement %s finished: COMPILATION ERROR',
                judgement_id,
            )

            return

    try:

        # ----------------------------------------------------
        # Tests
        # ----------------------------------------------------

        for test in job['tests']:

            logging.info(
                'Judgement %s, test %s',
                judgement_id,
                test['number'],
            )

            input_path = fetch_resource(
                test['input_resource_id']
            )

            expected_path = fetch_resource(
                test['answer_resource_id']
            )

            if compiler in (
                'python',
                'python3',
            ):
                result = run_python_test(
                    solution_path,
                    input_path,
                    expected_path,
                    test['time_limit'],
                    test['memory_limit'],
                )
            elif compiler in (
                'sh',
                'bash',
            ):
                checker_res_id = solution.get('checker_resource_id')
                checker_path = fetch_resource(checker_res_id) if checker_res_id else None

                result = run_sh_test(
                    solution_path,
                    input_path,
                    expected_path,
                    test['time_limit'],
                    test['memory_limit'],
                    checker_path=checker_path,
                )
            else:
                checker_res_id = solution.get('checker_resource_id')
                checker_path = fetch_resource(checker_res_id) if checker_res_id else None

                result = run_cpp_test(
                    cpp_executable,
                    input_path,
                    expected_path,
                    test['time_limit'],
                    test['memory_limit'],
                    checker_path=checker_path,
                )

            result['test_id'] = test['id']

            if result['score'] is None:
                result['score'] = test['points']

            results.append(
                result
            )

            if result['outcome'] != 'ACCEPTED':
                final_outcome = result[
                    'outcome'
                ]
                break

        # ----------------------------------------------------
        # Send result
        # ----------------------------------------------------

        payload = {
            'outcome': final_outcome,
            'tests': results,
        }

        send_result(
            judgement_id,
            payload,
        )

        logging.info(
            'Judgement %s finished: %s',
            judgement_id,
            final_outcome,
        )

    finally:
        if cpp_tempdir is not None:
            cpp_tempdir.cleanup()


# ============================================================
# MAIN
# ============================================================

def main():
    logging.info(
        'Simple Docker worker started'
    )

    while True:
        try:
            job = take_job()

            if job is None:
                time.sleep(2)
                continue

            process_job(
                job
            )

        except KeyboardInterrupt:
            logging.info(
                'Bye'
            )
            break

        except Exception:
            logging.exception(
                'Worker error'
            )

            time.sleep(3)


if __name__ == '__main__':
    main()