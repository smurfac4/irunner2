# Original worker Docker image

Build the image from this directory:

```bash
docker build . -t irunner-worker
```

Open an interactive container for inspection:

```bash
docker run --rm -it irunner-worker
```

This image belongs to the original worker setup. See [the worker README](../README.md) for configuration and startup instructions.
