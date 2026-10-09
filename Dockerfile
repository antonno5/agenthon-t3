# Track 3 submission image, minimal variant: the fully static native simulator and nothing else.
#
# Every public unit (65 single + 6 batch) runs on the native path, so the Python/ABIDES
# fallback is left out of this variant (see Dockerfile.full for the image that keeps it):
# a scenario the native path cannot run fails here instead of being delegated.
#
#   docker build --platform=linux/amd64 -t agenthon-t3:tiny .
#   docker run --rm --network none -v <in>:/input:ro -v <out>:/output agenthon-t3:tiny \
#       simulate --config /input/scenario.json --out /output/trace.parquet
FROM --platform=linux/amd64 python:3.11-slim@sha256:0dd364ba7e10242f07755449e3a3d0e35f9efd987952737b90def6709ab0c5ce AS native_build
RUN apt-get update && apt-get install -y --no-install-recommends g++ gcc libc6-dev \
    && rm -rf /var/lib/apt/lists/*
COPY native /src/native
COPY build_executable.py /src/build_executable.py
COPY pgo /src/pgo
RUN python /src/build_executable.py /src /out/usr/local/bin \
    && ln -s t3-native /out/usr/local/bin/simulate \
    && ln -s t3-native /out/usr/local/bin/simulate-batch \
    && mkdir -p /out/opt/licenses /out/tmp /out/etc/ld.so.conf.d /out/usr/lib/x86_64-linux-gnu \
    && printf 'root:x:0:0:root:/root:/sbin/nologin\nnobody:x:65534:65534:nobody:/nonexistent:/sbin/nologin\n' > /out/etc/passwd \
    && printf 'root:x:0:\nnogroup:x:65534:\n' > /out/etc/group \
    && cp /src/native/LICENSE.abides /out/opt/licenses/native-abides-LICENSE \
    && cp /src/native/svml/LICENSE /out/opt/licenses/native-numpy-LICENSE \
    && cp /src/native/vendor/LICENSE.json /out/opt/licenses/native-json-LICENSE

# A conventional skeleton (/etc with passwd/group and ld.so.conf.d, the multiarch lib dir) so
# runtime hooks that expect a distro layout (e.g. a GPU runtime's ldconfig step) find one.
FROM scratch
# Required on every submission image by the published contract (SUBMISSION_CLI.md).
LABEL qfbench2.interface_version="2.0"
COPY --from=native_build /out/ /
ENV PATH=/usr/local/bin T3_ENGINE=auto
# The platform makes the root filesystem read-only and provides a writable /tmp.
WORKDIR /tmp
# No ENTRYPOINT: the harness passes `simulate --config ... --out ...` as the command.
CMD ["simulate", "--help"]
