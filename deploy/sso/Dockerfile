ARG PYTHON_IMAGE=python:3.12-alpine
FROM ${PYTHON_IMAGE}
COPY sync.py /opt/files-sso/sync.py
USER 1000:1000
ENTRYPOINT ["python3", "/opt/files-sso/sync.py"]
