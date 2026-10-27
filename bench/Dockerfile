FROM python:3.12-slim

WORKDIR /bench

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# The client must come from fossasia/visdom's dev branch, not PyPI: api_key= and
# workspace= are not in a release yet. --no-deps because setup.py declares the
# *server's* dependencies, and openTSNE among them has no aarch64 wheel and needs a C++
# toolchain to build. The client's own hard imports are the four in requirements.txt;
# openTSNE sits behind a try/except that only raises if do_tsne() is called.
ARG VISDOM_REPO=https://github.com/fossasia/visdom.git
ARG VISDOM_REF=dev
RUN pip install --no-cache-dir --no-deps "visdom @ git+${VISDOM_REPO}@${VISDOM_REF}"

RUN python -c "import visdom, numpy, requests, websocket; from PIL import Image; \
import inspect; assert 'api_key' in inspect.signature(visdom.Visdom.__init__).parameters, \
'client lacks api_key= — wrong visdom build'; print('client ok', visdom.__version__)"

COPY . .

CMD ["python", "writebench.py"]
