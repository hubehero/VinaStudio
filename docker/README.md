# Headless Docker image

The image contains the CLI and local API server, not Qt. The desktop shell is
the `[desktop]` extra and is not installed here.

```bash
docker build -f docker/Dockerfile -t vinastudio-headless .
docker run --rm vinastudio-headless version --json
```

Dock a job from a mounted workspace:

```bash
docker run --rm -v "$PWD:/work" -w /work \
  vinastudio-headless dock --config job.json --out out --json
```

Run the local API server with a token (the container must bind `0.0.0.0` to be
reachable from the host; the token is required):

```bash
docker run --rm -p 127.0.0.1:8000:8000 \
  -e VINASTUDIO_API_TOKEN=change-me \
  vinastudio-headless server --host 0.0.0.0 --port 8000
```

The image has no GPU support and downloads no datasets. Mount only the data you
want the container to read/write. `VINASTUDIO_API_TOKEN` is the local API token;
do not publish the port without it.
