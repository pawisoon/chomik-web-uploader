FROM python:2.7

WORKDIR /app

# Fix dla Debian Buster - repozytoria przeniesione do archiwum
RUN echo "deb [trusted=yes] http://archive.debian.org/debian/ buster main" > /etc/apt/sources.list && \
    echo "deb [trusted=yes] http://archive.debian.org/debian-security buster/updates main" >> /etc/apt/sources.list && \
    apt-get update -o Acquire::Check-Valid-Until=false && \
    apt-get install -y git

# Instaluj Flask
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Instaluj ChomikUploader bezpośrednio z GitHuba
RUN pip install git+https://github.com/Grycek/ChomikUploader.git

# Kopiuj aplikację
COPY app.py .

EXPOSE 5000

CMD ["python", "app.py"]
