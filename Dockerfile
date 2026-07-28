# Helix Core — headless backend image.
#
# Purpose: give a reviewer a one-command, network-isolated reproduction of the
# backend and its test suite, and give CI a Linux target. The Electron GUI is
# not part of this image; it is packaged separately as AppImage and deb.
#
#   docker build -t helixcore-backend .
#   docker run --rm helixcore-backend pytest -q          # run the suite
#   docker run --rm -p 8299:8299 helixcore-backend       # serve the API
#
# Reproducibility notes
# ---------------------
# * AutoDock Vina is the official upstream v1.2.6 release asset, verified by
#   SHA-256. It is NOT the conda-forge `vina` package, which is a modified
#   build reporting `f458505-mod`; using it would mean the Linux and Windows
#   results came from different engines.
# * Open Babel comes from conda-forge at the same build as the Windows bundle.
#
# * The base image is pinned by DIGEST, not by tag. A tag is mutable: republishing
#   `mambaorg/micromamba:noble` would silently change the toolchain under an
#   already published result, which is not acceptable provenance for an archival
#   claim. The digest below is the multi-architecture OCI image index for the
#   `noble` tag (it lists linux/amd64, linux/arm64 and linux/ppc64le), so pinning
#   it does not by itself constrain the build platform; the tag is retained only
#   for human readability.
#
#   THIS IMAGE IS NEVERTHELESS linux/amd64 ONLY, and the base image is not the
#   reason. The constraint is the Vina asset pinned below: upstream publishes
#   vina_1.2.6_linux_x86_64 and vina_1.2.6_linux_aarch64 as separate files with
#   separate hashes, and this Dockerfile pins the x86_64 one unconditionally.
#   `docker build --platform linux/arm64 .` therefore fails at the `vina
#   --version` smoke test with an exec-format error, and ppc64le has no upstream
#   Vina asset at all. Supporting a second architecture means adding a
#   per-architecture URL and hash, not relaxing anything here — and it would mean
#   a second engine binary whose docking results have not been compared against
#   the ones the manuscript reports. Do not do it casually.
#
#   Digest resolved 2026-07-26 from the Docker Hub registry API and confirmed by
#   recomputing SHA-256 over the returned manifest bytes. To re-resolve after a
#   deliberate base-image upgrade:
#
#       docker buildx imagetools inspect mambaorg/micromamba:noble
#
#   Use buildx, not `docker pull` + `docker inspect .RepoDigests`: depending on
#   the image store and whether the pull was platform-qualified, RepoDigests can
#   hand back the single-architecture manifest digest instead of the index
#   digest. Both look like a valid pin and only one of them is.
#
#   Never edit the digest by hand.

FROM mambaorg/micromamba:noble@sha256:a0a4da2d5315f0d5b9d98196f2e9ecf50152c750bed4023bb127baade7e8faca AS base

USER root

# curl and ca-certificates are needed only to fetch the pinned Vina asset;
# procps provides the process metrics psutil surfaces in the kernel dock.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl procps \
 && rm -rf /var/lib/apt/lists/*

# --------------------------------------------------------------------------- #
#  AutoDock Vina — official upstream release asset, pinned by hash             #
# --------------------------------------------------------------------------- #
# Two build args, both load-bearing: overriding the URL without the matching
# hash fails the build at the `sha256sum -c` below. There is deliberately no
# VINA_VERSION arg — a version knob that the URL did not actually interpolate
# would let `--build-arg VINA_VERSION=...` appear to change the engine while
# silently installing this one.
ARG VINA_SHA256=06dfe473434e666723436f6bc9379d6ea7ba75a19203feb00c1196ec3a1593e0
ARG VINA_URL=https://github.com/ccsb-scripps/AutoDock-Vina/releases/download/v1.2.6/vina_1.2.6_linux_x86_64

RUN curl -fsSL "${VINA_URL}" -o /usr/local/bin/vina \
 && echo "${VINA_SHA256}  /usr/local/bin/vina" | sha256sum -c - \
 && chmod +x /usr/local/bin/vina \
 && vina --version

# --------------------------------------------------------------------------- #
#  Python environment                                                          #
# --------------------------------------------------------------------------- #
USER $MAMBA_USER

COPY --chown=$MAMBA_USER:$MAMBA_USER \
  backend/environment.yml \
  backend/requirements.lock.txt \
  /tmp/backend/

RUN micromamba install -y -n base -f /tmp/backend/environment.yml \
 && micromamba run -n base python -m pip install --no-cache-dir \
      -r /tmp/backend/requirements.lock.txt \
      pytest==8.3.5 pytest-asyncio==1.3.0 \
 && micromamba run -n base python -m pip check \
 && micromamba clean --all --yes

ARG MAMBA_DOCKERFILE_ACTIVATE=1

# --------------------------------------------------------------------------- #
#  Application                                                                 #
# --------------------------------------------------------------------------- #
WORKDIR /app

COPY --chown=$MAMBA_USER:$MAMBA_USER backend/ /app/backend/
COPY --chown=$MAMBA_USER:$MAMBA_USER pytest.ini /app/pytest.ini

# The workspace is a mount point in normal use; create it so a bare
# `docker run` still has somewhere to write.
ENV HELIX_WORKSPACE_DIR=/app/workspace \
    HELIX_HOST=0.0.0.0 \
    HELIX_PORT=8299 \
    PYTHONUNBUFFERED=1
RUN mkdir -p /app/workspace

# No HELIX_TOOLS_DIR: on Linux both engines resolve from PATH, which is what
# backend/config.py falls back to when no bundled tools directory exists.

EXPOSE 8299

# The base image does not put the conda prefix on PATH — it activates the
# environment inside `_entrypoint.sh`. A shell-form healthcheck therefore runs
# under /bin/sh with no `python` on PATH and reports unhealthy forever, so the
# probe is routed through the same entrypoint the container itself uses.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["/usr/local/bin/_entrypoint.sh", "python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8299/api/health', timeout=4).status==200 else 1)"]

ENTRYPOINT ["/usr/local/bin/_entrypoint.sh"]
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8299"]
