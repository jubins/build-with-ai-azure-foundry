FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY a2a_server.py .

# The A2A specialist listens here; Container Apps ingress targets this port.
EXPOSE 8001

CMD ["uvicorn", "a2a_server:app", "--host", "0.0.0.0", "--port", "8001"]
