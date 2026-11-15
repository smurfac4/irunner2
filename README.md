<p align="center"><img src="docs/images/overview.svg" alt="iRunner 2: prepare problems, submit solutions, evaluate results" width="100%"></p>

# iRunner 2 · Programming education & automated judging

A Python/Django platform for programming courses and contests: organize an archive of algorithmic problems, accept student submissions and automatically test solutions using judge workers.

**About this repository:** this is a copy of the existing Insight Runner 2 project, originally developed for use at Belarusian State University. Original authorship and repository history are preserved; this page does not claim that the platform was created from scratch by the profile owner. The original clone instructions referenced `sobols/irunner2` on Bitbucket.

## What the platform covers

| Area | Purpose |
| --- | --- |
| Problem archive | Statements, test data and reusable algorithmic tasks |
| Courses & contests | Organize programming practice and competitive events |
| Submissions | Receive solutions and track judging results |
| Judge workers | Execute and test submitted programs |
| Accounts | Users, groups, administration and two-factor authentication |

## How it fits together

The illustration above is a workflow diagram, not an application screenshot.

```text
Students & teachers → Django web application → submission queue
                               ↓                       ↓
                      problem archive             judge workers
                               ↑                       ↓
                               └──── results & verdicts
```

## Repository map

- `project/` — Django applications, templates and static assets.
- `irunner-unix-worker/` — Unix worker implementation and its setup notes.
- `requirements.txt` — pinned application dependencies.
- [Development guide](docs/DEVELOPMENT.md) — environment, database and local server setup.
- [Worker guide](irunner-unix-worker/README.md) — worker configuration.

## Development status

This repository contains a legacy dependency stack, including Django 3.1.2. Treat the existing setup instructions as historical development documentation; dependency upgrades and compatibility checks are needed before a new production deployment. No live demo or fresh installation is claimed here.
