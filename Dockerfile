FROM python:3.11-slim
SHELL ["/bin/bash", "-c"]

COPY . /srv/digitizer
WORKDIR /srv/digitizer

RUN pip3 install -r ./requirements.txt

RUN chmod +x ./start.sh
EXPOSE 8000
CMD ["./start.sh"]
