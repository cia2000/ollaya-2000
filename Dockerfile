FROM ghcr.io/ollaya-dev/ollaya:cuda12

# Bind mount these paths to keep question definitions and downloaded models on
# the host.
WORKDIR /questions
VOLUME ["/questions", "/home/ollaya/.ollaya/models"]
