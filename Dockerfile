FROM python:3.11-slim
SHELL ["/bin/bash", "-c"]


COPY . /srv/digitizer
WORKDIR /srv/digitizer

RUN pip3 install -r ./requirements.txt
RUN apt-get update && apt-get install libgl1

RUN chmod +x ./start.sh
EXPOSE 8000
CMD ["./start.sh"]
