# Digest corresponds to the reviewed CLIProxyAPI v8.0.13 image.
# Update only through a separate reviewed image verification.
FROM docker.io/eceasy/cli-proxy-api@sha256:5d5a9836ebe7743e021ec88b16db59318f10f9814a3f36557fd729ae7c5539a1
WORKDIR /CLIProxyAPI
COPY entrypoint.sh /usr/local/bin/truthrail-gateway-bootstrap
RUN chmod 0755 /usr/local/bin/truthrail-gateway-bootstrap && sh -n /usr/local/bin/truthrail-gateway-bootstrap
EXPOSE 10000
ENTRYPOINT ["/usr/local/bin/truthrail-gateway-bootstrap"]
