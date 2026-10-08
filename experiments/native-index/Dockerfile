ARG BASE_IMAGE=python-book-price-offset:20261007
FROM ${BASE_IMAGE} AS build
USER root
RUN apt-get update && apt-get install -y --no-install-recommends g++ gcc libc6-dev \
    && rm -rf /var/lib/apt/lists/*
COPY experiments/native-index/native /src/native
COPY experiments/native-index/build/native_build.py /src/native_build.py
COPY experiments/native-index/tests/book_test.cpp /src/book_test.cpp
RUN mkdir /native-output && python /src/native_build.py /src /native-output \
    && g++ -std=c++17 -O2 -Wall -I/src/native /src/book_test.cpp -o /native-output/book_test \
    && /native-output/book_test
RUN g++ -std=c++17 -O2 -fno-fast-math -ffp-contract=off -I/src/native \
    /src/native/tests/rngdump.cpp -o /native-output/rngdump

FROM ${BASE_IMAGE}
COPY --from=build /native-output/_t3engine*.so /opt/abides_fork/
COPY --from=build /native-output/book_test /opt/native-tests/book_test
COPY --from=build /native-output/rngdump /opt/native-tests/rngdump
COPY experiments/native-index/adapter/ /opt/abides_fork/
COPY experiments/native-index/LICENSE.abides /opt/licenses/native-abides-LICENSE
COPY experiments/native-index/native/svml/LICENSE /opt/licenses/native-numpy-LICENSE
RUN python -m compileall -q -j 0 /usr/local/lib/python3.11 /opt
WORKDIR /tmp
ENV T3_ENGINE=auto
