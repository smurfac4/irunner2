import io
import logging
import pathlib
import tarfile
import shutil

import docker

from .base import BaseTester


def _get_data(container, srcpath, dstpath):
    import docker
    try:
        strm, stat = container.get_archive(srcpath)
    except docker.errors.NotFound:
        return

    tarstream = io.BytesIO()
    for chunk in strm:
        tarstream.write(chunk)
    tarstream.seek(0)

    with tarfile.TarFile(fileobj=tarstream, mode='r') as tar:
        for member in tar:
            target = dstpath / member.name
            if member.isreg():
                file = tar.extractfile(member)
                with target.open('wb') as outfile:
                    shutil.copyfileobj(file, outfile)
                target.chmod(member.mode)
            elif member.isdir():
                target.mkdir(exist_ok=True)


class Container:
    def __init__(self, client):
        self._client = client
        self.rodir = pathlib.PosixPath('/opt/irunner/src')
        self.rwdir = pathlib.PosixPath('/opt/irunner/dst')

    def run_and_get_results(self, cmd, env, workdir, relpath):
        c = self._client.containers.create(
            'irunner-worker',
            command=cmd,
            environment=env,
            cap_add=['SYS_PTRACE'],
            volumes={
                str(workdir.resolve()): {'bind': str(self.rodir), 'mode': 'ro'}
            },
            pids_limit=500,
        )
        c.start()
        c.wait()
        logging.info('Logs: %s', c.logs())
        _get_data(c, self.rwdir / relpath, (workdir / relpath).parent)
        c.remove()


class DockerTester(BaseTester):
    def __init__(self, cache):
        super().__init__(cache)
        self._client = docker.from_env()

    def _build(self, job, workdir, srcpaths, dstpaths):
        c = Container(self._client)
        cmd = self._make_build_command(job, c.rodir, srcpaths, c.rwdir, dstpaths)
        c.run_and_get_results(cmd, self._make_env({}), workdir, dstpaths.builddir)

    def _execute(self, job, workdir, srcpaths, dstpaths):
        c = Container(self._client)
        cmd = self._make_execute_command(job, c.rodir, srcpaths, c.rwdir, dstpaths)
        if dstpaths.reportfile is not None:
            report_path = dstpaths.reportfile
        else:
            assert dstpaths.junitxmlfile is not None
            report_path = dstpaths.junitxmlfile
        c.run_and_get_results(cmd, self._make_env({}), workdir, report_path)
