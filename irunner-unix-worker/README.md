Create a user named `tester` and add him to the `docker` group.
```
sudo useradd -r tester
sudo usermod -aG docker tester
```

Expected final configuration:
```
$ cat /etc/passwd
tester:x:998:997::/home/tester:/bin/sh
$ cat /etc/group
docker:x:998:sobols,tester
tester:x:997:
$ groups tester
tester : tester docker
```

Put the source code somewhere.
```
$ git clone git@bitbucket.org:sobols/irunner2.git
$ cd irunner2/
$ git pull
$ cd ..
```

Build the docker image.
```
$ cd irunner2/irunner-unix-worker/vm/
$ docker build . -t irunner-worker
```

Prepare the virtualenv.
```
$ sudo apt-get install python3-virtualenv
$ virtualenv venv
$ source venv/bin/activate
$ pip install docker
```

Edit the production config in `~/config.ini` (please change to real values):
```
[Server]
endpoint = http://localhost:8000/api/
token = abacaba
interval = 1

[Tester]
mode = DOCKER
```

Poor man's "daemonization": run the command inside `screen`.
```
$ cd irunner2/irunner-unix-worker/
$ while true; do python main.py ~/config.ini; sleep 30; done
```

Set up systemd services for background execution.
```
$ ls /opt/
$ sudo mkdir /opt/worker1 && sudo chown tester:tester /opt/worker1
$ sudo mkdir /opt/worker2 && sudo chown tester:tester /opt/worker2
$ sudoedit /etc/systemd/system/worker1.service
$ sudo systemctl daemon-reload
$ sudo systemctl start worker1
$ sudo systemctl status worker1
$ ls /opt/worker1/
$ cat /opt/worker1/worker.log
...
$ sudo cp /etc/systemd/system/worker{1,2}.service
$ sudoedit  /etc/systemd/system/worker2.service
```

In case of any problems, try restarting the service.
```
$ sudo service worker1 restart
$ tail /opt/worker1/worker.log
YYYY-MM-DD hh:mm:ss INFO Hello, Sir! It's test server.
YYYY-MM-DD hh:mm:ss DEBUG Starting new HTTP connection (1): acm.bsu.by:80
YYYY-MM-DD hh:mm:ss INFO Nothing to test
```
