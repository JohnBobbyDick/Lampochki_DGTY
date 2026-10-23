FROM eclipse-temurin:17-jdk-alpine

RUN adduser -D -u 1000 sandbox
RUN mkdir -p /workspace && chown sandbox:sandbox /workspace

USER sandbox
WORKDIR /workspace

# The sandbox is used to compile and run Java code in isolation.
# Files are mounted/copied to /workspace, compiled and executed.
# Memory limit: 256MB (-Xmx256m)
# Time limit: enforced by the backend (10s timeout)

CMD ["tail", "-f", "/dev/null"]
