FROM python:3.13-slim

WORKDIR /app

RUN pip install --upgrade pip

COPY requirements.txt ./

RUN pip install -r requirements.txt

COPY dltool.py ./

ENTRYPOINT ["python", "dltool.py"]
