# Source-bound experiment over the currently adopted numeric-vector runtime.
FROM python-book-price-vector:20261007
COPY state.py /tmp/price-offset-state.py
RUN python -c "import abides_markets,hashlib,pathlib,shutil,py_compile; p=pathlib.Path(abides_markets.__file__).parent/'matching/state.py'; assert hashlib.sha256(p.read_bytes()).hexdigest() == 'e71ea04f678024485a3e73d68e8d89b03ceeda14b6db9537d590b19b2a4ed4fd'; shutil.copyfile('/tmp/price-offset-state.py',p); assert hashlib.sha256(p.read_bytes()).hexdigest() == 'a2b877e6bf3d3efbe5d086f5b89ce0bdacea03c58489d28cf504a19ee7914df0'; py_compile.compile(str(p),doraise=True)" \
    && rm /tmp/price-offset-state.py
