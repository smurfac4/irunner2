# Django application directory

This directory contains the web application, shared templates, static assets and database migrations.

- `common/` provides generic utilities and should not depend on feature applications.
- `users/` manages users, profiles and administrator groups.
- `cauth/` handles authentication, logout and two-factor authentication.
- `problems/`, `courses/`, `contests/` and `solutions/` implement the teaching and judging workflows.
- `api/` exposes application endpoints used by workers and other clients.
- `irunner2/` contains Django settings, URL configuration and deployment entry points.

See [the main README](../README.md) for the current branch's features and setup notes.
