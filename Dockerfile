FROM python:3.11-slim
SHELL ["/bin/bash", "-c"]


COPY . /srv/digitizer
WORKDIR /srv/digitizer

RUN pip3 install -r ./requirements.txt
RUN apt-get update && apt-get install ffmpeg libsm6 libxext6  -y

RUN chmod +x ./start.sh
EXPOSE 8000
CMD ["./start.sh"]
