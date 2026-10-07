# Source-bound experiment: inherit the exact measured bisect runtime.
FROM python-book-bisect:20261006
COPY state.py /tmp/price-vector-state.py
RUN python -c "import abides_markets,hashlib,pathlib,shutil,py_compile; p=pathlib.Path(abides_markets.__file__).parent/'matching/state.py'; assert hashlib.sha256(p.read_bytes()).hexdigest() == '615bcd4357f744f77fe7844f3dc648ee4e110097005a65540baa6c806f5c3f90'; shutil.copyfile('/tmp/price-vector-state.py',p); assert hashlib.sha256(p.read_bytes()).hexdigest() == 'e71ea04f678024485a3e73d68e8d89b03ceeda14b6db9537d590b19b2a4ed4fd'; py_compile.compile(str(p),doraise=True)" \
    && rm /tmp/price-vector-state.py
