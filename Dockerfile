FROM python:3.12-slim

RUN mkdir /sealed && chmod 777 /sealed

WORKDIR /app

COPY . /app

# Install gpg and python-gnupg
RUN apt-get update && apt-get install -y gnupg && \
    pip install --no-cache-dir python-gnupg


# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "-m", "my_proof"]
