FROM python:3.11-slim

# JDK for the runner (javac/java in JAVA_SANDBOX_MODE=subprocess), taken from the official Temurin image
COPY --from=eclipse-temurin:17-jdk /opt/java/openjdk /opt/java/openjdk
ENV JAVA_HOME=/opt/java/openjdk PATH="/opt/java/openjdk/bin:${PATH}"

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# non-root user for running untrusted Java
RUN useradd -m -u 1000 runner && chown -R runner /app
USER runner

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
